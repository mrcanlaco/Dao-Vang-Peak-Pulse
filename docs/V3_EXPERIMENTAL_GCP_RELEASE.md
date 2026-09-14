# Bản thử nghiệm v3 trên GCP

## Backfill-on-discovery (discovery_backfill_v1)

Sau thu thập tăng dần, V3 kiểm tra các khoảng thiếu trong kho normalized cho
coin radar ≥15% đang được theo dõi. Tái sử dụng Klines/OI/Taker/Global/Top/Funding
collectors, raw envelopes, normalizers, kiểm tra chất lượng và feature builders.
Giá/OI/taker/ratio tải cửa sổ 25h (kiểm tra 289 nến liên tục cho return 24h);
funding tải 31 ngày và được align lên grid 5m riêng để tính cửa sổ tối đa 30 ngày.
Không phải tải lại 30 ngày nến giá để tính funding. Kho normalized đã có được
tái sử dụng, kể cả dữ liệu từng tải muộn; planner sửa cả prefix và lỗ hổng nội bộ.

`research_v3/backfill.sqlite` lưu trạng thái, tiến độ, lần thử, lỗi, retry time,
quality và transition history theo coin. Raw checkpoints trong `backfill_cache`
giúp resume sau crash trước normalize mà không tải trùng; dữ liệu hỏng được giữ
đuôi `.invalid` ngoài inbox chung. Raw/Parquet hợp lệ được ghi atomic vào kho
chung. Scanner vẫn chỉ có một writer dưới instance lock hiện hành.

Trước khi DuckDB đọc footer Parquet, file scanner được lọc bằng symbol và mốc
collection trong tên file. Không lọc chỉ theo ngày partition (một lần tải dài
được lưu theo ngày bắt đầu). File import/checkpoint chưa biết cấu trúc tên vẫn
được đọc để không bỏ mất lịch sử đã tải. Cách này tránh mở file của toàn thị
trường cho từng coin, giảm RAM và độ trễ trên kho production lớn.

Mỗi chu kỳ giới hạn 24 range requests, ngân sách tải 45 giây (request đang chạy
có timeout 8 giây), pacing 150ms/request. Lỗi HTTP/network trả về job để retry
exponential 60s–1h; 429/418 lưu Retry-After theo toàn nhánh, qua cả restart.
Một coin lỗi không dừng coin khác hoặc scanner. Job chưa xong tiếp tục lượt sau;
coin đang theo dõi được xử lý theo thứ tự lần thử cũ nhất.

V3 materialize vào `v3_live_features` **chỉ một nến đóng hiện tại mỗi lượt**,
lưu `materialized_at` thật và `discovery_first_seen`, unique theo symbol/time.
Không sửa `feature_results`, không ghi lại feature cũ đã materialize và không
replay các mốc giờ bị lỡ trong lúc backfill. Bộ quyết định Timing và runtime v2
giữ nguyên; mốc nguồn minute=4, first-seen, activation, last-seen, 90 phút,
armed peak ≥30%, hai xác nhận hàng giờ và episode ≥4h vẫn được áp dụng.
Lịch sử warmup không tạo episode/armed peak/xác nhận. Restart tiếp tục state cũ.

API `/api/research/v3` trả `discovery.items[].pipeline_stage` và `backfill`:
DETECTED → BACKFILLING → DATA_READY → SCORING → CONFIRMATION → ENTRY/REJECT.
SCORING biểu thị đã sẵn sàng cho mốc giờ; điểm và lý do quyết định được ghi sau
quan sát thật. CONFIRMATION tiếp tục tới khi đủ điều kiện, REJECT không xóa coin
khỏi radar. UI hiển thị tiến độ, chất lượng, lỗi và thời điểm thử lại.

OHLCV phải hợp lệ và đủ 289 nến; OI/taker đủ 24h, ratio đủ 4h, funding hiện tại
không quá 12h. Coin mới niêm yết chưa đủ funding 30 ngày được báo
`funding_history_short`; percentile/z-score 30d và feature 7d thiếu coverage giữ
NULL, không dùng lịch sử ngắn giả làm lịch sử đầy đủ. Model giữ missing policy
hiện có; Funding Scout không vượt cổng khi thiếu feature. Đây vẫn là forward
observed, không phải chứng nhận PIT hay hiệu quả lợi nhuận.

Kiểm thử bổ sung bao phủ tải mới, reuse, lỗ hổng nội bộ, lỗi theo coin,
rate-limit/restart, crash giữa raw và normalized, quarantine, funding ngắn và
pipeline collector→Parquet→feature→observer: chỉ Entry sau đủ 4h, không replay
giờ bị lỡ, không sửa feature nhánh cũ. Mobile smoke xác nhận trạng thái/retry UI.

## Phát hiện thị trường độc lập (runtime v2)

V3 nhận trực tiếp ticker USD-M USDT tăng từ 15%/24h mỗi chu kỳ, độc lập với
`pump_filter_v1` và lựa chọn chế độ quét của nhánh cũ. Coin dưới 1 triệu USD
volume/24h, ticker cũ hoặc vượt sức chứa 150 coin được hiển thị lý do, không
bị nhầm thành đã chấm điểm và bị loại. Chu kỳ đặt mục tiêu 5 phút nhưng có
thể chậm theo thời gian thu thập/xử lý; giao diện hiển thị thời điểm thực tế.

Danh sách thu thập là hợp của nhánh cũ và v3. Coin rời top gainers được giữ
6 giờ để theo dõi episode; vị thế mô phỏng đang mở được giữ tới 49 giờ để
hoàn thiện đường giá. SQLite `discovery.sqlite` lưu first-seen và từng lần
phát hiện; `discovery.json` cập nhật ngay trước thu thập và bổ sung trạng thái
feature sau thu thập. API trả riêng thời gian ticker và thời gian feature.

Phát hiện mới kiểm tra feature nến đóng 5 phút. **Timing/Entry vẫn lấy mốc
hàng giờ**, giữ score .39 x 2, khoảng cách tối đa 90 phút, đỉnh từ armed ≥30%,
episode ≥4h, score sau xác nhận ≥.29. Không diễn giải hai nến 5 phút thành hai
lần xác nhận của chiến lược đã backtest.

Chẩn đoán GCP ngày 14/9: tại 06:04:59.999 UTC, `price_ret_24h` của BR, AIN,
BTW, CVC là NULL. Timeline hợp lệ của các coin này chưa đủ 288 nến trước đó;
ARK/KOMA đã đủ. Đây là lý do cụ thể chúng bị câu SQL cũ loại, không chứng minh
rằng mức tăng thật dưới 15%. Lịch sử tải về muộn còn chịu điều kiện availability
của timeline. UI mới hiện rõ thiếu lịch sử; không lấy ticker thay vào feature
model hoặc tạo xác nhận lịch sử giả.

Runtime v1 → v2 có migration duy nhất: giữ các quan sát, Entry và outcome cũ,
ghi lại thời điểm kích hoạt cũ, bắt đầu lại episode/last-seen tại thời điểm đổi
phạm vi. Không dùng feature trước lúc first-seen để phát lại quyết định cho
coin mới. Kết quả từ phạm vi rộng mới phải được đánh giá riêng; không nhận tỷ
lệ thắng backtest cũ là tỷ lệ đã xác minh của tập mới.

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
