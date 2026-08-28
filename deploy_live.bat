@echo off
setlocal enabledelayedexpansion
title DAO VANG - DEPLOY TO GOOGLE CLOUD (LIVE)
cls

echo ================================================================
echo           DAO VANG - DEPLOY TO GOOGLE CLOUD (LIVE SERVER)
echo ================================================================
echo  * Server IP : 136.110.29.208
echo  * Live URL  : https://daovang.comaygiauco.com
echo  * Direct    : http://136.110.29.208:8000
echo ================================================================
echo.

cd /d "%~dp0"

if exist .venv_dev\Scripts\python.exe (
    set "PYTHON_EXE=.venv_dev\Scripts\python.exe"
) else if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    set "PYTHON_EXE=python"
)

echo Chon che do trien khai:
echo   [1] Commit thay doi moi + Push GitHub + Deploy Google Cloud (Khuyen nghi)
echo   [2] Chi Deploy len Google Cloud (Lay ban moi nhat tren GitHub main)
echo   [3] Huy bo
echo.
set /p CHOICE="Nhap lua chon (1/2/3) [Mac dinh: 1]: "
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="3" (
    echo [INFO] Da huy bo thao tac.
    goto END
)

if "%CHOICE%"=="1" (
    echo.
    echo ================================================================
    echo [BUOC 1/2] COMMIT VA PUSH MA NGUON LEN GITHUB
    echo ================================================================
    git status --short
    echo.
    set /p COMMIT_MSG="Nhap thong diep commit (Enter de dung mac dinh): "
    if "!COMMIT_MSG!"=="" set COMMIT_MSG=chore: update dao vang release

    git add -A
    git commit -m "!COMMIT_MSG!"
    echo.
    echo [INFO] Dang push len GitHub origin/main ...
    git push origin main
    if %errorlevel% neq 0 (
        echo [ERROR] Git push that bai! Vui long kiem tra xung dot hoac mang.
        pause
        goto END
    )
    echo [OK] Push len GitHub thanh cong!
)

echo.
echo ================================================================
echo [BUOC 2/2] KICH HOAT TRIEN KHAI VA DOCKER BUILD TREN GOOGLE CLOUD
echo ================================================================
echo.
%PYTHON_EXE% scripts/deploy_google_server.py

:END
echo.
echo ================================================================
echo [INFO] Nhan phim bat ky de thoat...
echo ================================================================
pause >nul
