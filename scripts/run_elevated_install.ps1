$logDir = "D:\Coding\dao_vang\scripts\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Transcript -Path "$logDir\install_autostart.log" -Force
try {
    & "D:\Coding\dao_vang\scripts\install_autostart.ps1"
} catch {
    Write-Host "ERROR: $_"
}
Stop-Transcript
