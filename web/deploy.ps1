# One-stop "keep the knowledge base online" controller (plan A, persistent).
#
#   ensure        bring up whatever is missing (service, tunnel) + verify guard
#   status        show current state and public URL
#   stop          stop tunnel (service keeps running)
#   url           print the public URL only
#   install-task  register a Scheduled Task: run at logon + every N minutes
#   uninstall-task remove that task
#
# Tunnel backends:
#   tailscale   Tailscale Funnel -> PERMANENT https://<machine>.<tailnet>.ts.net
#   cloudflare  cloudflared quick tunnel -> random URL, changes on every restart
#   auto        prefer tailscale when it is installed AND logged in
#
# Safety (see agent.md section 6): refuses to expose anything without
# KB_ACCESS_TOKEN, and verifies end-to-end that an unauthenticated request
# really gets 401 before declaring success.
#
# NOTE: keep all output strings ASCII-only (Windows PowerShell 5.1 reads
# BOM-less .ps1 as ANSI/GBK, which breaks non-ASCII code).

param(
    [Parameter(Position = 0)]
    [ValidateSet('ensure', 'status', 'stop', 'url', 'install-task', 'uninstall-task')]
    [string]$Action = 'ensure',
    [int]$Port = 18765,
    [ValidateSet('auto', 'tailscale', 'cloudflare')]
    [string]$Tunnel = 'auto',
    [ValidateSet('host', 'vm')]
    [string]$Target = 'host',
    [string]$VmIp = '',
    [int]$IntervalMinutes = 5,
    [string]$TaskName = 'StudyKnowledge-KB-AutoDeploy'
)

$ErrorActionPreference = 'Continue'
$env:PYTHONUTF8 = '1'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$rt = Join-Path $here '.runtime'
if (-not (Test-Path $rt)) { New-Item -ItemType Directory -Path $rt | Out-Null }
$urlFile = Join-Path $rt 'public.url'
$logFile = Join-Path $rt 'deploy.log'
# NOTE: not $target -- PowerShell variable names are case-insensitive, so
# $target would collide with the -Target parameter above.
$svcUrl = 'http://127.0.0.1:' + $Port

function Write-Log($msg) {
    $line = ('[{0}] {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg)
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $msg
}

# ---- token: process env first, then the persisted user-level variable ----
$tok = $env:KB_ACCESS_TOKEN
if (-not $tok) { $tok = [Environment]::GetEnvironmentVariable('KB_ACCESS_TOKEN', 'User') }
$tok = ($tok | Out-String).Trim()
if ($tok) { $env:KB_ACCESS_TOKEN = $tok }

function Test-ServiceUp {
    # 200 = up and we hold a valid token; 401 = up and guarded
    foreach ($n in 1..2) {
        $c = (& curl.exe -s -o NUL -w '%{http_code}' --max-time 6 ($svcUrl + '/api/status') 2>$null | Out-String).Trim()
        if ($c -eq '200' -or $c -eq '401') { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Test-GuardEnforced {
    $c = (& curl.exe -s -o NUL -w '%{http_code}' --max-time 8 ($svcUrl + '/api/status') 2>$null | Out-String).Trim()
    if ($c -eq '401') { return $true }
    if ($c -eq '200') { return $false }
    return $null
}

function Get-TailscaleExe {
    $c = Get-Command tailscale -ErrorAction SilentlyContinue
    if ($c) { return $c.Source }
    $p = Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'
    if (Test-Path $p) { return $p }
    return $null
}

function Get-TailscaleState {
    $ts = Get-TailscaleExe
    if (-not $ts) { return 'absent' }
    $j = (& $ts status --json 2>$null | Out-String)
    if (-not $j) { return 'down' }
    try { $o = $j | ConvertFrom-Json } catch { return 'down' }
    if ($o.BackendState -ne 'Running') { return $o.BackendState }   # NeedsLogin / Stopped
    return 'running'
}

function Get-TailscaleUrl($ts) {
    try {
        $o = ((& $ts status --json 2>$null | Out-String) | ConvertFrom-Json)
        $dns = ($o.Self.DNSName | Out-String).Trim().TrimEnd('.')
        if ($dns) { return 'https://' + $dns }
    }
    catch { }
    return $null
}

function Start-Service {
    if (Test-ServiceUp) { return $true }
    Write-Log 'service down -> starting run.ps1'
    Start-Process powershell -ArgumentList '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $here 'run.ps1'), '-Action', 'start' -WindowStyle Hidden -PassThru | Out-Null
    foreach ($i in 1..20) {
        Start-Sleep -Seconds 2
        if (Test-ServiceUp) { Write-Log ('service up after ' + ($i * 2) + 's'); return $true }
    }
    Write-Log 'ERROR: service did not come up'
    return $false
}

function Start-TunnelTailscale {
    $ts = Get-TailscaleExe
    if (-not $ts) { Write-Log 'tailscale not installed'; return $null }
    $st = Get-TailscaleState
    if ($st -ne 'running') {
        Write-Log ('tailscale state is ' + $st + ' - log in once with: & "' + $ts + '" up')
        return $null
    }
    $cur = (& $ts funnel status 2>&1 | Out-String)
    if ($cur -notmatch ('127\.0\.0\.1:' + $Port)) {
        Write-Log ('enabling funnel on port ' + $Port)
        & $ts funnel --bg --yes $Port 2>&1 | Out-String | ForEach-Object { if ($_.Trim()) { Write-Log ('  ' + $_.Trim()) } }
    }
    else {
        Write-Log 'funnel already points at this port'
    }
    return (Get-TailscaleUrl $ts)
}

function Start-TunnelCloudflare {
    Write-Log 'starting cloudflare quick tunnel via tunnel.ps1'
    Start-Process powershell -ArgumentList '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $here 'tunnel.ps1'), '-Action', 'start', '-Port', "$Port" -WindowStyle Hidden -PassThru | Out-Null
    foreach ($i in 1..30) {
        Start-Sleep -Seconds 2
        $uf = Join-Path $rt 'tunnel.url'
        if (Test-Path $uf) { return ((Get-Content $uf -Raw) | Out-String).Trim() }
    }
    return $null
}

function Stop-TunnelAll {
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    $ts = Get-TailscaleExe
    if ($ts) {
        $st = Get-TailscaleState
        if ($st -eq 'running') { & $ts funnel reset 2>&1 | Out-Null }
    }
    Write-Log 'tunnels stopped'
}

function Resolve-Backend {
    if ($Tunnel -ne 'auto') { return $Tunnel }
    if ((Get-TailscaleState) -eq 'running') { return 'tailscale' }
    return 'cloudflare'
}

# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# VM target (Target=vm): the site runs in the Ubuntu VM, but the PUBLIC URL
# stays exactly the same.
#
#   Windows boot -> VM autostart task -> containers (restart:unless-stopped)
#   logon task   -> deploy.ps1 -Target vm ensure:
#                     stop host copy of the service  (frees 18765)
#                     start VM, wait for its 18765
#                     netsh portproxy  0.0.0.0:18765 -> <vmIp>:18765
#                     Tailscale Funnel  -> 127.0.0.1:18765  (unchanged)
#
# so https://<machine>.<tailnet>.ts.net keeps working and friends' links do not
# change. Requires elevation for `netsh interface portproxy` -> the logon task
# is registered with -RunLevel Highest.
# --------------------------------------------------------------------------
function Get-VmIp {
    if ($VmIp) { return $VmIp }
    $lease = 'C:\ProgramData\VMware\vmnetdhcp.leases'
    if (Test-Path $lease) {
        $txt = Get-Content $lease -Raw -ErrorAction SilentlyContinue
        $m = [regex]::Matches($txt, 'lease\s+(\d+\.\d+\.\d+\.\d+)\s*\{')
        if ($m.Count -gt 0) { return $m[$m.Count - 1].Groups[1].Value }
    }
    return '192.168.163.128'
}

function Test-TcpPort($ip, $p, $ms) {
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $c.BeginConnect($ip, $p, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne($ms, $false)
        return ($ok -and $c.Connected)
    }
    catch { return $false }
    finally { $c.Close() }
}

function Ensure-PortProxy($listenPort, $targetIp, $targetPort) {
    $show = (& netsh interface portproxy show v4tov4 2>&1 | Out-String)
    $pat = '0\.0\.0\.0\s+' + $listenPort + '\s+' + [regex]::Escape($targetIp) + '\s+' + $targetPort
    if ($show -match $pat) { Write-Log ('  portproxy already: ' + $listenPort + ' -> ' + $targetIp + ':' + $targetPort); return $true }
    & netsh interface portproxy delete v4tov4 listenport=$listenPort listenaddress=0.0.0.0 2>&1 | Out-Null
    $r = (& netsh interface portproxy add v4tov4 listenport=$listenPort listenaddress=0.0.0.0 connectport=$targetPort connectaddress=$targetIp 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        Write-Log ('  ERROR portproxy add failed (need admin?): ' + $r.Trim())
        return $false
    }
    Write-Log ('  portproxy set: ' + $listenPort + ' -> ' + $targetIp + ':' + $targetPort)
    return $true
}

function Ensure-VmServe {
    $ip = Get-VmIp
    Write-Log ('target=vm  vmIp=' + $ip)

    # 1) free the port on the host: the host copy of the service must not run
    $hostPidFile = Join-Path $rt 'server.pid'
    if (Test-Path $hostPidFile) {
        $hp = [int](Get-Content $hostPidFile -Raw)
        if (Get-Process -Id $hp -ErrorAction SilentlyContinue) {
            Write-Log '  stopping host copy of the service (frees port)'
            Start-Process powershell -ArgumentList '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $here 'run.ps1'), '-Action', 'stop' -WindowStyle Hidden -PassThru | Out-Null
            Start-Sleep -Seconds 4
        }
    }
    # a portproxy listening on 0.0.0.0:18765 excludes a local 127.0.0.1 bind;
    # make sure no stale host listener is left
    $holder = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue |
              Where-Object { $_.LocalAddress -ne '0.0.0.0' }
    foreach ($h in $holder) {
        $pr = Get-Process -Id $h.OwningProcess -ErrorAction SilentlyContinue
        if ($pr -and $pr.ProcessName -match 'python') {
            Write-Log ('  killing stale host listener PID ' + $pr.Id)
            Stop-Process -Id $pr.Id -Force -ErrorAction SilentlyContinue
        }
    }

    # 2) VM up (autostart task normally already did this)
    $vmPs = Join-Path $here 'vm.ps1'
    if (Test-Path $vmPs) {
        Start-Process powershell -ArgumentList '-ExecutionPolicy', 'Bypass', '-File', $vmPs, '-Action', 'start' -WindowStyle Hidden -PassThru | Out-Null
    }

    # 3) wait for the service inside the VM
    $up = $false
    foreach ($i in 1..40) {
        if (Test-TcpPort $ip $Port 3000) { $up = $true; Write-Log ('  VM service reachable after ' + ($i * 3) + 's'); break }
        Start-Sleep -Seconds 3
    }
    if (-not $up) {
        Write-Log ('  ERROR: VM service not reachable at ' + $ip + ':' + $Port)
        Write-Log '  check inside the VM:  cd /opt/study-knowledge && docker compose ps'
        return $false
    }

    # 4) forward + funnel
    if (-not (Ensure-PortProxy $Port $ip $Port)) { return $false }

    $be = Resolve-Backend
    Write-Log ('  tunnel backend: ' + $be)
    $url = $null
    if ($be -eq 'tailscale') { $url = Start-TunnelTailscale }
    if (-not $url -and $be -eq 'tailscale') {
        Write-Log '  tailscale unavailable; falling back to cloudflare quick tunnel'
        $url = Start-TunnelCloudflare
    }
    elseif ($be -eq 'cloudflare') { $url = Start-TunnelCloudflare }

    # 5) guard must be live (this goes through the proxy into the VM)
    $guarded = Test-GuardEnforced
    if ($guarded -eq $true) { Write-Log '[auth] OK: unauthenticated request returns 401 (via VM)' }
    elseif ($guarded -eq $false) {
        Write-Log '[auth] CRITICAL: service answers WITHOUT a passcode - stopping tunnels'
        Stop-TunnelAll
        return $false
    }
    else { Write-Log '[auth] WARNING: could not verify guard' }

    if ($url) {
        Set-Content -Path $urlFile -Value $url -Encoding ASCII
        Write-Log ('PUBLIC URL: ' + $url + '  -> VM ' + $ip)
    }
    else { Write-Log 'no public URL available'; return $false }
    return $true
}

switch ($Action) {

    'ensure' {
        if (-not $tok) {
            Write-Log 'REFUSED: KB_ACCESS_TOKEN is not set - will not expose anything publicly.'
            Write-Host 'Set it once, then re-run:'
            Write-Host '  [Environment]::SetEnvironmentVariable("KB_ACCESS_TOKEN","<passcode>","User")'
            exit 1
        }

        if ($Target -eq 'vm') {
            if (-not (Ensure-VmServe)) { exit 1 }
            exit 0
        }

        if (-not (Start-Service)) { exit 1 }

        $be = Resolve-Backend
        Write-Log ('tunnel backend: ' + $be)

        $url = $null
        if ($be -eq 'tailscale') { $url = Start-TunnelTailscale }
        if (-not $url -and $be -eq 'tailscale') {
            Write-Log 'tailscale unavailable; falling back to cloudflare quick tunnel'
            $url = Start-TunnelCloudflare
        }
        elseif ($be -eq 'cloudflare') { $url = Start-TunnelCloudflare }

        # the check that actually matters: is the guard live?
        $guarded = Test-GuardEnforced
        if ($guarded -eq $true) { Write-Log '[auth] OK: unauthenticated request returns 401' }
        elseif ($guarded -eq $false) {
            Write-Log '[auth] CRITICAL: service answers WITHOUT a passcode - stopping tunnels'
            Stop-TunnelAll
            exit 1
        }
        else { Write-Log '[auth] WARNING: could not verify guard' }

        if ($url) {
            Set-Content -Path $urlFile -Value $url -Encoding ASCII
            Write-Log ('PUBLIC URL: ' + $url)
        }
        else {
            Write-Log 'no public URL available (see messages above)'
            exit 1
        }
    }

    'status' {
        $up = Test-ServiceUp
        Write-Host ('service   : ' + $(if ($up) { 'UP' } else { 'DOWN' }))
        if ($up) {
            $g = Test-GuardEnforced
            Write-Host ('auth guard: ' + $(if ($g -eq $true) { 'OK (401 without token)' } elseif ($g -eq $false) { 'MISSING - DO NOT EXPOSE' } else { 'unknown' }))
        }
        $ts = Get-TailscaleExe
        Write-Host ('tailscale : ' + $(if ($ts) { (Get-TailscaleState) } else { 'not installed' }))
        if ($ts -and (Get-TailscaleState) -eq 'running') {
            Write-Host ('funnel    : ' + (Get-TailscaleUrl $ts))
        }
        Write-Host ('cloudflared procs: ' + (Get-Process cloudflared -ErrorAction SilentlyContinue | Measure-Object).Count)
        if (Test-Path $urlFile) { Write-Host ('public URL: ' + ((Get-Content $urlFile -Raw) | Out-String).Trim()) }
        $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Write-Host ('auto task : ' + $(if ($t) { $t.State } else { 'not installed' }))
    }

    'stop' { Stop-TunnelAll }

    'url' {
        if (Test-Path $urlFile) { Write-Host (((Get-Content $urlFile -Raw) | Out-String).Trim()) }
        else { Write-Host 'no public URL recorded yet' }
    }

    'install-task' {
        $ps1 = Join-Path $here 'deploy.ps1'
        $act = New-ScheduledTaskAction -Execute 'powershell.exe' `
            -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
                       $ps1 + '" -Action ensure -Target ' + $Target + ' -Port ' + $Port)
        $trigLogon = New-ScheduledTaskTrigger -AtLogOn
        # Logon-only by default: a repeating trigger kept popping up a console
        # window every few minutes and interrupting the user. Pass
        # -IntervalMinutes N (>0) to also add a watchdog repeat.
        $triggers = @($trigLogon)
        if ($IntervalMinutes -gt 0) {
            # no -RepetitionDuration on purpose: an empty Duration means "repeat
            # indefinitely". [TimeSpan]::MaxValue serialises to
            # P99999999DT23H59M59S which Task Scheduler rejects as out of range.
            $triggers += New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
                -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
        }
        $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 20) -Hidden
        # Highest: netsh interface portproxy (Target=vm) needs admin rights
        $runLevel = if ($Target -eq 'vm') { 'Highest' } else { 'Limited' }
        $prin = New-ScheduledTaskPrincipal -UserId ($env:USERDOMAIN + '\' + $env:USERNAME) -LogonType Interactive -RunLevel $runLevel
        Register-ScheduledTask -TaskName $TaskName -Action $act -Trigger $triggers `
            -Settings $set -Principal $prin -Force `
            -Description 'Keep the study knowledge base online: start VM, forward port, keep tunnel alive (see web/README.md).' | Out-Null
        $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($t) {
            Write-Host ('scheduled task installed: ' + $TaskName + '  (state=' + $t.State + ', target=' + $Target + ', runLevel=' + $runLevel + ')')
            if ($IntervalMinutes -gt 0) {
                Write-Host ('  at logon + every ' + $IntervalMinutes + ' minutes -> deploy.ps1 -Action ensure -Target ' + $Target)
            }
            else {
                Write-Host ('  at logon only (no repeat, no popup) -> deploy.ps1 -Action ensure -Target ' + $Target)
            }
        }
        else {
            Write-Host 'ERROR: scheduled task was NOT created (see message above).' -ForegroundColor Red
            exit 1
        }
    }

    'uninstall-task' {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Write-Host ('scheduled task removed: ' + $TaskName)
    }
}
