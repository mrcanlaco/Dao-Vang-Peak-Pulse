@echo off
echo ==========================================
echo STARTING DAO VANG SCANNER - LIVE ENVIRONMENT
echo DATA: data_live
echo ==========================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\service_scanner_loop.ps1"
