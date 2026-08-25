@echo off
>nul 2>&1 "%SYSTEMROOT%\system32\cacls.exe" "%SYSTEMROOT%\system32\config\system"
if %errorlevel% NEQ 0 (
    echo Requesting administrative privileges...
    powershell -Command "Start-Process cmd -ArgumentList \"/c `\"%~dpnx0`\"\" -Verb RunAs"
    exit /b
)

echo ====================================================
echo  DANG TAT UNG DUNG DAO VANG TREN SERVER / LAPTOP MSI
echo ====================================================

echo [1/4] Dung Scheduled Tasks...
schtasks /end /tn "DaoVangScanner" >nul 2>&1
schtasks /end /tn "DaoVangWebUI" >nul 2>&1
schtasks /end /tn "DaoVangAutoUpdater" >nul 2>&1
schtasks /delete /tn "DaoVangScanner" /f >nul 2>&1
schtasks /delete /tn "DaoVangWebUI" /f >nul 2>&1
schtasks /delete /tn "DaoVangAutoUpdater" /f >nul 2>&1

echo [2/4] Kill tat ca tien trinh Dao Vang...
taskkill /F /IM dao-vang.exe >nul 2>&1
taskkill /F /IM dao-vang-ui.exe >nul 2>&1
taskkill /F /PID 24184 /PID 5064 /PID 24332 /PID 24368 /PID 14904 /PID 24352 /PID 3852 /PID 3764 >nul 2>&1

echo [3/4] Cap nhat Cloudflare Tunnel sang Google Cloud (136.110.29.208:8000)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$sysCfg = 'C:\Windows\System32\config\systemprofile\.cloudflared\config.yml'; if (Test-Path $sysCfg) { $c = Get-Content $sysCfg -Raw; $c = $c -replace 'http://127.0.0.1:8000', 'http://136.110.29.208:8000'; Set-Content -Path $sysCfg -Value $c -NoNewline }"
net stop Cloudflared >nul 2>&1
net start Cloudflared >nul 2>&1

echo [4/4] Don dep file .venv con lai...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -Path 'D:\Coding\dao_vang\.venv' -Recurse -Force -ErrorAction SilentlyContinue"

echo ====================================================
echo  HOAN TAT! DA TAT VA GIAI PHONG TOAN BO TAI NGUYEN!
echo ====================================================
pause
