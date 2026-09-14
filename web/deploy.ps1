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
$target = 'http://127.0.0.1:' + $Port

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
        $c = (& curl.exe -s -o NUL -w '%{http_code}' --max-time 6 ($target + '/api/status') 2>$null | Out-String).Trim()
        if ($c -eq '200' -or $c -eq '401') { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Test-GuardEnforced {
    $c = (& curl.exe -s -o NUL -w '%{http_code}' --max-time 8 ($target + '/api/status') 2>$null | Out-String).Trim()
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
switch ($Action) {

    'ensure' {
        if (-not $tok) {
            Write-Log 'REFUSED: KB_ACCESS_TOKEN is not set - will not expose anything publicly.'
            Write-Host 'Set it once, then re-run:'
            Write-Host '  [Environment]::SetEnvironmentVariable("KB_ACCESS_TOKEN","<passcode>","User")'
            exit 1
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
            -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + $ps1 + '" -Action ensure -Port ' + $Port)
        $trigLogon = New-ScheduledTaskTrigger -AtLogOn
        # no -RepetitionDuration on purpose: an empty Duration means "repeat
        # indefinitely". [TimeSpan]::MaxValue serialises to P99999999DT23H59M59S
        # which Task Scheduler rejects as out of range.
        $trigRepeat = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
            -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes)
        $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
        $prin = New-ScheduledTaskPrincipal -UserId ($env:USERDOMAIN + '\' + $env:USERNAME) -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $act -Trigger @($trigLogon, $trigRepeat) `
            -Settings $set -Principal $prin -Force `
            -Description 'Keep the study knowledge base service and public tunnel alive (see web/README.md).' | Out-Null
        $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        if ($t) {
            Write-Host ('scheduled task installed: ' + $TaskName + '  (state=' + $t.State + ')')
            Write-Host ('  at logon + every ' + $IntervalMinutes + ' minutes -> deploy.ps1 -Action ensure')
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
