$logDir = "D:\Coding\dao_vang\scripts\logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Start-Transcript -Path "$logDir\diag_svc.log" -Force

Write-Host "--- Win32_Service info ---"
Get-CimInstance Win32_Service -Filter "Name='Cloudflared'" | Format-List Name,DisplayName,PathName,StartName,State,Status,ExitCode

Write-Host "--- registry ImagePath ---"
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\Cloudflared" | Select-Object ImagePath, ObjectName

Write-Host "--- sc start (raw) ---"
sc.exe start Cloudflared
Start-Sleep -Seconds 3
sc.exe query Cloudflared

Write-Host "--- ACL on system .cloudflared dir ---"
icacls "C:\Windows\System32\config\systemprofile\.cloudflared"

Stop-Transcript
