# VMware VM lifecycle helper for the knowledge-base server VM.
#
#   start | stop | status | wait-ssh | info | install-task | uninstall-task
#
# The VM is a normal VMware Workstation guest (no Hyper-V). Windows has no
# built-in "start this VM at boot", so we register a Scheduled Task that runs
# `vm.ps1 -Action start` at logon (hidden).
#
# NOTE: keep all output strings ASCII-only (Windows PowerShell 5.1 reads
# BOM-less .ps1 as ANSI/GBK, which breaks non-ASCII code).

param(
    [Parameter(Position = 0)]
    [ValidateSet('start', 'stop', 'status', 'wait-ssh', 'info', 'install-task', 'uninstall-task')]
    [string]$Action = 'status',
    [string]$Vmx = '',
    [string]$VmUser = 'awei',
    [int]$SshPort = 22,
    [int]$TimeoutSeconds = 180,
    [string]$TaskName = 'StudyKnowledge-VM-AutoStart'
)

$ErrorActionPreference = 'Continue'

function Find-Vmrun {
    foreach ($c in @(
            'D:\progra\VMware\vmrun.exe',
            'C:\Program Files (x86)\VMware\VMware Workstation\vmrun.exe',
            'C:\Program Files\VMware\VMware Workstation\vmrun.exe',
            'C:\Program Files (x86)\VMware\VMware Player\vmrun.exe')) {
        if (Test-Path $c) { return $c }
    }
    $cmd = Get-Command vmrun.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

function Find-Vmx {
    if ($Vmx -and (Test-Path $Vmx)) { return $Vmx }
    foreach ($root in @('D:\progra\iso', "$env:USERPROFILE\Documents\Virtual Machines", 'D:\', 'E:\')) {
        if (-not (Test-Path $root)) { continue }
        $f = Get-ChildItem -Path $root -Filter '*.vmx' -Recurse -Depth 3 -ErrorAction SilentlyContinue |
             Select-Object -First 1
        if ($f) { return $f.FullName }
    }
    return $null
}

$vmrun = Find-Vmrun
$vmxPath = Find-Vmx

if ($Action -eq 'install-task') {
    if (-not $vmxPath) { Write-Host 'ERROR: no .vmx found'; exit 1 }
    $ps1 = $MyInvocation.MyCommand.Path
    $user = ($env:USERDOMAIN + '\' + $env:USERNAME)
    $act = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
                   $ps1 + '" -Action start -Vmx "' + $vmxPath + '"')
    $trig = New-ScheduledTaskTrigger -AtLogOn
    $set = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -Hidden
    $prin = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    Register-ScheduledTask -TaskName $TaskName -Action $act -Trigger $trig -Settings $set `
        -Principal $prin -Force `
        -Description 'Start the knowledge-base server VM at logon (see web/README.md).' | Out-Null
    $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($t) { Write-Host ('task installed: ' + $TaskName + ' (state=' + $t.State + ')') }
    else { Write-Host 'ERROR: task not created'; exit 1 }
    exit 0
}

if ($Action -eq 'uninstall-task') {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host ('task removed: ' + $TaskName)
    exit 0
}

if (-not $vmrun) { Write-Host 'ERROR: vmrun.exe not found (VMware Workstation installed?)'; exit 1 }
if (-not $vmxPath) { Write-Host 'ERROR: no .vmx found'; exit 1 }

function Get-RunningVm {
    $out = (& $vmrun -T ws list 2>$null | Out-String)
    return ($out -split "`n" | Where-Object { $_ -match '\.vmx' } | ForEach-Object { $_.Trim() })
}

function Test-VmRunning {
    foreach ($v in Get-RunningVm) { if ($v -ieq $vmxPath) { return $true } }
    return $false
}

function Get-VmIp {
    # read the VMware DHCP lease table for the most recent guest address
    $lease = 'C:\ProgramData\VMware\vmnetdhcp.leases'
    if (Test-Path $lease) {
        $txt = Get-Content $lease -Raw -ErrorAction SilentlyContinue
        $m = [regex]::Matches($txt, 'lease\s+(\d+\.\d+\.\d+\.\d+)\s*\{')
        if ($m.Count -gt 0) { return $m[$m.Count - 1].Groups[1].Value }
    }
    return $null
}

function Test-SshPort {
    $ip = Get-VmIp
    if (-not $ip) { return $false }
    $c = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $c.BeginConnect($ip, $SshPort, $null, $null)
        $ok = $iar.AsyncWaitHandle.WaitOne(2000, $false)
        return ($ok -and $c.Connected)
    }
    catch { return $false }
    finally { $c.Close() }
}

switch ($Action) {

    'start' {
        if (Test-VmRunning) {
            Write-Host ('VM already running: ' + $vmxPath)
        }
        else {
            Write-Host ('starting VM (nogui): ' + $vmxPath)
            & $vmrun -T ws start $vmxPath nogui 2>&1 | ForEach-Object { if ("$_".Trim()) { Write-Host ('  ' + "$_".Trim()) } }
            Start-Sleep -Seconds 5
        }
        if (Test-VmRunning) { Write-Host 'VM is running.' } else { Write-Host 'ERROR: VM did not start'; exit 1 }
    }

    'stop' {
        if (-not (Test-VmRunning)) { Write-Host 'VM not running.'; exit 0 }
        Write-Host 'stopping VM (soft)...'
        & $vmrun -T ws stop $vmxPath soft 2>&1 | Out-Null
        Start-Sleep -Seconds 5
        if (Test-VmRunning) {
            Write-Host 'soft stop timed out; trying hard...'
            & $vmrun -T ws stop $vmxPath hard 2>&1 | Out-Null
        }
        Write-Host 'stopped.'
    }

    'status' {
        Write-Host ('vmrun : ' + $vmrun)
        Write-Host ('vmx   : ' + $vmxPath)
        if (Test-VmRunning) { Write-Host 'state : RUNNING' } else { Write-Host 'state : stopped' }
        $t = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
        Write-Host ('autostart task: ' + $(if ($t) { $t.State } else { 'not installed' }))
        Write-Host ('ssh port ' + $SshPort + ' reachable: ' + (Test-SshPort))
    }

    'wait-ssh' {
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        while ((Get-Date) -lt $deadline) {
            if (Test-SshPort) { Write-Host 'SSH is up.'; exit 0 }
            Start-Sleep -Seconds 3
        }
        Write-Host ('ERROR: SSH not reachable within ' + $TimeoutSeconds + 's')
        exit 1
    }

    'info' {
        Write-Host ('vmrun : ' + $vmrun)
        Write-Host ('vmx   : ' + $vmxPath)
        Write-Host ('running VMs:')
        Get-RunningVm | ForEach-Object { Write-Host ('  ' + $_) }
        Write-Host ('tools state : ' + ((& $vmrun -T ws checkToolsState $vmxPath 2>&1 | Out-String).Trim()))
    }
}
