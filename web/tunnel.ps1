# Cloudflare Tunnel control for the local knowledge-base web service (plan A).
# Exposes http://127.0.0.1:<Port> to a public https URL WITHOUT opening any
# inbound firewall port, so the local Ollama models stay on this machine.
#
# Safety rule (see agent.md section 6): the tunnel REFUSES to start unless an
# access token is set, because the moment the URL is public anyone holding it
# can burn this machine's model. Override deliberately with -AllowNoToken.
#
# NOTE: keep all output strings ASCII-only. Windows PowerShell 5.1 reads .ps1
# as ANSI (GBK) when there is no BOM, so non-ASCII strings break parsing.

param(
    [Parameter(Position = 0)]
    [string]$Action = 'start',
    [int]$Port = 18765,
    [string]$HostAddr = '127.0.0.1',
    [string]$Token,
    [string]$TunnelName,
    [switch]$AllowNoToken
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$rt = Join-Path $here '.runtime'
if (-not (Test-Path $rt)) { New-Item -ItemType Directory -Path $rt | Out-Null }
$pidFile = Join-Path $rt 'tunnel.pid'
$logFile = Join-Path $rt 'tunnel.log'
$errFile = Join-Path $rt 'tunnel.err.log'
$urlFile = Join-Path $rt 'tunnel.url'

# 1. locate cloudflared
$exe = $null
$cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
if ($cmd) { $exe = $cmd.Source }
if (-not $exe) {
    foreach ($c in @(
            (Join-Path $env:ProgramData 'cloudflared\cloudflared.exe'),
            (Join-Path $rt 'cloudflared.exe'),
            (Join-Path $env:USERPROFILE 'cloudflared.exe'))) {
        if (Test-Path $c) { $exe = $c; break }
    }
}
if (-not $exe) {
    Write-Host 'ERROR: cloudflared not found.' -ForegroundColor Red
    Write-Host 'Install one of these ways, then re-run:'
    Write-Host '  winget install --id Cloudflare.cloudflared'
    Write-Host '  or download cloudflared-windows-amd64.exe from GitHub releases'
    Write-Host ('  and place it at ' + (Join-Path $env:ProgramData 'cloudflared\cloudflared.exe'))
    exit 1
}

# 2. resolve access token (env wins unless -Token given)
$tok = $Token
if (-not $tok) { $tok = $env:KB_ACCESS_TOKEN }
$tok = ($tok | Out-String).Trim()

$target = 'http://' + $HostAddr + ':' + $Port

function Test-Service {
    try {
        $hdr = @{}
        if ($tok) { $hdr['X-KB-Token'] = $tok }
        $null = Invoke-RestMethod -Uri ($target + '/api/status') -Headers $hdr -TimeoutSec 5
        return $true
    }
    catch {
        # 401 still means the service is alive and the guard is working
        $resp = $_.Exception.Response
        if ($resp -and $resp.StatusCode.value__ -eq 401) { return $true }
        return $false
    }
}

$runningPid = 0
if (Test-Path $pidFile) { $runningPid = [int](Get-Content $pidFile -Raw) }
function Test-TunnelRunning {
    if ($script:runningPid -gt 0) {
        return ($null -ne (Get-Process -Id $script:runningPid -ErrorAction SilentlyContinue))
    }
    return $false
}

# End-to-end proof that the running service really enforces the passcode:
# an unauthenticated /api/status MUST come back 401. A 200 here means the
# service was started WITHOUT KB_ACCESS_TOKEN, and opening a tunnel on top of
# that would publish the local models to anyone. Uses curl.exe because
# Invoke-WebRequest would try to negotiate the 401 challenge and hang.
function Test-GuardEnforced {
    $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
    if (-not $curl) { return $null }   # cannot verify
    $code = (& curl.exe -s -o NUL -w "%{http_code}" --max-time 8 ($target + '/api/status') 2>$null | Out-String).Trim()
    if ($code -eq '401') { return $true }
    if ($code -eq '200') { return $false }
    return $null
}

if ($Action -eq 'start') {
    if (-not (Test-TunnelRunning) -and -not $AllowNoToken -and -not $tok) {
        Write-Host 'REFUSED: no access token set.' -ForegroundColor Red
        Write-Host 'A public URL without a token lets anyone use your local models.'
        Write-Host 'Set one first, then start the service and the tunnel:'
        Write-Host '  $env:KB_ACCESS_TOKEN = "<your-passcode>"'
        Write-Host '  powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action start'
        Write-Host '  powershell -ExecutionPolicy Bypass -File web\tunnel.ps1 -Action start'
        Write-Host 'Override (NOT recommended) with -AllowNoToken'
        exit 1
    }

    if (Test-TunnelRunning) {
        Write-Host ('tunnel already running (PID ' + $runningPid + ')')
        if (Test-Path $urlFile) { Write-Host ('public URL: ' + (Get-Content $urlFile -Raw).Trim()) }
        exit 0
    }

    if (-not (Test-Service)) {
        Write-Host ('WARNING: nothing healthy on ' + $target) -ForegroundColor Yellow
        Write-Host 'Start the service first:'
        Write-Host '  powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action start'
        Write-Host ''
    }
    else {
        # The service is up - but is it actually guarded? This is the check that
        # catches "service started without KB_ACCESS_TOKEN" before we publish it.
        $guarded = Test-GuardEnforced
        if ($guarded -eq $false) {
            Write-Host 'REFUSED: the running service answers WITHOUT a passcode.' -ForegroundColor Red
            Write-Host 'It was started without KB_ACCESS_TOKEN, so /api/status returns 200 with no token.'
            Write-Host 'Opening a tunnel now would expose your local models to anyone with the URL.'
            Write-Host 'Fix it (note the env var must be set in THIS shell before starting):'
            Write-Host '  $env:KB_ACCESS_TOKEN = "<your-passcode>"'
            Write-Host '  powershell -ExecutionPolicy Bypass -File web\run.ps1 -Action restart'
            Write-Host 'then start the tunnel again.'
            exit 1
        }
        elseif ($null -eq $guarded) {
            Write-Host 'WARNING: could not verify the passcode guard (curl.exe unavailable).' -ForegroundColor Yellow
        }
        else {
            Write-Host '[auth] verified: unauthenticated request returns 401.'
        }
    }

    if ($TunnelName) {
        $cargs = @('tunnel', '--no-autoupdate', 'run', $TunnelName)
        Write-Host ('starting NAMED tunnel: ' + $TunnelName)
    }
    else {
        $cargs = @('tunnel', '--no-autoupdate', '--url', $target)
        Write-Host ('starting quick tunnel -> ' + $target)
    }

    Remove-Item $urlFile -Force -ErrorAction SilentlyContinue
    $proc = Start-Process -FilePath $exe -ArgumentList $cargs -WindowStyle Hidden `
        -RedirectStandardOutput $logFile -RedirectStandardError $errFile -PassThru
    Set-Content -Path $pidFile -Value $proc.Id

    # parse the public URL out of the cloudflared banner.
    # Match ONLY *.trycloudflare.com: the banner also contains cloudflare.com
    # terms-of-use links, and a looser pattern happily matches those instead.
    $url = $null
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 700
        foreach ($f in @($errFile, $logFile)) {
            if (Test-Path $f) {
                $txt = Get-Content $f -Raw -ErrorAction SilentlyContinue
                if ($txt) {
                    $m = [regex]::Match($txt, 'https://[a-z0-9][a-z0-9-]*\.trycloudflare\.com')
                    if ($m.Success) { $url = $m.Value; break }
                }
            }
        }
        if ($url) { break }
    }

    if ($url) {
        Set-Content -Path $urlFile -Value $url
        Write-Host ''
        Write-Host '=====================================================' -ForegroundColor Green
        Write-Host ('  PUBLIC URL: ' + $url) -ForegroundColor Green
        Write-Host '=====================================================' -ForegroundColor Green
        Write-Host 'Share this URL plus the access passcode with your testers.'
        if ($tok) { Write-Host ('Passcode is the KB_ACCESS_TOKEN you set (' + $tok.Length + ' chars).') }
        Write-Host 'Mobile: open the URL in the phone browser, then "Add to Home screen".'
    }
    else {
        Write-Host 'tunnel started but no public URL parsed yet; check logs:' -ForegroundColor Yellow
        Write-Host ('  ' + $errFile)
        Write-Host ('  ' + $logFile)
    }
}
elseif ($Action -eq 'stop') {
    if (Test-TunnelRunning) {
        Stop-Process -Id $runningPid -Force
        Write-Host ('stopped tunnel PID ' + $runningPid)
    }
    else { Write-Host 'tunnel not running.' }
    Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Remove-Item $pidFile -Force -ErrorAction SilentlyContinue
    Remove-Item $urlFile -Force -ErrorAction SilentlyContinue
}
elseif ($Action -eq 'status') {
    if (Test-TunnelRunning) {
        Write-Host ('tunnel running (PID ' + $runningPid + ')')
        if (Test-Path $urlFile) { Write-Host ('public URL: ' + (Get-Content $urlFile -Raw).Trim()) }
    }
    else { Write-Host 'tunnel not running.' }
    $guarded = Test-GuardEnforced
    if ($guarded -eq $true) { Write-Host '[auth] verified: unauthenticated request returns 401.' }
    elseif ($guarded -eq $false) { Write-Host '[auth] WARNING: service answers WITHOUT a passcode - do not expose this.' -ForegroundColor Red }
    else { Write-Host '[auth] could not verify guard (service down, or curl.exe missing).' }
    if ($tok) { Write-Host '[auth] KB_ACCESS_TOKEN is present in this shell.' }
    else { Write-Host '[auth] KB_ACCESS_TOKEN is NOT set in this shell.' -ForegroundColor Yellow }
}
elseif ($Action -eq 'url') {
    if (Test-Path $urlFile) { Write-Host ((Get-Content $urlFile -Raw).Trim()) }
    else { Write-Host 'no public URL recorded (tunnel not started?)' }
}
elseif ($Action -eq 'logs') {
    if (Test-Path $errFile) { Get-Content $errFile -Tail 40 }
    if (Test-Path $logFile) { Get-Content $logFile -Tail 20 }
}
else {
    Write-Host 'usage: tunnel.ps1 <start|stop|status|url|logs> [-Port 18765] [-Token <passcode>] [-TunnelName <named-tunnel>] [-AllowNoToken]'
}
