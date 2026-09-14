# Forward48 regime/context filter research — 2026-09-14

## Kết luận

Development chọn **`btc_not_hot`** sau coverage floors và multiple-testing penalty. Fold 4 chỉ là `recycled_branch_holdout`; August là `recycled_audit`. Không kết quả nào trong báo cáo này là sealed-forward/promotion evidence.

## Protocol

- Frozen timing: pump peak >=30%, age >=4h, 2 confirmations, threshold 0.39.
- Frozen execution: 0/+3/+6, allocations 20/30/50, 6h scale-in, TP -20%, stop +16%, horizon 48h.
- Folds 1–3: development and selection; fold 4: recycled branch holdout; August: opened recycled audit.
- Eligibility: >=35% development coverage, >=20 signals total, >=5 signals in each development fold.
- Search: 21 predeclared variants including baseline; EV standard-error penalty sqrt(2 log M), temporal-fold penalty, and simultaneous Wilson intervals.

## Baseline vs selected

| Period | Variant | n | Target | Target rate | Coverage | Actual EV | Conservative EV | Wilson 95% | MDD | EV/downside vol |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| development_folds_1_3 | `baseline` | 109 | 42 | 38.53% | 100.00% | -0.74% | -2.33% | 29.93%–47.91% | 96.84% | -0.132411763348246 |
| development_folds_1_3 | `btc_not_hot` | 86 | 34 | 39.53% | 78.90% | -0.51% | -1.97% | 29.86%–50.10% | 93.08% | -0.09438441863403377 |
| recycled_branch_holdout_fold_4 | `baseline` | 30 | 16 | 53.33% | 100.00% | -1.57% | 3.00% | 36.14%–69.77% | 55.16% | NA |
| recycled_branch_holdout_fold_4 | `btc_not_hot` | 28 | 14 | 50.00% | 93.33% | -2.17% | 1.80% | 32.63%–67.37% | 60.76% | NA |
| recycled_august_audit | `baseline` | 36 | 20 | 55.56% | 100.00% | 0.46% | 3.80% | 39.58%–70.46% | 72.19% | 0.13159451273585296 |
| recycled_august_audit | `btc_not_hot` | 33 | 18 | 54.55% | 91.67% | 0.23% | 3.44% | 37.99%–70.16% | 72.19% | 0.06494144510545649 |

## All variants

| Variant | Eligible | Dev n | Dev target | Dev EV | Adjusted score | Fold4 n/EV | August n/EV |
|---|---:|---:|---:|---:|---:|---:|---:|
| `baseline` | True | 109 | 38.53% | -0.74% | -4.74% | 30 / -1.57% | 36 / 0.46% |
| `block_trending_bull` | True | 90 | 36.67% | -1.71% | -5.96% | 23 / -2.08% | 28 / -0.05% |
| `sideway_only` | False | 26 | 34.62% | -0.91% | -8.42% | 11 / -2.93% | 6 / -2.86% |
| `sideway_or_bear` | True | 86 | 36.05% | -1.51% | -5.80% | 23 / -2.08% | 26 / -0.98% |
| `high_vol_chop_only` | False | 4 | 50.00% | -6.12% | -20.48% | 0 / NA | 2 / 11.99% |
| `nonbull_joint_high_vol` | False | 13 | 38.46% | -4.73% | -13.62% | 1 / 19.80% | 1 / 3.96% |
| `sideway_or_joint_high_vol` | False | 38 | 34.21% | -2.66% | -8.07% | 12 / -4.04% | 7 / -1.89% |
| `btc_not_hot` | True | 86 | 39.53% | -0.51% | -4.61% | 28 / -2.17% | 33 / 0.23% |
| `btc_nonpositive` | True | 54 | 42.59% | -0.14% | -5.53% | 13 / -2.66% | 11 / -4.72% |
| `breadth_not_hot` | True | 73 | 41.10% | -0.09% | -4.62% | 22 / -3.54% | 32 / 0.79% |
| `breadth_weak` | True | 55 | 43.64% | -0.25% | -5.30% | 13 / -1.11% | 12 / 1.69% |
| `dominance_proxy_up` | True | 76 | 36.84% | -1.26% | -5.73% | 21 / -2.17% | 19 / 0.75% |
| `dominance_up_alt_hot` | True | 75 | 37.33% | -1.23% | -5.82% | 20 / -1.47% | 19 / 0.75% |
| `liquidity_10m_500m` | True | 97 | 40.21% | -1.16% | -5.64% | 26 / -0.87% | 34 / 0.37% |
| `liquidity_below_500m` | True | 102 | 39.22% | -0.97% | -5.26% | 26 / -0.87% | 34 / 0.37% |
| `funding_percentile_high` | False | 38 | 39.47% | 0.20% | -8.14% | 15 / 0.36% | 24 / 2.33% |
| `funding_exhaustion_rising` | False | 25 | 44.00% | 2.10% | -8.11% | 7 / 5.50% | 10 / 6.97% |
| `funding_exhaustion_rollover` | False | 0 | 0.00% | NA | NA | 0 / NA | 8 / 0.60% |
| `funding_oi_crowded` | False | 17 | 47.06% | 0.55% | -11.72% | 5 / 0.25% | 5 / 0.34% |
| `raw_funding_high_negative_control` | False | 22 | 36.36% | -0.90% | -9.79% | 3 / -0.78% | 10 / 4.97% |
| `ls_spread_high_negative_control` | False | 22 | 40.91% | 0.72% | -11.18% | 2 / -3.15% | 2 / 6.93% |

## Temporal stability of selected variant

| Fold | n | Target rate | Actual EV | Conservative EV | Coverage |
|---:|---:|---:|---:|---:|---:|
| 1 | 19 | 47.37% | 1.38% | 0.85% | 79.17% |
| 2 | 28 | 28.57% | -1.56% | -5.91% | 65.12% |
| 3 | 39 | 43.59% | -0.68% | -0.51% | 92.86% |
| 4 | 28 | 50.00% | -2.17% | 1.80% | 93.33% |
| 5 | 33 | 54.55% | 0.23% | 3.44% | 91.67% |

## Data audit

- Historical compact paths: 80,064 5m rows for 139 signals.
- Corrupt/unreadable all-universe kline files excluded before breadth calculation: 0.
- `btc_dominance_proxy_24h` means BTC return minus median altcoin return, not exchange/vendor BTC dominance.
- Market-cap data was unavailable point-in-time, so no market-cap filter was tested. Quote-volume liquidity was available.
- Funding/OI/LS fields come from the same historical/live feature snapshot at Entry 1; BTC/breadth/regime use only bars closed by Entry 1.
- Sequential MDD compounds overlapping signals as if traded one after another; it is a stress statistic, not a portfolio simulation.
- Conservative binary EV assigns +19.8% to every target and -16.2% to every non-target. Actual-path EV respects partial fills, timeout exits, costs and funding, so the two can disagree.

## Hypothesis provenance

Reports 01–07 and `docs/RESEARCH_LIBRARY_HYPOTHESIS_MAP_20260914.md` were used only to predeclare hypotheses. Old precision/ROI claims were not imported as evidence. `raw_funding_high` and LS spread are negative controls; high volatility is tested as an interaction rather than automatically blocked.

## Decision

No validated regime alpha was found. The development winner btc_not_hot still had negative EV and underperformed baseline on both fold 4 and August. Funding-exhaustion slices are scout hypotheses only: coverage was below the predeclared floor and temporal performance was unstable. Freeze any next scout before testing future data; only >=100 new independent resolved episodes after the frozen cutoff can support promotion.
