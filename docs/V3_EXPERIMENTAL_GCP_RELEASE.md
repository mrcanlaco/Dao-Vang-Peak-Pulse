# Bản thử nghiệm v3 trên GCP

## Phạm vi

Ứng dụng hiện có giữ bộ quét, lịch sử, watchlist và cảnh báo cũ. Nút
**Thử nghiệm v3 · 20% / 48h** mở khu vực riêng cho Challenger/Funding Scout,
Entry1/2/3 theo Compact và kết quả mô phỏng. Có nút quay về ứng dụng.

`research_v3_enabled` bật/tắt nhánh mới độc lập. Model tham chiếu đã khóa có
SHA-256 `1410707d5fc658278cc294d98cf9fccfbae52ffb1d3d9983b9aa7b773b437459`.
Không huấn luyện lại hoặc tự thay model phục vụ. Điểm tham chiếu không được
hiển thị như xác suất thắng v3.

Nhánh mới chạy sau khi scanner ghi xong snapshot chính, dùng cùng kết nối DB
để tránh khóa writer. Lỗi v3 không dừng nhánh chính; API báo lỗi hoặc dữ liệu cũ
sau 15 phút. API v3 yêu cầu đăng nhập như các API khác.

## Dữ liệu và giới hạn thử nghiệm

- Ghi snapshot ứng viên hàng giờ từ lúc bật, không biến backtest thành tín hiệu
  mới. Cần episode đủ 4h và xác nhận; vì vậy có thể chưa có Entry ngay khi deploy.
- Lưu feature/điểm/thời gian quan sát, quyết định chọn/loại và state episode vào
  `data_live/research_v3/observations.sqlite`; snapshot UI là `snapshot.json`.
- Khởi động lại tiếp tục từ state; thay model/contract phải đổi thư mục bằng chứng,
  không âm thầm dùng state cũ. Không backfill lúc scanner dừng quá 90 phút.
- Chỉ mô phỏng Entry tại giá đóng nến nguồn; độ trễ quét có thể khiến giá thực tế
  khác. Kết quả không phải giá khớp giao dịch thực và chưa được chứng nhận PIT.
- Target/stop hiện hành dựa trên quantity-weighted average theo tỷ trọng notional
  20/30/50. Cửa sổ thêm lệnh 6h, giới hạn toàn bộ 48h.
- Outcome không đủ nến còn trong hạn hiển thị đang theo dõi; sau 49h còn thiếu
  thì đóng là thiếu dữ liệu. Không tính thiếu dữ liệu thành thắng/thua.
- Chưa xác minh funding, nên không báo net EV hoặc tỷ lệ chính xác chính thức.
- Không đặt lệnh và không gửi Telegram từ nhánh v3. Cảnh báo cũ không bị đổi nghĩa.
- Nến v3 chọn phiên bản theo available time rồi collected time; exact tie khác
  OHLC bị từ chối, không chọn tùy ý. Bản ghi mô phỏng terminal được giữ nguyên.

## Kiểm tra và triển khai

1. Python tests/lint/typecheck, frontend build/bundle budget và browser smoke.
2. Chuyển riêng model tham chiếu tới path trong config, kiểm tra đúng SHA trước
   khi nạp pickle. Không commit khóa, mật khẩu, DB hoặc model phát sinh.
3. Commit code và chờ CI của đúng SHA; workflow GCP build trước khi đổi container.
4. Giữ Git SHA, config và image cũ để rollback. Không xóa dữ liệu/model runtime.
5. Kiểm tra web/scanner healthy, API có xác thực và snapshot v3 bắt đầu ghi.

## Quay lại

Có thể tắt riêng nhánh v3 bằng `research_v3_enabled: false` và khởi động lại
scanner/web theo quy trình host. Giữ nguyên thư mục `research_v3` để audit.
Nếu cần rollback cả giao diện/code, dùng image/config đã giữ trước rollout;
không reset hoặc xóa dữ liệu để quay lại. Việc rollback phải được ghi nhận,
tránh để CI tự triển khai lại một revision khác trong lúc phục hồi.
