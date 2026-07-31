# DATA QUALITY

## Trạng thái

- `valid`: dùng bình thường.
- `warning`: dùng có cờ cảnh báo.
- `invalid`: không dùng để tạo feature/label.
- `quarantined`: chưa được normalize hoặc cần review.

## Checks chung

- duplicate natural key;
- timestamp order;
- expected interval;
- missing periods;
- schema drift;
- parse failures;
- negative/invalid values;
- source latency;
- response truncation;
- cross-field consistency;
- clock drift.

## OHLCV

- high >= open/close/low;
- low <= open/close/high;
- volume >= 0;
- close time đúng interval;
- chỉ nến đã đóng.

## Statistics

- value parse được;
- ratio > 0 khi bắt buộc;
- period đều;
- không nhầm endpoint/account vs position.

## Hành động

- Không auto sửa raw.
- Repair normalized chỉ bằng rule versioned.
- Mọi loại bỏ phải có `exclusion_reason`.
- Báo cáo quality theo ngày, nguồn và dataset version.
