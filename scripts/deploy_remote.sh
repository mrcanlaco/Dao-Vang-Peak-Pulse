#!/bin/bash
set -e

echo === [1/5] Kéo code mới nhất từ Git ===
git merge --abort 2>/dev/null || true
git reset --hard HEAD
git clean -fd
git fetch origin main --prune
git reset --hard origin/main

echo === [2/5] Xóa file lock cũ (nếu có kẹt do crash trước đó) ===
rm -f data/web.lock data_live/web.lock data/scanner.lock data_live/scanner.lock

echo === [3/5] Build lại Docker containers ===
docker compose build

echo === [4/5] Khởi động lại các container ngầm ===
docker compose up -d

echo === [5/5] Kiểm tra trạng thái dịch vụ ===
sleep 3
docker compose ps
echo "
echo === Kiểm tra endpoint HTTP API ===
curl -s -o /dev/null -w HTTP Status: %{http_code}\n http://localhost:8000/api/status || true
echo === Hoàn tất cập nhật ===
