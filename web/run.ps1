# 启动/停止本地知识库问答服务
param(
    [ValidateSet('start','stop','status','logs','restart')]
    [string]$Action = 'start',
    [int]$Port = 8765,
    [string]$HostAddr = '127.0.0.1'
)
$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$rt   = Join-Path $here '.runtime'
$pidFile = Join-Path $rt 'server.pid'
$logFile = Join-Path $rt 'server.log'
New-Item -ItemType Directory -Force -Path $rt | Out-Null

# 定位 localbrain 的 Python（优先工具环境）
$py = "$env:APPDATA\uv\tools\localbrain\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "$env:USERPROFILE\.local\share\uv\tools\localbrain\Scripts\python.exe" }
if (-not (Test-Path $py)) { $py = (Get-Command python -ErrorAction SilentlyContinue).Source }
if (-not $py) { Write-Error '找不到 Python（需要安装了 localbrain 的环境）。'; exit 1 }
Write-Output "使用 Python: $py"

function Get-Pid { if (Test-Path $pidFile) { [int](Get-Content $pidFile -Raw).Trim() } else { 0 } }
function Is-Running {
    $p = Get-Pid
    if ($p -gt 0) { $proc = Get-Process -Id $p -ErrorAction SilentlyContinue; return ($null -ne $proc) }
    return $false
}

switch ($Action) {
    'start' {
        if (Is-Running) { Write-Output "服务已在运行 (PID $(Get-Pid)): http://$HostAddr`:$Port"; break }
        $env:PORT = "$Port"; $env:HOST = $HostAddr
        $p = Start-Process -FilePath $py -ArgumentList @('server.py') -WorkingDirectory $here -WindowStyle Hidden -RedirectStandardOutput $logFile -RedirectStandardError (Join-Path $rt 'server.err.log') -PassThru
        Set-Content -Path $pidFile -Value $p.Id
        Start-Sleep -Seconds 3
        Write-Output "已启动 (PID $($p.Id)): http://$HostAddr`:$Port  （日志: $logFile）"
        try { (Invoke-RestMethod -Uri "http://$HostAddr`:$Port/api/status" -TimeoutSec 5) | Out-Null; Write-Output '健康检查通过。' } catch { Write-Output '服务启动中，稍后刷新页面即可。若失败请看日志。' }
    }
    'stop' {
        if (Is-Running) { Stop-Process -Id (Get-Pid) -Force; Write-Output "已停止 PID $(Get-Pid)" } else { Write-Output '服务未在运行' }
        Remove-Item $pidFile -ErrorAction SilentlyContinue
    }
    'status' {
        if (Is-Running) { Write-Output "运行中 (PID $(Get-Pid)): http://$HostAddr`:$Port" } else { Write-Output '未运行' }
    }
    'logs' {
        if (Test-Path $logFile) { Get-Content $logFile -Tail 40 } else { Write-Output '暂无日志' }
    }
    'restart' { & $MyInvocation.MyCommand.Path -Action stop -Port $Port; Start-Sleep 1; & $MyInvocation.MyCommand.Path -Action start -Port $Port }
}
