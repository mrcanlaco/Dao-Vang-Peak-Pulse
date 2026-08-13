---
document_id: ADR-008
status: experimental
decision_date: 2026-08-10
author: Integrator
related: LABEL_SPECIFICATION_v0.2.md, WORK_BOARD.md
---

# ADR-008: Label Distribution v0.2 — Target 20% / MAE 10% cho volatile altcoins

## Status

Experimental — cần backtest và forward test trước khi promote.

## Context

Label v0.1 (8% drawdown / 24h, MAE ≤ 4%) trên BTCUSDT 90 ngày chỉ tạo ra ~602 positive rows (prevalence 1.63%) và tập trung vào 1 sự kiện, không đủ để train/validate mô hình một cách ổn định. Multi-coin volatile scan cho thấy các altcoin biến động mạnh có nhiều event hơn hẳn.

WORK_BOARD đề xuất v0.2 theo hướng **giảm** target drawdown (8% → 5–6%) để tăng số lượng positive. Tuy nhiên, sau phân tích dữ liệu scan volatile, nhóm muốn thử nghiệm ngược lại: **tăng target lên 20%** để chỉ bắt những nhịp xả lớn thực sự, đồng thời nới MAE lên 10%, và **giới hạn train trên các altcoin biến động lớn trong ngày**, loại BTC/ETH/top cap ra.

## Decision

Triển khai **Label Distribution v0.2**:

- `target_drawdown`: **0.20** (20%)
- `maximum_adverse_excursion`: **0.10** (10%)
- `maximum_horizon`: **24h**
- `interval`: 5 phút
- `signal_price_field`: close của nến đã đóng
- Universe: các altcoin trong **multi-coin volatile scan**, lọc theo biến động 24h và volume; loại BTCUSDT, ETHUSDT và các coin top-cap / low-volatility.
- Ngưỡng tối thiểu để đưa một coin vào tập train: **≥ 500 positive labels** trong cửa sổ dữ liệu hiện có (khoảng 90 ngày).

## Alternatives considered

1. **Giảm target xuống 5–6%** (WORK_BOARD đề xuất): tăng số positive, nhưng sẽ bắt cả những nhịp giảm nhỏ, dễ nhầm với noise.
2. **Giữ target 8%, kéo dài horizon 48–72h**: không giải quyết vấn đề BTC 90 ngày vẫn ít event.
3. **Target 20% + horizon 48h**: có thể tăng positive nhưng làm thay đổi định nghĩa “short-term distribution”. Quyết định giữ 24h trước, nếu thiếu data mới xem xét 48h.

## Consequences

- Số lượng positive giảm đáng kể so với v0.1 (khoảng 5x trên cùng universe), nhưng các altcoin biến động vẫn đủ positive để train.
- Mô hình Logistic Regression frozen hiện tại (train trên v0.1) **bị vô hiệu hóa**; phải train lại hoàn toàn.
- Scorer heuristic runtime (composite 0–100) chưa liên kết với label v0.2; nếu promote cần recalibrate ngưỡng cảnh báo.
- Cần viết lại `LABEL_SPECIFICATION_v0.2.md`, update `DECISION_LOG.md`, và lưu artifact experiment mới.

## Experiment result (2026-08-10)

- Backtest artifact: `exp_20260810_062343_f238d251`
- Dataset: 15 volatile altcoin whitelist, ~93 ngày, 157.507 row, 12.706 positive (prevalence ~8.07%).
- Walk-forward: 3 folds valid.
- LR aggregate: **precision 0.186**, **recall 0.574**, **brier 0.199**.
- 95% CI precision: [0.115, 0.258].
- Best baseline B1 (price_ret_0.05): precision 0.107.
- Leakage report: passed.
- Median lead time: ~12.1h.

### Forward-test

- Frozen model: `frozen_20260810_064047_4ecfda88`
- Train cutoff: 2026-07-28T05:39:59+07:00 (~85% data).
- Forward rows: 23.621, actual positives: 1.510.
- Forward precision: **0.189**, recall **0.543**, brier **0.251**.
- Validation precision (used to tune threshold): 0.345.
- Precision drift: -0.155 (> 0.1) → **forward precision không ổn định so với validation**.

→ Model **vượt baseline** trên nhãn v0.2, nhưng precision thấp và forward-test có drift. Cần forward test dài hơn, nhiều dữ liệu hơn, hoặc thử horizon 48h (ADR-009) trước khi promote.

## Conditions to revisit

- Nếu số coin đạt ≥ 500 positive < 10 coin sau 90 ngày data → bỏ hoặc chuyển sang target 15%.
- Nếu precision LR không vượt baseline ngoài mẫu (forward test) → xem xét horizon 48h hoặc universe rộng hơn.
