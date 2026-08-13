# DAO VANG — Docker Deployment Guide

Run the 24/7 scanner and interactive Web UI in Docker containers.

---

## 1. Prerequisites

- **Docker** 20.10+ ([Install Docker](https://docs.docker.com/get-docker/))
- **Docker Compose** v2+ (bundled with Docker Desktop)
- **Frozen ML Model** (see Section 3 below if not already created)

---

## 2. Quick Start (3 Steps)

### Step 1: Create the Environment File

```powershell
# Windows PowerShell
Copy-Item .env.docker.example .env.docker
notepad .env.docker
```

```bash
# Linux / macOS
cp .env.docker.example .env.docker
nano .env.docker
```

Configure the following essential variables:
- `DAO_VANG_SCANNER__FROZEN_MODEL_ID` — **REQUIRED** (see Section 3)
- `DAO_VANG_TELEGRAM__BOT_TOKEN` + `DAO_VANG_TELEGRAM__CHAT_ID` — to receive Telegram alerts
- `DAO_VANG_TELEGRAM__LANGUAGE=en` — to receive alerts in English (`en` or `vi`)

### Step 2: Build the Docker Image

```powershell
docker compose build
```

*Initial build takes ~3–5 minutes (downloading Python base image and installing dependencies). Subsequent builds take ~30s with caching.*

### Step 3: Run 24/7 Daemon

```powershell
docker compose up -d
```

Check status and logs:
```powershell
docker compose ps           # view running container status
docker compose logs -f      # follow real-time logs
docker compose logs scanner  # scanner logs only
docker compose logs web      # web API / UI logs only
```

Open Web Dashboard: **`http://localhost:8501`** (or your server domain/IP).

---

## 3. Frozen Model Setup

The scanner requires a frozen, hash-verified ML model bundle.

### Option A: Use an Existing Model Bundle (Fastest)

Check available models in `artifacts/frozen_models/`:
```powershell
ls artifacts/frozen_models/
# e.g., frozen_20260803_160757_cf749fbe
```

Set the ID in `.env.docker`:
```env
DAO_VANG_SCANNER__FROZEN_MODEL_ID=frozen_20260803_160757_cf749fbe
```

### Option B: Train a New Model inside Docker

```powershell
# Run temporary container to collect data & train
docker compose run --rm web dao-vang data collect --start-timestamp 1754000000 --end-timestamp 1754300000
docker compose run --rm web dao-vang labels generate --db-path data/dev.duckdb --source-table raw_timeline
docker compose run --rm web dao-vang features generate --db-path data/dev.duckdb --source-table raw_timeline --target-table feature_results
docker compose run --rm web dao-vang experiment freeze --db-path data/dev.duckdb

# List all frozen model IDs
docker compose run --rm web dao-vang experiment frozen-list
```

---

## 4. Maintenance & Management

### View Running Status
```powershell
docker compose ps
docker compose logs --tail 50 scanner
docker compose logs -f scanner
```

### Inspect Database inside Container
```powershell
docker compose exec web python -c "
import duckdb
conn = duckdb.connect('data/scanner.duckdb', read_only=True)
print(conn.execute('SELECT COUNT(*) FROM feature_results').fetchone())
"
```

### Restart / Stop Services
```powershell
docker compose restart scanner   # Restart scanner only
docker compose down             # Gracefully stop all services
```

---

## 5. Security Best Practices

- Never commit `.env.docker` to Git (it is blocked by `.gitignore`).
- Use Docker secrets or environment variables for token injection on production VPS.
