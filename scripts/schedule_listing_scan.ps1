# Register a Windows Scheduled Task that runs the Binance listing scan once per day.
#
# Usage (run as the current user, no admin needed):
#   powershell -ExecutionPolicy Bypass -File scripts\schedule_listing_scan.ps1
#
# To remove the task:
#   Unregister-ScheduledTask -TaskName "DaoVang_ListingScan" -Confirm:$false

[CmdletBinding()]
param(
    [string]$TaskName = "DaoVang_ListingScan",
    # Time of day to run (24h, local time). Default 09:00.
    [string]$StartTime = "09:00",
    # Project root (auto-detected if not provided).
    [string]$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
)

$ErrorActionPreference = "Stop"

# Locate the venv python that has dao-vang installed.
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "venv python not found at $venvPython. Run `uv sync` first."
}

$daoVangExe = Join-Path $ProjectRoot ".venv\Scripts\dao-vang.exe"
if (-not (Test-Path $daoVangExe)) {
    throw "dao-vang CLI not found at $daoVangExe. Run `uv sync` first."
}

# Action: cd into project root, run the listing scan, log output to a file.
$logFile = Join-Path $ProjectRoot "data\listing_scan.log"
$action = New-ScheduledTaskAction `
    -Execute $daoVangExe `
    -Argument "data listing-scan" `
    -WorkingDirectory $ProjectRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $StartTime

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Dao Vang: daily Binance Spot/Futures listing scan -> data/binance_listing_history.json" `
    -Force | Out-Null

Write-Host "Scheduled task '$TaskName' registered." -ForegroundColor Green
Write-Host "  Runs daily at $StartTime (local time)"
Write-Host "  Command:  dao-vang data listing-scan"
Write-Host "  Working dir: $ProjectRoot"
Write-Host ""
Write-Host "To run now:    $daoVangExe data listing-scan"
Write-Host "To view log:   Get-Content $logFile"
Write-Host "To remove:     Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
