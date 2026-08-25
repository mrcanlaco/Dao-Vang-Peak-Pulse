# Môi Trường Triển Khai & Vận Hành Hệ Thống Đảo Vàng

## 1. Phân Định Kiến Trúc Môi Trường (System Architecture & Roles)

| Môi Trường | Thiết Bị / Máy Chủ | Vai Trò & Chức Năng | Hệ Điều Hành / Công Nghệ | Phương Thức Vận Hành |
|---|---|---|---|---|
| **💻 DEV (Phát triển)** | Máy bàn (Local Desktop) | Phát triển tính năng mới, debug, viết code, kiểm thử unit test, build frontend React/Vite | Windows | Python (.venv), Vite dev, Git commit & push |
| **🚀 LIVE / PROD (Vận hành 24/7)** | **Google Cloud Server** (`136.110.29.208`) | Chạy quét Radar 24/7 (Scanner daemon), phục vụ API server, Web React UI, Cloudflare Tunnel | Ubuntu Linux | Docker Compose (`dao_vang_scanner`, `dao_vang_web`, `dao_vang_cloudflared`) |
| **💾 DATA & BACKTEST (Dữ liệu & Nghiên cứu)** | **Google Drive** | Lưu trữ dài hạn toàn bộ dữ liệu phái sinh (Parquet, DuckDB snapshots, feature sets, labels) | Cloud Storage | Đồng bộ định kỳ từ Live để phục vụ Backtest & Train mô hình ML mới |

---

## 2. Thông Tin Kết Nối & Triển Khai Máy Chủ LIVE (Google Cloud Server)

* **Địa chỉ IP Server**: `136.110.29.208`
* **Người dùng (User)**: `ubuntu`
* **Khóa SSH**: `~/.ssh/gcp_dao_vang` (Ed25519)
* **Thư mục làm việc trên server**: `/home/ubuntu/dao_vang`
* **Script triển khai tự động 1-click từ Desktop**:
  ```powershell
  python scripts/deploy_google_server.py
  ```
* **Quy trình deploy tự động bao gồm**:
  1. Đồng bộ mã nguồn mới nhất từ GitHub (`git fetch origin main && git reset --hard origin/main && git clean -fd`).
  2. Tự động dọn dẹp các file lock cũ (`data/web.lock`, `data_live/web.lock`, `data/scanner.lock`, `data_live/scanner.lock`).
  3. Dừng và rebuild các Docker container với frontend và code backend mới (`docker compose up -d --build --force-recreate`).
  4. Kiểm tra sức khỏe API (`http://localhost:8000/api/status`).

---

## 3. Quy Trình Lưu Trữ Dữ Liệu & Backtest (Google Drive)

1. **Thu thập dữ liệu Live**:
   * Scanner daemon trên Google Cloud Server liên tục thu thập nến 5m, Orderbook, Taker ratio, Open Interest, Funding rate và ghi vào định dạng Parquet / DuckDB.
2. **Lưu trữ & Sao lưu (Google Drive)**:
   * Toàn bộ dữ liệu thu thập được định kỳ đồng bộ sang Google Drive để bảo đảm an toàn dữ liệu và tối ưu dung lượng đĩa của VPS Google Cloud.
3. **Huấn luyện & Backtest**:
   * Khi cần chạy Walk-Forward Validation, phát triển Feature mới, hoặc Backtest chiến lược, dữ liệu từ Google Drive sẽ được nạp về môi trường Desktop DEV để chạy tính toán hiệu năng cao.
