# Đảo Vàng — Hướng dẫn Docker

Chạy bộ quét 24/7 + web UI trong Docker container.

## 1. Yêu cầu

- **Docker** 20.10+ (cài: https://docs.docker.com/get-docker/)
- **Docker Compose** v2+ (đã kèm Docker Desktop)
- **Frozen model** đã có (xem mục 3 bên dưới nếu chưa có)

## 2. Cài đặt nhanh (3 bước)

### Bước 1: Tạo file env

```powershell
# Windows PowerShell
Copy-Item .env.docker.example .env.docker
notepad .env.docker
```

```bash
# Linux/Mac
cp .env.docker.example .env.docker
nano .env.docker
```

Sửa các giá trị:
- `DAO_VANG_SCANNER__FROZEN_MODEL_ID` — **BẮT BUỘC** (xem mục 3)
- `DAO_VANG_TELEGRAM__BOT_TOKEN` + `DAO_VANG_TELEGRAM__CHAT_ID` — nếu muốn nhận alert Telegram

### Bước 2: Build image

```powershell
docker compose build
```

Lần đầu mất ~3-5 phút (tải Python image + cài dependencies). Lần sau chỉ ~30s (cache).

### Bước 3: Chạy 24/7

```powershell
docker compose up -d
```

Kiểm tra:
```powershell
docker compose ps          # xem trạng thái
docker compose logs -f     # xem log real-time
docker compose logs scanner # chỉ log scanner
docker compose logs web     # chỉ log web
```

Mở web UI: http://localhost:8501

## 3. Frozen model — nếu chưa có

Frozen model là AI đã huấn luyện + đóng băng, cần thiết cho scanner. Có 2 cách:

### Cách A: Dùng model đã có (nhanh nhất)

Kiểm tra model có sẵn trong `artifacts/frozen_models/`:
```powershell
ls artifacts/frozen_models/
# → frozen_20260803_160757_cf749fbe
```

Copy ID vào `.env.docker`:
```
DAO_VANG_SCANNER__FROZEN_MODEL_ID=frozen_20260803_160757_cf749fbe
```

### Cách B: Train model mới trong Docker

```powershell
# Chạy container tạm để collect data + train
docker compose run --rm web dao-vang data collect --start-timestamp 1754000000 --end-timestamp 1754300000
docker compose run --rm web dao-vang labels generate --db-path data/dev.duckdb --source-table raw_timeline
docker compose run --rm web dao-vang features generate --db-path data/dev.duckdb --source-table raw_timeline --target-table feature_results
docker compose run --rm web dao-vang experiment freeze --db-path data/dev.duckdb

# Xem model ID
docker compose run --rm web dao-vang experiment frozen-list
```

## 4. Quản lý

### Xem trạng thái
```powershell
docker compose ps                    # containers đang chạy
docker compose logs --tail 50 scanner # 50 dòng log gần nhất
docker compose logs -f scanner        # follow log real-time
```

### Vào container xem DB
```powershell
docker compose exec web python -c "
import duckdb
conn = duckdb.connect('data/scanner.duckdb', read_only=True)
print(conn.execute('SELECT COUNT(*) FROM feature_results').fetchone())
print(conn.execute('SELECT symbol, COUNT(*) FROM feature_results GROUP BY symbol ORDER BY COUNT(*) DESC LIMIT 10').fetchall())
"
```

### Kiểm tra scanner status qua CLI
```powershell
docker compose exec web dao-vang scanner status
docker compose exec web dao-vang scanner history --days 7
docker compose exec web dao-vang watchlist list
```

### Quản lý watchlist
```powershell
docker compose exec web dao-vang watchlist add EULUSDT
docker compose exec web dao-vang watchlist remove DOGEUSDT
docker compose exec web dao-vang watchlist list
```

### Xem trước danh sách quét
```powershell
docker compose exec web dao-vang scanner scan-list
docker compose exec web dao-vang scanner scan-list --mode all
```

## 5. Dừng / khởi động lại

```powershell
# Dừng (giữ data)
docker compose down

# Khởi động lại
docker compose up -d

# Dừng + XÓA data (cẩn thận!)
docker compose down -v
```

## 6. Cấu hình

### Đổi scan mode / số coin

Sửa trong `docker-compose.yml` phần `environment`:
```yaml
- DAO_VANG_SCANNER__SCAN_MODE=all        # gainers|losers|volume|volatile|all
- DAO_VANG_SCANNER__MAX_COINS=100
- DAO_VANG_SCANNER__POLL_INTERVAL_MINUTES=10
```

Hoặc sửa trong `.env.docker` (override cả compose):
```
DAO_VANG_SCANNER__SCAN_MODE=all
DAO_VANG_SCANNER__MAX_COINS=100
```

Sau đó:
```powershell
docker compose up -d  # tự recreate container với config mới
```

### Bật CoinGecko cross-reference
```
DAO_VANG_COINGECKO__ENABLED=true
```

### Market cap từ Binance Agent OS

Market cap trên dashboard dùng Binance Agent OS làm nguồn chuẩn. Dữ liệu
được truy vấn khi mở chi tiết token và cache mặc định 15 phút:

```
DAO_VANG_BINANCE_AGENT_OS__ENABLED=true
DAO_VANG_BINANCE_AGENT_OS__CACHE_MINUTES=15
```

## 7. Volumes

Docker compose tạo 2 named volume:

| Volume | Mount path | Chứa gì |
|---|---|---|
| `dao_vang_data` | `/app/data` | DuckDB, parquet, watchlist.json, heartbeat |
| `dao_vang_artifacts` | `/app/artifacts` | Frozen models, experiment JSON |

Data tồn tại độc lập với container — `docker compose down` không xóa data. Chỉ `docker compose down -v` mới xóa.

### Backup data
```powershell
docker run --rm -v dao_vang_data:/data -v ${PWD}:/backup alpine tar czf /backup/dao_vang_data_backup.tar.gz /data
```

### Restore data
```powershell
docker run --rm -v dao_vang_data:/data -v ${PWD}:/backup alpine tar xzf /backup/dao_vang_data_backup.tar.gz /data
```

## 8. Troubleshooting

### Scanner không chạy — "frozen_model_id not set"
→ Kiểm tra `.env.docker` có `DAO_VANG_SCANNER__FROZEN_MODEL_ID=frozen_...` và file model tồn tại trong volume.

### Web UI không mở được
```powershell
docker compose logs web
docker compose restart web
```

### Scanner báo "No symbols"
→ Binance API có thể bị chặn IP. Kiểm tra:
```powershell
docker compose exec scanner curl -s https://fapi.binance.com/fapi/v1/ping
```

### Log quá lớn
Docker compose đã giới hạn log: scanner 50MB×5 files, web 20MB×3 files. Nếu vẫn quá lớn:
```powershell
docker compose logs --tail 100 scanner > scanner_log.txt
docker system prune -f  # xóa log cũ
```

### Update code
```powershell
git pull
docker compose build
docker compose up -d
```

## 9. Kiến trúc

```
┌─────────────────────────────────────────────────┐
│  Docker Host                                     │
│                                                  │
│  ┌──────────────────┐  ┌──────────────────┐     │
│  │  scanner          │  │  web (Streamlit) │     │
│  │  dao-vang scanner │  │  port 8501       │     │
│  │  start            │  │                  │     │
│  │                   │  │  → Bảng xếp hạng │     │
│  │  Mỗi 5 phút:      │  │  → Phân tích coin│     │
│  │  1. Quét Binance  │  │  → Cảnh báo      │     │
│  │  2. Pump filter   │  │  → Backtest      │     │
│  │  3. Score 8 tín hiệu│ │                  │     │
│  │  4. Telegram alert│  │                  │     │
│  └────────┬─────────┘  └────────┬─────────┘     │
│           │                      │               │
│           └──────────┬───────────┘               │
│                      │                           │
│           ┌──────────▼──────────┐                │
│           │  Volume: dao_vang_data│               │
│           │  - scanner.duckdb    │               │
│           │  - watchlist.json    │               │
│           │  - heartbeat.json    │               │
│           └─────────────────────┘                │
│           ┌─────────────────────┐                │
│           │  Volume: dao_vang_artifacts│          │
│           │  - frozen_models/   │                │
│           └─────────────────────┘                │
└──────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
   Binance API              Telegram API
   (fapi.binance.com)       (api.telegram.org)
```

Scanner và web chia sẻ cùng volume `dao_vang_data` — web UI đọc DuckDB mà scanner ghi vào, nên bảng xếp hạng cập nhật real-time.
