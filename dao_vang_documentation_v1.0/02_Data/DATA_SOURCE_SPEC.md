---
document_id: DAO_VANG_DATA_SOURCE_SPEC
version: 1.0.0
status: approved_for_mvp
source_authority: Binance USD-M Futures official API
---

# ĐẶC TẢ NGUỒN DỮ LIỆU

## 1. Nguồn chuẩn

```yaml
provider: Binance
product: USD-M Futures
base_url: https://fapi.binance.com
symbol: BTCUSDT
authentication: public_market_data
canonical_period: 5m
```

Không fallback sang sàn hoặc endpoint khác trong cùng dataset version.

## 2. Endpoint MVP

| Data type | Endpoint | Key time field | Period | Lịch sử |
|---|---|---|---|---|
| OHLCV | `GET /fapi/v1/klines` | open/close time | 5m | tải theo pagination |
| Funding | `GET /fapi/v1/fundingRate` | fundingTime | event-based | kiểm tra giới hạn API |
| Open Interest Statistics | `GET /futures/data/openInterestHist` | timestamp | 5m | thường chỉ gần đây |
| Taker Buy/Sell | `GET /futures/data/takerlongshortRatio` | timestamp | 5m | latest 30 days theo docs |
| Global Long/Short Account | `GET /futures/data/globalLongShortAccountRatio` | timestamp | 5m | latest 30 days theo docs |
| Top Trader Long/Short Account | `GET /futures/data/topLongShortAccountRatio` | timestamp | 5m | latest 30 days theo docs |

Collector phải kiểm tra lại official docs và contract tests, không dựa vào tên endpoint.

## 3. Hệ quả của giới hạn lịch sử

Các endpoint statistics có thể chỉ cung cấp cửa sổ lịch sử ngắn. Vì vậy:

- không giả định có thể backfill nhiều năm;
- collector phải chạy định kỳ và lưu snapshot liên tục;
- raw response phải bất biến;
- mọi khoảng thiếu phải được ghi metadata;
- không dùng nguồn thay thế âm thầm;
- MVP dataset có thể bắt đầu với độ dài giới hạn và phải báo sample size trung thực.

## 4. Quy tắc endpoint

### 4.1. OHLCV

- Chỉ giữ nến đã đóng.
- `event_time` chuẩn là `close_time`.
- `available_time` backfill = `close_time + availability_lag`.
- `availability_lag` mặc định 1000 ms cho historical simulation, có thể hiệu chỉnh bằng forward collection.
- Raw payload phải giữ toàn bộ fields Binance trả về.

### 4.2. Funding Rate

- `event_time = fundingTime`.
- `available_time = max(fundingTime, collected_at)` cho forward snapshot.
- Với backfill, đặt `available_time = fundingTime + configured_lag`.
- Không forward-fill funding raw như thể có sự kiện mới; alignment layer có thể carry-forward `last_known_funding_rate`.

### 4.3. Open Interest Statistics

- Dùng endpoint lịch sử theo period 5m, không dùng current open interest để tái tạo quá khứ.
- Timestamp được xem là start time của period nếu docs ghi như vậy.
- `available_time = period_end + configured_lag`.
- Lưu `sumOpenInterest` và `sumOpenInterestValue` nếu có.

### 4.4. Taker Buy/Sell Volume

- Dùng `buyVol`, `sellVol`, `buySellRatio`.
- Timestamp là start time của period.
- Không diễn giải buy volume là toàn bộ market buy volume ngoài contract của endpoint.
- `available_time = period_end + configured_lag`.

### 4.5. Global Long/Short Account Ratio

- Dùng tỷ lệ số account Long/Short toàn bộ trader.
- Không nhầm với position ratio.
- `available_time = period_end + configured_lag`.

### 4.6. Top Trader Account Ratio

- Dùng account ratio của top traders.
- Không nhầm với Top Trader Position Ratio.
- `available_time = period_end + configured_lag`.

## 5. Collection policy

```yaml
timeout_seconds: 15
max_retries: 5
retry_backoff: exponential_with_jitter
respect_retry_after: true
max_concurrency: 2
raw_write_before_normalize: true
```

Mọi request log:

- endpoint;
- params;
- request start/end;
- HTTP status;
- response headers liên quan rate limit;
- response hash;
- row count;
- collector version;
- error hoặc retry count.

## 6. Pagination

- Pagination phải idempotent.
- Dùng explicit start/end time.
- Window kế tiếp bắt đầu sau timestamp cuối đã xác nhận.
- Deduplicate bằng natural key.
- Không coi response rỗng là thành công nếu nằm trong kỳ vọng dữ liệu.
- Ghi watermark theo từng data type.

## 7. Source versioning

`source_version` gồm:

```text
provider + product + endpoint + response_schema_hash + collector_parser_version
```

Schema thay đổi phải:

1. fail contract test;
2. quarantine response;
3. tạo parser/source version mới;
4. không ghi đè normalized cũ.

## 8. Validation với nguồn

Mỗi endpoint cần contract test xác minh:

- HTTP 200;
- required fields;
- numeric strings parse được;
- timestamp hợp lệ;
- period đúng;
- thứ tự timestamp;
- response không vượt assumptions.

## 9. Chính sách secrets

MVP dùng public market data. Không yêu cầu API key. Nếu sau này thêm key:

- chỉ đọc từ environment/secret store;
- không commit;
- không cấp trade permission;
- không log key.
