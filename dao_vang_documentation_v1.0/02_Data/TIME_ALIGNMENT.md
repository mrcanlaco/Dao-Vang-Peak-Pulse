---
document_id: DAO_VANG_TIME_ALIGNMENT_SPEC
version: 1.0.0
status: approved_for_mvp
---

# ĐẶC TẢ CĂN CHỈNH THỜI GIAN

## 1. Canonical timeline

MVP dùng timeline 5 phút theo close time của nến BTCUSDT futures đã đóng.

Ví dụ:

```text
Nến open 12:00:00, close 12:04:59.999
feature_time chuẩn hóa: 12:05:00 UTC
```

Không tạo feature cho nến đang mở.

## 2. Luật point-in-time

Tại `feature_time = T`, một record chỉ được join nếu:

```text
record.available_time <= T
```

Không dùng:

- nearest join hai phía;
- backward fill từ tương lai;
- interpolation qua tương lai;
- timestamp event_time thay cho available_time khi available_time muộn hơn.

## 3. Availability rules

### OHLCV

```text
event_time = candle_close_time
available_time = candle_close_time + configured_kline_lag
```

Default historical lag: 1 giây.

### Period statistics 5m

```text
event_time = period_end
available_time = period_end + configured_statistics_lag
```

Default historical lag: 5 giây, phải hiệu chỉnh bằng forward collection.

### Funding

```text
event_time = funding_time
available_time = funding_time + configured_funding_lag
```

Default historical lag: 5 giây.

## 4. Alignment method

### Exact join

OHLCV và 5m statistics được exact join theo `period_end == feature_time` sau khi chuẩn hóa.

Nếu timestamp nguồn biểu diễn period start:

```text
period_end = period_start + 5m
```

### As-of backward join

Funding được as-of backward join theo `available_time`, lấy record mới nhất đã biết.

Phải lưu:

- `funding_rate_last_known`;
- `funding_event_time`;
- `funding_age_minutes`.

Không carry forward quá `max_funding_age = 12h`. Quá ngưỡng thì null.

## 5. Missing data policy

- Không nội suy OHLCV.
- Không nội suy OI/taker/ratio.
- Không backfill từ record tương lai.
- Có thể carry-forward funding theo luật trên.
- Missing được giữ null và gắn quality flag.

Row quality:

```yaml
valid:
  required_price_present: true
  completeness: ">= 0.80"
warning:
  required_price_present: true
  completeness: ">= 0.50 and < 0.80"
invalid:
  required_price_present: false
  or completeness: "< 0.50"
```

Ngưỡng có thể thay đổi bằng version mới.

## 6. Duplicates

Nếu có nhiều record cùng natural key:

1. cùng payload hash: giữ một, ghi duplicate flag;
2. payload khác nhau:
   - giữ tất cả raw;
   - normalized chọn record có `collected_at` sớm nhất cho point-in-time snapshot;
   - ghi conflict;
   - quarantine nếu không xác định được.

Không chọn bản sửa sau này để thay lịch sử mà không tạo dataset version mới.

## 7. Clock handling

- Server time được kiểm tra đầu collection run.
- Ghi local clock offset.
- Nếu lệch clock > 1 giây: warning.
- Nếu > 5 giây: fail collection run.
- Mọi timestamp chuyển UTC trước lưu.

## 8. Watermark

Mỗi data type có watermark riêng:

```text
latest contiguous valid period_end
```

Dataset builder chỉ tạo đến minimum watermark của các nguồn bắt buộc, trừ khi config cho phép partial rows.

## 9. Leakage tests bắt buộc

1. Thêm record có available_time sau T không làm feature tại T thay đổi.
2. As-of join luôn chọn backward.
3. Dữ liệu cùng event_time nhưng collected muộn không xuất hiện sớm.
4. Nến chưa đóng bị loại.
5. Funding quá cũ thành null.
6. Future row addition không thay aligned rows quá khứ.
7. Timezone conversion không dịch bucket.

## 10. Ví dụ

Tại T=12:05:

| Nguồn | event_time | available_time | Được dùng? |
|---|---:|---:|---|
| Kline 12:00–12:05 | 12:05 | 12:05:01 | Không tại đúng 12:05:00 |
| OI period | 12:05 | 12:05:04 | Không |
| Funding cũ | 08:00 | 08:00:05 | Có |
| Ratio future | 12:10 | 12:10:04 | Không |

Trong historical feature generation, feature timestamp có thể định nghĩa là `decision_time = canonical_close + max_configured_lag`, ví dụ 12:05:05. Tên này phải được lưu riêng, không giả vờ dữ liệu có tại 12:05:00.
