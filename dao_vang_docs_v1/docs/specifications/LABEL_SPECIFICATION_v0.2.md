---
document_id: DISTRIBUTION_LABEL_SPEC_v0.2
label_id: distribution_short_v0.2
version: 0.2.0
status: experimental
adr: docs/decisions/ADR-008-label-v0.2.md
---

# ĐẶC TẢ NHÃN DISTRIBUTION v0.2

## 1. Mục đích

Thử nghiệm định nghĩa Distribution là một nhịp giảm **sâu hơn** (≥ 20%) trong khung 24h, cho phép pullback trước khi xả lớn hơn (MAE ≤ 10%), và giới hạn train trên các **altcoin biến động lớn** — nơi những nhịp xả này xảy ra đủ thường xuyên để có dữ liệu thống kê.

## 2. Phạm vi

```yaml
market: binance_usdm_perpetual
interval: 5m
price_source: futures_kline
signal_price_field: close
signal_time: candle_close_time
target_drawdown: 0.20
maximum_adverse_excursion: 0.10
maximum_horizon: 24h
minimum_lead_time: 0m
```

### Universe

- Chỉ các altcoin được chọn qua **multi-coin volatile scan** (biến động 24h cao, đủ volume).
- Loại BTCUSDT, ETHUSDT và các coin top-cap / low-volatility khỏi tập train vì tần suất nhịp giảm 20%/24h gần như bằng 0 trong dữ liệu lịch sử.
- Một coin chỉ được đưa vào tập train nếu có **ít nhất 500 positive labels** trong cửa sổ dữ liệu hiện có (khoảng 90 ngày).

## 3. Điều kiện hợp lệ của signal row

Một row chỉ được gắn nhãn khi:

- nến tín hiệu đã đóng;
- có đủ dữ liệu giá liên tục đến hết horizon;
- không có gap giá lớn hơn 2 nến liên tiếp;
- symbol đang ở trạng thái giao dịch bình thường;
- quality status của price window không phải `invalid` hoặc `quarantined`.

Nếu không đủ điều kiện, label là `null`, không phải 0.

## 4. Thuật toán

Với signal price `P0` tại thời điểm `T`:

1. Xét các nến đã đóng sau T đến T + 24h.
2. Target được đạt lần đầu tại nến `j` nếu:
   - `low_j <= P0 * (1 - 0.20)`.
3. Trước hoặc tại nến target, tính:
   - `MAE = max(high_i / P0 - 1)`.
4. Label dương khi:
   - target được đạt trong 24h;
   - `MAE <= 0.10`.
5. Nếu target không đạt hoặc MAE vượt 10% trước target, label âm.
6. Nếu dữ liệu không đủ, label null.

## 5. Quy tắc giá

- Dùng low để xác định target đã chạm.
- Dùng high để tính MAE.
- Dùng close nến tín hiệu làm `P0`.
- Không giả định khả năng khớp lệnh tại low/high.
- Label đo sự kiện thị trường, không đo lợi nhuận giao dịch.

## 6. Output schema

```yaml
label_version: "distribution_short_v0.2"
signal_time: datetime_utc
signal_price: decimal
label_value: integer|null
target_reached: boolean|null
target_time: datetime_utc|null
lead_time_minutes: integer|null
max_adverse_excursion: float|null
max_favorable_excursion_24h: float|null
future_max_high: decimal|null
future_min_low: decimal|null
exclusion_reason: string|null
```

## 7. Edge cases

### Target và MAE xảy ra cùng nến

Do OHLC không cho biết thứ tự intrabar, trường hợp cùng nến vừa vượt MAE 10% vừa chạm target 20% là `ambiguous_intrabar` và label `null` trong v0.2.

### Gap hoặc dữ liệu thiếu

- thiếu 1 nến: có thể giữ row nhưng quality=`warning`;
- thiếu trên 2 nến liên tiếp: label null;
- không forward-fill OHLCV.

### Flash crash

V0.2 vẫn tính flash crash nếu dữ liệu nguồn hợp lệ. Báo cáo phải có trường anomaly để phân tích riêng. Không loại thủ công sau khi xem outcome.

### Các signal liên tiếp

Mọi timestamp 5 phút đủ điều kiện đều được gắn label để phục vụ supervised learning.

Khi đánh giá pattern/event-level, dùng cooldown 4 giờ để tránh đếm nhiều tín hiệu trùng một sự kiện. Cả row-level và event-level metrics phải được báo cáo.

## 8. Test bắt buộc

- target đạt và MAE dưới ngưỡng 10%;
- target không đạt;
- MAE vượt 10% trước target;
- target đúng tại 24h;
- target sau 24h;
- thiếu future data;
- target và MAE cùng nến;
- không thay đổi label quá khứ khi thêm dữ liệu sau horizon;
- deterministic với cùng input.

## 9. Điều chưa chốt

- Horizon 24h có thể quá ngắn cho target 20%; nếu experiment thiếu positive sẽ thử 48h.
- Có thể thử `volatility-adjusted target` (target phụ thuộc ATR) ở v0.3.
- Cần đánh giá xem train per-coin hay pooled multi-coin cho kết quả ổn định hơn.

Không thay đổi v0.2 sau khi có artifact đầu tiên; mọi điều chỉnh phải tạo version mới.
