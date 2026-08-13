---
document_id: DISTRIBUTION_LABEL_SPEC
label_id: distribution_short
version: 0.1.0
status: active_production
---

# ĐẶC TẢ NHÃN DISTRIBUTION v0.1

## 1. Mục đích

Tạo nhãn nhị phân tái tạo được để kiểm tra khả năng phát hiện sớm một nhịp giảm đáng kể sau signal time.

## 2. Phạm vi

```yaml
symbol: BTCUSDT
market: binance_usdm_perpetual
interval: 5m
price_source: futures_kline
signal_price_field: close
signal_time: candle_close_time
target_drawdown: 0.08
maximum_adverse_excursion: 0.04
maximum_horizon: 24h
minimum_lead_time: 0m
```

`minimum_lead_time` được đặt 0 ở v0.1 để label engine đơn giản. Báo cáo phải phân phối outcome theo lead-time buckets: `<1h`, `1–4h`, `4–12h`, `12–24h`.

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
   - `low_j <= P0 * (1 - 0.08)`.
3. Trước hoặc tại nến target, tính:
   - `MAE = max(high_i / P0 - 1)`.
4. Label dương khi:
   - target được đạt trong 24h;
   - `MAE <= 0.04`.
5. Nếu target không đạt hoặc MAE vượt 4% trước target, label âm.
6. Nếu dữ liệu không đủ, label null.

## 5. Quy tắc giá

- Dùng low để xác định target đã chạm.
- Dùng high để tính MAE.
- Dùng close nến tín hiệu làm `P0`.
- Không giả định khả năng khớp lệnh tại low/high.
- Label đo sự kiện thị trường, không đo lợi nhuận giao dịch.

## 6. Output schema

```yaml
signal_time: datetime_utc
signal_price: decimal
label_version: string
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

Do OHLC không cho biết thứ tự intrabar, trường hợp cùng nến vừa vượt MAE 4% vừa chạm target 8% là `ambiguous_intrabar` và label `null` trong v0.1.

### Gap hoặc dữ liệu thiếu

- thiếu 1 nến: có thể giữ row nhưng quality=`warning`;
- thiếu trên 2 nến liên tiếp: label null;
- không forward-fill OHLCV.

### Flash crash

V0.1 vẫn tính flash crash nếu dữ liệu nguồn hợp lệ. Báo cáo phải có trường anomaly để phân tích riêng. Không loại thủ công sau khi xem outcome.

### Các signal liên tiếp

Mọi timestamp 5 phút đủ điều kiện đều được gắn label để phục vụ supervised learning.

Khi đánh giá pattern/event-level, dùng cooldown 4 giờ để tránh đếm nhiều tín hiệu trùng một sự kiện. Cả row-level và event-level metrics phải được báo cáo.

## 8. Test bắt buộc

- target đạt và MAE dưới ngưỡng;
- target không đạt;
- MAE vượt trước target;
- target đúng tại 24h;
- target sau 24h;
- thiếu future data;
- target và MAE cùng nến;
- không thay đổi label quá khứ khi thêm dữ liệu sau horizon;
- deterministic với cùng input.

## 9. Điều chưa chốt

V0.2 có thể nghiên cứu:

- minimum lead time 4h;
- target dựa trên close thay vì low;
- volatility-adjusted target;
- multi-class Short/Medium/Slow;
- event deduplication khác.

Không thay đổi v0.1; phải tạo version mới.
