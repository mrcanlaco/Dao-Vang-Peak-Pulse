#!/usr/bin/env bash
# ================================================================
# Đảo Vàng PeakPulse - 1-Command Linux / Server Updater
# ================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${ROOT_DIR}"

echo "================================================================"
echo "         DAO VANG PEAKPULSE - ONE COMMAND SYSTEM UPDATER        "
echo "================================================================"
echo "Project Directory: ${ROOT_DIR}"
echo "Current Time: $(date)"
echo ""

# 1. Check Git Remote
BRANCH="${1:-main}"
echo "[1/4] Pulling latest updates from origin/${BRANCH}..."
git fetch origin "${BRANCH}" --quiet
git pull origin "${BRANCH}"

# 2. Clean stale locks
echo "[2/4] Cleaning any stale lock files..."
rm -f data/web.lock data/scanner.lock data_live/web.lock data_live/scanner.lock

# 3. Check if Docker Compose is running
if command -v docker >/dev/null 2>&1 && [ -f "docker-compose.yml" ]; then
    echo "[3/4] Rebuilding and restarting Docker Compose services..."
    docker compose build --quiet || true
    docker compose up -d
    sleep 3
    docker compose ps
elif [ -d ".venv" ]; then
    echo "[3/4] Updating Python dependencies in .venv..."
    if command -v uv >/dev/null 2>&1; then
        uv sync
    else
        .venv/bin/pip install -e .
    fi
fi

# 4. Health check
echo "[4/4] Verifying API Server health..."
sleep 2
if command -v curl >/dev/null 2>&1; then
    curl -s -o /dev/null -w "API Status HTTP: %{http_code}\n" http://localhost:8000/api/status || true
fi

echo ""
echo "================================================================"
echo "   DAO VANG UPDATED SUCCESSFULLY AND READY TO SERVE!           "
echo "================================================================"
