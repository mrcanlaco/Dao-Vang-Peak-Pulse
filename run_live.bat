@echo off
echo ==========================================
echo STARTING DAO VANG - LIVE ENVIRONMENT
echo PORT: 8001
echo DATA: data_live
echo ==========================================
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\service_web_live_loop.ps1"
