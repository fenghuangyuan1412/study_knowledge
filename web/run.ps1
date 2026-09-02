# Local knowledge-base web service control (start/stop/status/logs/restart)
param(
    [Parameter(Position = 0)]
    [string]$Action = 'start',
    [int]$Port = 18765,
    [string]$HostAddr = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$rt = Join-Path $here '.runtime'
$pidFile = Join-Path $rt 'server.pid'
$logFile = Join-Path $rt 'server.log'
$errFile = Join-Path $rt 'server.err.log'

if (-not (Test-Path $rt)) { New-Item -ItemType Directory -Path $rt | Out-Null }

$py = Join-Path $env:APPDATA 'uv\tools\localbrain\Scripts\python.exe'
if (-not (Test-Path $py)) { $py = Join-Path $env:USERPROFILE '.local\share\uv\tools\localbrain\Scripts\python.exe' }
if (-not (Test-Path $py)) { $c = Get-Command python -ErrorAction SilentlyContinue; if ($c) { $py = $c.Source } }
if (-not $py) { Write-Host 'ERROR: python (with localbrain) not found.' -ForegroundColor Red; exit 1 }

$currentPid = 0
if (Test-Path $pidFile) { $currentPid = [int](Get-Content $pidFile -Raw) }

function Test-Running {
    if ($script:currentPid -gt 0) {
        $proc = Get-Process -Id $script:currentPid -ErrorAction SilentlyContinue
        return ($null -ne $proc)
    }
    return $false
}

$url = 'http://' + $HostAddr + ':' + $Port

if ($Action -eq 'start') {
    if (Test-Running) {
        Write-Host ('already running (PID ' + $currentPid + '): ' + $url)
    }
    else {
        $env:PORT = [string]$Port
        $env:HOST = $HostAddr
        $p = Start-Process -FilePath $py -ArgumentList @('server.py') -WorkingDirectory $here -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errFile -PassThru
        Set-Content -Path $pidFile -Value $p.Id
        Start-Sleep -Seconds 3
        Write-Host ('started (PID ' + $p.Id + '): ' + $url)
        try {
            $null = Invoke-RestMethod -Uri ($url + '/api/status') -TimeoutSec 6
            Write-Host 'health check OK.'
        }
        catch {
            Write-Host 'starting; if still unavailable later, check logs:'
            Write-Host ('  ' + $logFile)
            Write-Host ('  ' + $errFile)
        }
    }
}
elseif ($Action -eq 'stop') {
    if (Test-Running) {
        Stop-Process -Id $currentPid -Force
        Write-Host ('stopped PID ' + $currentPid)
    }
    else { Write-Host 'not running.' }
    if (Test-Path $pidFile) { Remove-Item $pidFile -Force }
}
elseif ($Action -eq 'status') {
    if (Test-Running) { Write-Host ('running (PID ' + $currentPid + '): ' + $url) }
    else { Write-Host 'not running.' }
}
elseif ($Action -eq 'logs') {
    if (Test-Path $logFile) { Get-Content $logFile -Tail 40 }
    else { Write-Host 'no logs yet.' }
}
elseif ($Action -eq 'restart') {
    & $PSCommandPath -Action stop
    Start-Sleep -Seconds 1
    & $PSCommandPath -Action start
}
else {
    Write-Host 'usage: run.ps1 <start|stop|status|logs|restart> [-Port 8765]'
}
