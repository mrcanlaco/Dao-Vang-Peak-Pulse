# PowerShell script to sync/merge new data from DaoVang_Data_Backup to Quant_Data
$gdriveRoot = "I:\My Drive"
$source = "$gdriveRoot\DaoVang_Data_Backup\latest_data"
$dest = "$gdriveRoot\Quant_Data"

Write-Host "=========================================================" -ForegroundColor Cyan
Write-Host "   DONG BO DU LIEU MOI TU DAO VANG SANG QUANT DATA LAKE   " -ForegroundColor Cyan
Write-Host "=========================================================" -ForegroundColor Cyan

if (-not (Test-Path $source)) {
    Write-Host "[LOI] Khong tim thay thu muc nguon: $source" -ForegroundColor Red
    exit 1
}

# S? d?ng tham s? an toàn cho Cloud Virtual Drive (Google Drive):
# /FFT: tuong thích timestamp FAT/Cloud
# /MT:2: gi?i h?n lu?ng tránh ngh?n I/O Google Drive
# /R:3 /W:2: t? d?ng th? l?i 3 l?n n?u m?ng Google Drive có d? tr?
Write-Host "[1/2] Dang bo sung Parquet moi nhat..." -ForegroundColor Yellow
robocopy "$source\normalized" "$dest\normalized" /E /XO /FFT /R:3 /W:2 /NP /MT:2 /NFL /NDL

Write-Host "[2/2] Dang cap nhat live.duckdb..." -ForegroundColor Yellow
robocopy "$source" "$dest\databases" "live.duckdb" /XO /FFT /R:3 /W:2 /NP /NFL /NDL

Write-Host "`nHOAN TAT DONG BO! Quant_Data da co du lieu moi nhat san sang su dung!" -ForegroundColor Green