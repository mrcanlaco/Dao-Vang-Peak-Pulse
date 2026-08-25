#Requires -RunAsAdministrator
<#
.SYNOPSIS
    Installs auto-start + auto-restart for:
      1. cloudflared tunnel (trade.comaygiauco.com) as a Windows Service
      2. Scanner daemon as a Scheduled Task (runs at startup, restarts on crash)
      3. Streamlit web UI as a Scheduled Task (runs at startup, restarts on crash)
#>

$ErrorActionPreference = "Stop"
$root = "D:\Coding\dao_vang"

Write-Host "== 1. cloudflared Windows Service ==" -ForegroundColor Cyan

$userCloudflaredDir = "$env:USERPROFILE\.cloudflared"
$systemCloudflaredDir = "C:\Windows\System32\config\systemprofile\.cloudflared"

New-Item -ItemType Directory -Force -Path $systemCloudflaredDir | Out-Null
Get-ChildItem "$userCloudflaredDir\*.json" | ForEach-Object {
    Copy-Item $_.FullName "$systemCloudflaredDir\$($_.Name)" -Force
}
if (Test-Path "$userCloudflaredDir\cert.pem") {
    Copy-Item "$userCloudflaredDir\cert.pem" "$systemCloudflaredDir\cert.pem" -Force
}

# The user's config.yml references credentials-file under %USERPROFILE%,
# which the SYSTEM account (used by the Windows service) cannot resolve.
# Rewrite that path to the copy under the SYSTEM profile.
$configContent = Get-Content "$userCloudflaredDir\config.yml" -Raw
$configContent = $configContent -replace [regex]::Escape($userCloudflaredDir), $systemCloudflaredDir
Set-Content -Path "$systemCloudflaredDir\config.yml" -Value $configContent -NoNewline
Write-Host "Copied tunnel config + credentials to SYSTEM profile (path rewritten)." -ForegroundColor Green
Write-Host "--- system config.yml ---" -ForegroundColor DarkGray
Get-Content "$systemCloudflaredDir\config.yml" | Write-Host

$svc = Get-Service -Name "Cloudflared" -ErrorAction SilentlyContinue
if (-not $svc) {
    & "C:\Program Files (x86)\cloudflared\cloudflared.exe" service install
    Start-Sleep -Seconds 2
}

# The service's default ImagePath just launches cloudflared.exe with no
# arguments. Under the LocalSystem account it cannot reliably resolve
# %USERPROFILE%\.cloudflared\config.yml, so the process aborts immediately
# (Win32 exit 1067). Point it explicitly at the SYSTEM-profile config.
$exePath = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
$cfgPath = "$systemCloudflaredDir\config.yml"
$imagePath = "`"$exePath`" --config `"$cfgPath`" tunnel run"
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Services\Cloudflared" -Name "ImagePath" -Value $imagePath
Write-Host "Rewrote service ImagePath: $imagePath" -ForegroundColor DarkGray

Set-Service -Name "Cloudflared" -StartupType Automatic
try {
    Restart-Service -Name "Cloudflared" -Force -ErrorAction Stop
} catch {
    Write-Host "Service failed to start: $_" -ForegroundColor Red
    Write-Host "--- recent Cloudflared event log entries ---" -ForegroundColor Yellow
    Get-WinEvent -LogName Application -MaxEvents 20 -ErrorAction SilentlyContinue |
        Where-Object { $_.ProviderName -like "*Cloudflared*" -or $_.Message -like "*cloudflared*" } |
        Select-Object -First 8 TimeCreated, Message | Format-List
}
Write-Host "Cloudflared service status:" -ForegroundColor Green
Get-Service -Name "Cloudflared" | Format-Table -AutoSize

Write-Host "`n== 2. Scheduled Task: DaoVangScanner ==" -ForegroundColor Cyan
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\service_scanner_loop.ps1`""
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "DaoVangScanner" -Action $action -Trigger $trigger `
    -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "DaoVangScanner"
Write-Host "DaoVangScanner task registered + started." -ForegroundColor Green

Write-Host "`n== 3. Scheduled Task: DaoVangWebUI ==" -ForegroundColor Cyan
$action2 = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\service_web_live_loop.ps1`""
Register-ScheduledTask -TaskName "DaoVangWebUI" -Action $action2 -Trigger $trigger `
    -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "DaoVangWebUI"
Write-Host "DaoVangWebUI task registered + started." -ForegroundColor Green

Write-Host "`n== 4. Scheduled Task: DaoVangAutoUpdater ==" -ForegroundColor Cyan
$action3 = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$root\scripts\service_auto_updater.ps1`""
Register-ScheduledTask -TaskName "DaoVangAutoUpdater" -Action $action3 -Trigger $trigger `
    -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "DaoVangAutoUpdater"
Write-Host "DaoVangAutoUpdater task registered + started." -ForegroundColor Green

Write-Host "`nDone. All tasks + the Cloudflared service will auto-start on boot and auto-restart on crash." -ForegroundColor Cyan
