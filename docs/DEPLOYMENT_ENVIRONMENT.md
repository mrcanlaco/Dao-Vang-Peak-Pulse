# Môi Trường Triển Khai & Vận Hành (Deployment Environment)

## 1. Phân định môi trường (Environment Separation)

| Môi trường | Thiết bị / Máy chủ | Vai trò | Hệ điều hành | Phương thức chạy |
|---|---|---|---|---|
| **DEV** | Máy bàn (Local Desktop) | Phát triển tính năng, kiểm thử, debug, build code | Windows | Local Python (.venv), Vite dev |
| **PROD** | Máy chủ Ubuntu MSI | Chạy quét 24/7 (Scanner), phục vụ API server, React frontend, Cloudflare Tunnel | Ubuntu Linux | Docker Compose (dao_vang_scanner, dao_vang_web, dao_vang_cloudflared) |

---

## 2. Nguyên nhân & Cách khắc phục lỗi 502 / 524 trên Ubuntu MSI

### A. Lỗi HTTP 502 (Bad Gateway)
**Bản chất**: Cloudflare Tunnel (dao_vang_cloudflared) không thể kết nối tới cổng http://localhost:8000 của dịch vụ dao_vang_web (Connection Refused).

**Các nguyên nhân chính**:
1. **Container dao_vang_web bị crash hoặc dừng**:
   - Do hết RAM (OOM Killer trên Linux giết process Python).
   - Do xung đột file lock web.lock hoặc scanner.lock khi khởi động lại.
2. **Dịch vụ chưa được khởi động sau khi reboot / update**:
   - Container chưa chạy hoặc đang bị restart loop.

**Cách kiểm tra và xử lý trên Ubuntu MSI**:
`ash
# 1. Kiểm tra trạng thái các container
docker compose ps

# 2. Xem log lỗi gần nhất của container web
docker compose logs -n 100 web

# 3. Xem log của cloudflared
docker compose logs -n 100 cloudflared

# 4. Kéo code mới nhất đã fix lỗi truy vấn & build lại
git pull origin main
docker compose down
# Xóa file lock cũ nếu có
rm -f data/web.lock data_live/web.lock
# Build và chạy lại
docker compose build
docker compose up -d
`

---

### B. Lỗi HTTP 524 (A Timeout Occurred)
**Bản chất**: Container dao_vang_web vẫn sống nhưng xử lý request vượt quá 100 giây (timeout mặc định của Cloudflare) do câu truy vấn DuckDB nặng (quét VIEW hàng triệu dòng hoặc copy file database lớn).

**Đã khắc phục trong mã nguồn**:
1. pi_server.py: Sử dụng trực tiếp system_data_stats.json được scanner daemon tạo định kỳ thay vì thực hiện full table scan mỗi lần gọi API.
2. _self_learning_status: Bỏ join toàn bảng eature_results x labels (1.3M+ dòng), trả về kết quả trong < 0.2s.
3. Chỉ truy vấn BASE TABLE, không quét VIEW lớn (ligned_5m, kline, unding...).
4. Frontend: Thêm ErrorBoundary và kiểm tra an toàn dữ liệu, ngăn chặn lỗi đen/trắng màn hình.
