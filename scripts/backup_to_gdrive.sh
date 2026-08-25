#!/usr/bin/env bash
# ==============================================================================
# ?? DAO VANG — AUTOMATED GOOGLE DRIVE BACKUP & QUANT_DATA SYNC SCRIPT
# ==============================================================================
# Script này du?c thi?t k? d? ch?y d?nh k? (qua Cron job) trên Google Server.
# T? d?ng d?ng b? Database DuckDB, Parquet raw/normalized lên Google Drive:
#   1. DaoVang_Data_Backup: Luu tr? snapshot hàng ngày và live backup c?a GCP
#   2. Quant_Data: T? d?ng b? sung/c?p nh?t d? li?u m?i vào Data Lake Quant
# ==============================================================================

set -euo pipefail

PROJECT_DIR="/home/ubuntu/dao_vang"
DATA_DIR="${PROJECT_DIR}/data"
BACKUP_DIR="${PROJECT_DIR}/backups"
GDRIVE_BACKUP="gdrive:DaoVang_Data_Backup"
GDRIVE_QUANT="gdrive:Quant_Data"
LOG_FILE="${PROJECT_DIR}/data/backup.log"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

echo "========================================================" >> "${LOG_FILE}"
echo "==> [$(date '+%Y-%m-%d %H:%M:%S')] B?t d?u quy trình Backup & Ð?ng b? Quant Data" >> "${LOG_FILE}"

mkdir -p "${BACKUP_DIR}"

# C?p quy?n d?c toàn b? d? li?u (c? file và thu m?c con)
sudo -n chmod -R a+rX "${DATA_DIR}" 2>/dev/null || true

if ! rclone listremotes | grep -q "^gdrive:"; then
    echo "[L?I] Chua c?u hình remote 'gdrive' trong rclone!" >> "${LOG_FILE}"
    echo "Vui lòng ch?y 'rclone config' d? k?t n?i tài kho?n Google Drive." >> "${LOG_FILE}"
    exit 1
fi

# 1. T?o Daily Snapshot DuckDB
if [ -f "${DATA_DIR}/live.duckdb" ]; then
    SNAPSHOT_FILE="${BACKUP_DIR}/live_${TIMESTAMP}.duckdb"
    echo "--> T?o snapshot DuckDB: ${SNAPSHOT_FILE}" >> "${LOG_FILE}"
    cp "${DATA_DIR}/live.duckdb" "${SNAPSHOT_FILE}"
    
    rclone copy "${SNAPSHOT_FILE}" "${GDRIVE_BACKUP}/daily_snapshots/" >> "${LOG_FILE}" 2>&1
    rm -f "${SNAPSHOT_FILE}"
fi

# 2. Ð?ng b? b?n sao luu Live m?i nh?t sang DaoVang_Data_Backup
echo "--> Ðang d?ng b? thu m?c data lên DaoVang_Data_Backup..." >> "${LOG_FILE}"
rclone sync "${DATA_DIR}" "${GDRIVE_BACKUP}/latest_data/" \
    --include "live.duckdb" \
    --include "raw/**" \
    --include "normalized/**" \
    --include "system_data_stats.json" \
    --include "candidate_snapshot.json" \
    --include "tracking_watchlist.json" \
    --transfers 4 \
    --checkers 8 \
    --stats 30s \
    >> "${LOG_FILE}" 2>&1

# 3. T? d?ng B? SUNG d? li?u Parquet m?i nh?t sang Quant_Data (Data Lake Backtest)
echo "--> Ðang t? d?ng b? sung Parquet m?i nh?t sang Quant_Data..." >> "${LOG_FILE}"
rclone copy "${DATA_DIR}/normalized" "${GDRIVE_QUANT}/normalized/" \
    --update \
    --transfers 8 \
    --checkers 16 \
    --stats 30s \
    >> "${LOG_FILE}" 2>&1

# 4. C?p nh?t live.duckdb m?i nh?t sang Quant_Data/databases/
if [ -f "${DATA_DIR}/live.duckdb" ]; then
    echo "--> C?p nh?t live.duckdb sang Quant_Data/databases/..." >> "${LOG_FILE}"
    rclone copy "${DATA_DIR}/live.duckdb" "${GDRIVE_QUANT}/databases/" \
        --update \
        >> "${LOG_FILE}" 2>&1
fi

# 5. D?n d?p snapshot cu hon 30 ngày trên Google Drive
echo "--> D?n d?p snapshot cu hon 30 ngày trên Google Drive..." >> "${LOG_FILE}"
rclone delete "${GDRIVE_BACKUP}/daily_snapshots/" --min-age 30d >> "${LOG_FILE}" 2>&1 || true

echo "==> [$(date '+%Y-%m-%d %H:%M:%S')] Hoàn thành Backup & Ð?ng b? Quant Data thành công!" >> "${LOG_FILE}"
echo "========================================================" >> "${LOG_FILE}"