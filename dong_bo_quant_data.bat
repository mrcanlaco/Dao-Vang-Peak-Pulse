@echo off
title Dong Bo Du Lieu Quant Data
echo =========================================================
echo    DANG DONG BO DU LIEU TU DAO VANG SANG QUANT DATA
echo =========================================================
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\sync_quant_data.ps1"
echo =========================================================
pause