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
    # 端口自清理：若端口被残留的本服务进程占用（pid 文件之外的旧进程），先结束它
    try {
        $holder = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($holder -and $holder.OwningProcess -ne $currentPid) {
            $hp = $holder.OwningProcess
            $pi = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $hp) -ErrorAction SilentlyContinue
            if ($pi -and $pi.CommandLine -like '*server.py*') {
                Stop-Process -Id $hp -Force -ErrorAction SilentlyContinue
                Write-Host ('cleaned stale server on port ' + $Port + ' (old PID ' + $hp + ')')
                Start-Sleep -Seconds 1
            }
        }
    }
    catch { }
    if (Test-Running) {
        Write-Host ('already running (PID ' + $currentPid + '): ' + $url)
    }
    else {
        $env:PORT = [string]$Port
        $env:HOST = $HostAddr
        $p = Start-Process -FilePath $py -ArgumentList @('server.py') -WorkingDirectory $here -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError $errFile -PassThru
        Set-Content -Path $pidFile -Value $p.Id
        Start-Sleep -Seconds 3
        # uv 的 Scripts\python.exe 是包装器，会再拉起真正的解释器当监听者；
        # pid 文件应记录真实监听进程，否则 stop 杀不掉、旧进程变“幽灵”占端口
        try {
            $real = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($real -and $real.OwningProcess -ne $p.Id) {
                Set-Content -Path $pidFile -Value $real.OwningProcess
                Write-Host ('real listener PID ' + $real.OwningProcess + ' recorded (uv wrapper)')
            }
        }
        catch { }
        Write-Host ('started (PID ' + $p.Id + '): ' + $url)
        # health check via curl.exe: Invoke-RestMethod tries to negotiate the
        # 401 challenge (WWW-Authenticate) and can hang instead of failing fast
        $curl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($curl) {
            $hargs = @('-s', '-o', 'NUL', '-w', '%{http_code}', '--max-time', '6', ($url + '/api/status'))
            if ($env:KB_ACCESS_TOKEN) { $hargs += @('-H', ('X-KB-Token: ' + $env:KB_ACCESS_TOKEN)) }
            # the uv wrapper spawns the real interpreter, so give it a few tries
            $code = '000'
            foreach ($try in 1..8) {
                $code = (& curl.exe @hargs 2>$null | Out-String).Trim()
                if ($code -eq '200' -or $code -eq '401') { break }
                Start-Sleep -Seconds 2
            }
            if ($code -eq '200') { Write-Host 'health check OK.' }
            elseif ($code -eq '401') {
                Write-Host 'health check: 401 - service is up but auth does not accept this token.' -ForegroundColor Yellow
            }
            else {
                Write-Host ('health check returned ' + $code + '; if it stays unavailable, check logs:')
                Write-Host ('  ' + $logFile)
                Write-Host ('  ' + $errFile)
            }
        }
        else {
            Write-Host 'curl.exe not found; skipping health check.'
        }
        if ($env:KB_ACCESS_TOKEN) {
            Write-Host '[auth] token enabled (from KB_ACCESS_TOKEN).'
        }
        else {
            Write-Host '[auth] KB_ACCESS_TOKEN not set - local use only; set it before exposing via tunnel.' -ForegroundColor Yellow
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
