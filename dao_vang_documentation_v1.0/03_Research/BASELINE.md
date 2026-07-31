# BASELINE SPECIFICATION

## Baselines bắt buộc

- B0: prevalence/random calibrated.
- B1: price return 24h cao.
- B2: funding percentile cao.
- B3: OI change 4h cao.
- B4: funding cao + OI tăng.
- B5: logistic regression Feature Set v0.1.

## Quy tắc threshold

- Chọn threshold chỉ trên train/validation.
- Không chỉnh sau khi xem test.
- Threshold và seed lưu trong artifact.

## So sánh

Báo:

- precision;
- recall;
- signal rate;
- FPR;
- lead time;
- sample size;
- calibration;
- confidence interval.
