@echo off
echo ==========================================
echo STARTING DAO VANG SCANNER - DEV SHADOW
echo DATA: data
echo ==========================================
set PYTHONPATH=src
set DAO_VANG_PATHS__DATA_DIR=data
set DAO_VANG_PATHS__RAW_DIR=data/raw
set DAO_VANG_PATHS__NORMALIZED_DIR=data/normalized
set DAO_VANG_SCANNER__DB_PATH=data/dev.duckdb
set DAO_VANG_SCANNER__FROZEN_MODEL_ID=frozen_20260811_082824_96df7ec9
set DAO_VANG_SCANNER__OPERATING_MODE=shadow
set DAO_VANG_SCORING__ALERT_SCORE_THRESHOLD=40
if exist .venv_dev\Scripts\python.exe (
    set "PYTHON_EXE=.venv_dev\Scripts\python.exe"
) else (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
)

%PYTHON_EXE% -m dao_vang scanner start
pause
