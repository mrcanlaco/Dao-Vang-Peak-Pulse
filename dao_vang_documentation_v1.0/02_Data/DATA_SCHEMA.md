---
document_id: DAO_VANG_DATA_SCHEMA
version: 1.0.0
status: approved_for_mvp
---

# ĐẶC TẢ SCHEMA DỮ LIỆU

## 1. Quy ước chung

- UTC timezone-aware.
- Timestamp lưu microseconds hoặc milliseconds nhưng interface Python dùng `datetime[UTC]`.
- Giá trị số từ API parse bằng Decimal ở lớp normalization; feature có thể dùng float64 sau kiểm tra.
- Tên cột snake_case.
- Không overwrite raw.
- Null phải có lý do khi ảnh hưởng pipeline.

## 2. Raw Envelope

```yaml
collection_run_id: string
request_id: string
provider: string
product: string
endpoint: string
request_params_json: string
requested_at: datetime_utc
received_at: datetime_utc
http_status: int
response_hash_sha256: string
source_version: string
collector_version: string
payload_json: string
```

Partition:

```text
data/raw/{data_type}/date={YYYY-MM-DD}/
```

## 3. Common normalized fields

```yaml
symbol: string
market: string
data_type: string
interval: string|null
event_time: datetime_utc
available_time: datetime_utc
collected_at: datetime_utc
source_version: string
dataset_version: string
quality_status: enum[valid,warning,invalid,quarantined]
quality_flags: list[string]
```

Invariant:

```text
available_time >= event_time
collected_at >= event_time
```

Ngoại lệ phải được ghi quality flag và không dùng production dataset.

## 4. OHLCV schema

```yaml
symbol: string
interval: string
open_time: datetime_utc
close_time: datetime_utc
event_time: datetime_utc
available_time: datetime_utc
open: decimal
high: decimal
low: decimal
close: decimal
volume_base: decimal
volume_quote: decimal
trade_count: int
taker_buy_base: decimal
taker_buy_quote: decimal
quality_status: string
quality_flags: list[string]
source_version: string
```

Primary key:

```text
(symbol, interval, open_time, source_version)
```

Checks:

- high >= max(open, close, low);
- low <= min(open, close, high);
- volume >= 0;
- close_time > open_time.

## 5. Funding schema

```yaml
symbol: string
funding_time: datetime_utc
event_time: datetime_utc
available_time: datetime_utc
funding_rate: decimal
mark_price: decimal|null
quality_status: string
quality_flags: list[string]
source_version: string
```

Primary key:

```text
(symbol, funding_time, source_version)
```

## 6. Open Interest schema

```yaml
symbol: string
interval: string
period_start: datetime_utc
period_end: datetime_utc
event_time: datetime_utc
available_time: datetime_utc
open_interest_contracts: decimal
open_interest_value: decimal|null
quality_status: string
quality_flags: list[string]
source_version: string
```

Primary key:

```text
(symbol, interval, period_start, source_version)
```

## 7. Taker Volume schema

```yaml
symbol: string
interval: string
period_start: datetime_utc
period_end: datetime_utc
event_time: datetime_utc
available_time: datetime_utc
buy_volume: decimal
sell_volume: decimal
buy_sell_ratio: decimal|null
quality_status: string
quality_flags: list[string]
source_version: string
```

## 8. Global Ratio schema

```yaml
symbol: string
interval: string
period_start: datetime_utc
period_end: datetime_utc
event_time: datetime_utc
available_time: datetime_utc
long_account: decimal|null
short_account: decimal|null
long_short_ratio: decimal
quality_status: string
quality_flags: list[string]
source_version: string
```

## 9. Top Trader Account Ratio schema

Giống Global Ratio, thêm:

```yaml
population: constant["top_trader_accounts"]
```

## 10. Aligned dataset schema

```yaml
symbol: string
feature_time: datetime_utc
price_open: float
price_high: float
price_low: float
price_close: float
price_volume_base: float
funding_rate_last_known: float|null
funding_age_minutes: int|null
open_interest: float|null
taker_buy_volume: float|null
taker_sell_volume: float|null
global_long_short_ratio: float|null
top_trader_long_short_ratio: float|null
data_completeness: float
quality_status: string
dataset_version: string
```

Unique key:

```text
(symbol, feature_time, dataset_version)
```

## 11. Feature table schema

```yaml
symbol: string
feature_time: datetime_utc
dataset_version: string
feature_set_version: string
features: columns defined by feature registry
row_quality_status: string
feature_missing_count: int
label_version: string|null
label_value: int|null
```

Feature table dùng cho model phải được xuất thành artifact bất biến.

## 12. Metadata schemas

### Collection run

```yaml
collection_run_id: string
started_at: datetime_utc
completed_at: datetime_utc|null
status: enum[running,succeeded,partial,failed]
data_type: string
range_start: datetime_utc
range_end: datetime_utc
rows_raw: int
rows_normalized: int
error_count: int
collector_version: string
```

### Dataset manifest

```yaml
dataset_version: string
created_at: datetime_utc
source_versions: map
input_files: list
input_hashes: list
schema_version: string
alignment_version: string
row_count: int
min_time: datetime_utc
max_time: datetime_utc
fingerprint_sha256: string
```

## 13. Compatibility

- Thêm nullable column: minor version.
- Đổi semantic hoặc type: major version.
- Xóa/đổi tên column: major version và migration explicit.
