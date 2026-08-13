---
document_id: DISTRIBUTION_LABEL_SPEC_v0.3
label_id: distribution_short_v0.3
version: 0.3.0
status: experimental
adr: docs/decisions/ADR-009-label-v0.3.md
---

# ĐẶC TẢ NHÃN DISTRIBUTION v0.3

## 1. Mục đích

Thử nghiệm tăng prediction horizon lên **48 giờ** để kiểm tra xem nhịp giảm 20% trên altcoin biến động có hoàn thành trong khung thời gian dài hơn không, và liệu điều đó có cải thiện precision/recall so với v0.2 (24h).

## 2. Phạm vi

```yaml
market: binance_usdm_perpetual
interval: 5m
price_source: futures_kline
signal_price_field: close
signal_time: candle_close_time
target_drawdown: 0.20
maximum_adverse_excursion: 0.10
maximum_horizon: 48h
minimum_lead_time: 0m
```

### Universe

- Cùng với v0.2: các altcoin trong **multi-coin volatile scan**, loại BTC/ETH/top-cap.
- Coin phải có **≥ 500 positive labels** trong dữ liệu 90 ngày mới đưa vào train.

## 3. Điều kiện hợp lệ của signal row

Giống v0.2, nhưng cần đủ dữ liệu liên tục đến **T + 48h**.

## 4. Thuật toán

Với signal price `P0` tại thời điểm `T`:

1. Xét các nến đã đóng sau T đến T + 48h.
2. Target được đạt lần đầu tại nến `j` nếu:
   - `low_j <= P0 * (1 - 0.20)`.
3. Trước hoặc tại nến target, tính:
   - `MAE = max(high_i / P0 - 1)`.
4. Label dương khi:
   - target được đạt trong 48h;
   - `MAE <= 0.10`.
5. Nếu target không đạt hoặc MAE vượt 10% trước target, label âm.
6. Nếu dữ liệu không đủ đến T + 48h, label null.

## 5. Quy tắc giá

Giống v0.2.

## 6. Output schema

```yaml
label_version: "distribution_short_v0.3"
signal_time: datetime_utc
signal_price: decimal
label_value: integer|null
target_reached: boolean|null
target_time: datetime_utc|null
lead_time_minutes: integer|null
max_adverse_excursion: float|null
max_favorable_excursion_48h: float|null
future_max_high: decimal|null
future_min_low: decimal|null
exclusion_reason: string|null
```

## 7. Edge cases

Giống v0.2, với horizon tối đa 48h.

## 8. Test bắt buộc

Giống v0.2, thêm:

- target đạt trong khoảng 24–48h;
- target sau 48h;
- đủ dữ liệu 48h;
- thiếu dữ liệu trong 48h.

## 9. Điều chưa chốt

- Nếu v0.3 cải thiện rõ rệt, có thể thử **volatility-adjusted target** ở v0.4.
- Có thể thử MAE 12–15% nếu precision thấp do pullback sâu trước xả.

Không thay đổi v0.3 sau khi có artifact đầu tiên; mọi điều chỉnh phải tạo version mới.
