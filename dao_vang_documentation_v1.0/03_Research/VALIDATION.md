# VALIDATION PROTOCOL

## Split

- Chỉ chronological.
- Không shuffle.
- Không overlap leakage giữa lookback/horizon.
- Embargo tối thiểu bằng maximum horizon giữa train và test khi cần.

## Walk-forward khởi điểm

```yaml
train_window: 90d
validation_window: 30d
test_window: 30d
step: 30d
```

Có thể điều chỉnh khi dữ liệu thực tế hạn chế, nhưng phải version.

## Fitting

- scaler/imputer fit train only;
- feature selection train only;
- threshold validation only;
- test locked.

## Báo cáo

- aggregate;
- per-window;
- regime;
- confidence interval;
- calibration curve;
- error analysis;
- row-level và event-level.

## Final test

Sau final test, nếu sửa phương pháp thì test trở thành validation lịch sử và cần test mới.
