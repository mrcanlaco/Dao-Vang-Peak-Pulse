#!/usr/bin/env bash
# ==============================================================================
# DAO VANG – STORAGE PRUNING & LEAN MAINTENANCE
# ==============================================================================
# Keeps only the latest 3 days of raw JSONL and Parquet on the VPS.
# Historical data is already safely backed up to Google Drive and local Data Lake.
# ==============================================================================

set -euo pipefail

DATA_DIR="/home/ubuntu/dao_vang/data"
RAW_DIR="${DATA_DIR}/raw"
NORM_DIR="${DATA_DIR}/normalized"

echo "==> [$(date '+%Y-%m-%d %H:%M:%S')] Dọn dẹp dữ liệu cũ > 3 ngày trên Server GCP..."

# Xóa các thư mục raw date cũ hơn 3 ngày
if [ -d "${RAW_DIR}" ]; then
    find "${RAW_DIR}" -mindepth 2 -maxdepth 2 -type d -name "date=*" -mtime +3 -exec rm -rf {} + 2>/dev/null || true
fi

# Xóa các thư mục normalized date cũ hơn 3 ngày
if [ -d "${NORM_DIR}" ]; then
    find "${NORM_DIR}" -mindepth 2 -maxdepth 2 -type d -name "date=*" -mtime +3 -exec rm -rf {} + 2>/dev/null || true
fi

echo "==> Hoàn tất tinh gọn dữ liệu!"
