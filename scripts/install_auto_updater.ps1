#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Installs the Dao Vang Auto-Updater as a Windows Scheduled Task.
    Runs at system startup and restarts automatically if terminated.
#>

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "== Dang ky Windows Scheduled Task: DaoVangAutoUpdater ==" -ForegroundColor Cyan

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\service_auto_updater.ps1`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "DaoVangAutoUpdater" -Action $action -Trigger $trigger `
    -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null

try {
    Start-ScheduledTask -TaskName "DaoVangAutoUpdater"
    Write-Host "[OK] DaoVangAutoUpdater task da duoc dang ky va khoi chay thanh cong!" -ForegroundColor Green
} catch {
    Write-Host "[WARN] Da dang ky task nhung chua khoi dong duoc ngay: $_" -ForegroundColor Yellow
}

Write-Host "`nDa hoan tat. He thong se tu dong kiem tra ban cap nhat moi tren GitHub dinh ky 24/7." -ForegroundColor Cyan
