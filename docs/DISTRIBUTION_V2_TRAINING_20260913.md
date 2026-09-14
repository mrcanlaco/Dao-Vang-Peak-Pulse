# Distribution signal v2 — training result (2026-09-13)

## Decision

The v2 LightGBM challenger remains **research-only**. It was not frozen and no
production configuration was changed.

## Contract

- Universe: serving-compatible pump candidates with 24h return >= 15%, sampled hourly.
- Success: price falls at least 20% within 24 hours before moving 16% against the short.
- Same-bar target/stop: excluded because 5-minute OHLC cannot establish intrabar order.
- Signal counting: first qualifying signal per symbol, then a 24-hour cooldown.
- Costs for the promotion EV gate: 0.20% round trip.

## Dataset

- PIT candidate rows: 12,578 across 146 symbols.
- Positive labels: 1,770 (14.07%).
- History: 2025-12-02 through 2026-07-31.
- OOS rows across four expanding folds: 9,114.
- Fit, probability calibration, threshold policy and test windows are chronological,
  with a 24-hour label embargo between fit/calibration/policy and before each OOS fold.

## OOS result

| Metric | LightGBM v2 | Logistic baseline |
|---|---:|---:|
| Average precision | 24.49% | 20.08% |
| AP lift over prevalence | 1.72x | 1.41x |
| ROC-AUC | 0.676 | 0.590 |
| Brier score | 0.1194 | 0.1234 |
| Episode signals | 314 | 311 |
| Episode precision | 15.61% | 16.40% |
| Episode recall | 3.78% | 3.93% |
| Conservative EV per signal | -10.58% | -10.30% |

LightGBM ranks candidates better than the linear baseline, but that ranking does
not yet identify the correct **entry timing**. Row-level precision before episode
dedup was 34.55%; after applying the production-like 24-hour rising-edge rule it
fell to 15.61%. This indicates that later rows inside a long pump episode often
contain the useful information, while the first entry is still premature.

Only one of four OOS folds had positive conservative EV. Promotion failed the
precision, recall, aggregate EV and three-positive-fold gates. The production
model therefore remains unchanged.

## Artifacts

- Final report: `artifacts/research_models/distribution_v2_20260913_130613/report.json`
- Research estimator/calibrator: same directory as the report.
- OOS predictions: `oos_lightgbm.csv` and `oos_logistic_regression.csv`.
- Cached labeled dataset: `artifacts/distribution_v2_training.duckdb`.

## Next experiment

The next challenger should model **entry timing inside a pump episode**, not only
whether a 20% decline eventually occurs. Train an episode-aware hazard/ranking
target on consecutive candidate snapshots, then choose Entry 1 from the first
local probability peak or confirmed reversal. Keep Entry 2/3 and average-price
outcomes in the separate execution-policy backtest so signal quality and sizing
are not mixed during model fitting.
