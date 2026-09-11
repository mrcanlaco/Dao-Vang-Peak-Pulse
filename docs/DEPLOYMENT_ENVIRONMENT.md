# Môi trường triển khai Đảo Vàng

## Local
- Python 3.12 trong .venv; React/Vite ở frontend.
- API: http://127.0.0.1:8000; Vite: http://localhost:8088.
- Khởi động: `.venv/Scripts/python.exe -m dao_vang.web.run --host 127.0.0.1 --port 8000 --reload`.
- Chạy frontend: `cd frontend`, sau đó `npm run dev`.
- `dao-vang-ui` cũng hỗ trợ --host, --port và --reload. Cổng positional cũ vẫn được hỗ trợ.
- Dữ liệu và mật khẩu lấy từ môi trường/.env. Không mặc định bật scanner khi khởi động web.

## GCP
- Host: 136.110.29.208; tài khoản SSH: ubuntu.
- Khóa: ~/.ssh/gcp_dao_vang.
- Thư mục: /home/ubuntu/dao_vang.
- Domain: https://daovang.comaygiauco.com.
- Docker Compose: scanner, web, cloudflared.
- Bind mount dữ liệu trên host ./data vào /app/data_live; artifacts và configs giữ riêng ngoài image.
- Không xóa file lock của dịch vụ đang chạy.
- Scanner healthcheck yêu cầu heartbeat mới trong 15 phút, trạng thái running và chu kỳ gần nhất không failed.
- /api/health kiểm tra web còn đáp ứng; nó không thay thế kiểm tra scanner, dữ liệu và model.

## Triển khai
1. Kiểm tra mã: Ruff, bộ kiểm thử Python, Pyright theo danh sách CI; frontend build.
2. Commit và lưu mã vào GitHub. CI phải thành công trước khi workflow deploy chạy.
3. Workflow deploy triển khai đúng SHA đã qua CI, không tự reset/clean hoặc ghi đè thay đổi chưa commit.
4. Có thể xem trước triển khai thủ công: `python scripts/deploy_google_server.py --revision <SHA-40-ký-tự>`.
5. Thêm --apply để thực hiện. Server phải có thư mục Git sạch và revision phải có sẵn trên remote.
6. Chờ cả các dịch vụ Docker healthy, rồi kiểm tra API qua domain và dữ liệu scanner.
7. Updater trong container được tắt vì .git chỉ đọc; cập nhật qua host/CI.

## Rà soát và phục hồi
- Chạy `python scripts/audit_runtime.py` trong container web để kiểm tra API có xác thực; công cụ không in mật khẩu/cookie, không gửi Telegram.
- Chạy `python scripts/check_public_url.py` từ bên ngoài để kiểm tra domain và yêu cầu đăng nhập.
- Trước rollout, giữ image đang chạy và Git SHA cũ. Chỉ thay image khi image mới đã build và qua kiểm thử.
- Không xóa dữ liệu, artifacts, Docker image hoặc bản sao lưu khi chưa xác định chính sách lưu trữ.
- Xem [báo cáo rà soát 11/09/2026](AUDIT_2026-09-11.md) để biết lỗi đã sửa và các giới hạn kiểm chứng.
