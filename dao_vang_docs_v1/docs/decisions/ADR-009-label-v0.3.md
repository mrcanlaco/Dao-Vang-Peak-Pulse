---
document_id: ADR-009
status: experimental
decision_date: 2026-08-10
author: Integrator
related: LABEL_SPECIFICATION_v0.3.md, ADR-008-label-v0.2.md
---

# ADR-009: Label Distribution v0.3 — Target 20% / MAE 10% với horizon 48h

## Status

Experimental — so sánh trực tiếp với v0.2 (horizon 24h).

## Context

ADR-008 (Label v0.2: 20%/10%/24h) đã cho thấy model vượt baseline trên backtest, nhưng forward-test precision có drift đáng kể so với validation. Một trong những lý do có thể là nhịp giảm 20% thường cần nhiều hơn 24 giờ để hoàn thành, đặc biệt trên các altcoin biến động lớn. Vì vậy, thử nghiệm tăng horizon lên **48h** để xem số lượng positive, precision, recall và lead time có cải thiện không.

## Decision

Triển khai **Label Distribution v0.3**:

- `target_drawdown`: **0.20** (20%)
- `maximum_adverse_excursion`: **0.10** (10%)
- `maximum_horizon`: **48h** (2880 phút)
- Cùng universe và whitelist với v0.2: các altcoin biến động mạnh, loại BTC/ETH/top cap.

## Alternatives considered

1. **Giữ v0.2 24h, tinh chỉnh threshold / feature**: chưa giải quyết vấn đề horizon quá ngắn.
2. **Tăng target lên 30%**: sẽ làm positive quá hiếm.
3. **Horizon 72h**: quá dài, signal hết giá trị trong ngắn hạn; thử 48h trước.

## Consequences

- Số positive tăng so với v0.2 (24h) vì có thêm thời gian để giá giảm 20%.
- Lead time trung bình có thể tăng; signal vẫn hợp lệ trong 48h.
- Cần dữ liệu future đến T+48h, nên fold cuối và forward-test cutoff phải lùi thêm 24h.
- Mọi model train trên v0.2 không dùng được cho v0.3; phải train lại.

## Experiment result (2026-08-10)

- Backtest artifact: `exp_20260810_064158_c2de5e8b`
- Dataset: cùng whitelist 15 coin, ~93 ngày, 154.915 row, 19.620 positive (prevalence ~12.67%).
- Walk-forward: 3 folds valid.
- LR aggregate: **precision 0.225**, **recall 0.715**, **brier 0.223**.
- 95% CI precision: [0.165, 0.281].
- Best baseline B2 (funding_0.5): precision 0.159.
- Leakage report: passed.
- Median lead time: ~18.2h (max 48h).

### So sánh với v0.2 (24h)

| Metric | v0.2 (24h) | v0.3 (48h) | Delta |
|---|---|---|---|
| Precision mean | 0.186 | 0.225 | +0.039 |
| Recall mean | 0.574 | 0.715 | +0.141 |
| Prevalence | 8.07% | 12.67% | +4.6pp |
| Brier mean | 0.199 | 0.223 | +0.024 |
| Median lead time | 12.1h | 18.2h | +6.1h |

### Forward-test v0.3 (48h)

- Frozen model: `frozen_20260810_064748_37f0c97d`
- Train cutoff: 2026-07-25T08:34:59+07:00.
- Forward rows: 30.977, actual positives: 4.861.
- Forward precision: **0.269**, recall **0.363**, brier **0.259**.
- Validation precision (threshold tuning): 0.277.
- Precision drift: **-0.007** (dưới ngưỡng 0.1) → **không có drift đáng kể**.

So với forward-test v0.2 (precision 0.189, drift -0.155), **v0.3 48h vừa có precision cao hơn, vừa ổn định hơn ngoài mẫu**.

→ **v0.3 48h cho precision và recall tốt hơn v0.2**; nhiều nhịp giảm 20% cần 24–48h mới hoàn thành. Forward-test ổn định.

## Conditions to revisit

- Nếu forward-test v0.3 ổn định hơn v0.2 → chọn v0.3 cho production.
- Nếu precision v0.3 không cao hơn v0.2 đáng kể → giữ v0.2 hoặc thử 72h.
- Nếu recall tăng nhưng precision giảm mạnh ngoài mẫu → cân nhắc nới MAE hoặc thay đổi universe.
