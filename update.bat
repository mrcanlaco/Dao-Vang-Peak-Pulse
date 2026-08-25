@echo off
setlocal enabledelayedexpansion
title DAO VANG PEAKPULSE - ONE CLICK UPDATER

echo ================================================================
echo          DAO VANG PEAKPULSE - ONE-CLICK SYSTEM UPDATER
echo ================================================================
echo.
echo Checking Git, Python and remote GitHub updates...
echo.

cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update.ps1"

echo.
echo ================================================================
echo [INFO] Update process finished. Press any key to close this window.
echo ================================================================
pause >nul
