# Forward 48h timing reconstruction — August 2026

## Decision

The locked timing state machine improves precision over first-crossing, but it
does **not** clear the trading or promotion gates. Keep it research-only.

| Policy | Evaluable signals | TP | Precision | Wilson 95% | Episode recall | Conservative EV |
|---|---:|---:|---:|---:|---:|---:|
| Locked timing champion | 36 | 14 | 38.89% | 24.78%–55.14% | 7.33% | -2.20% |
| Pre-registered first-crossing baseline | 61 | 20 | 32.79% | 22.34%–45.28% | 10.47% | -4.40% |

The champion trades 41% less often and improves precision by 6.10 percentage
points and EV by 2.20 percentage points. It remains below the 45% break-even
precision and catches fewer positive episodes.

## Locked policy

- 24h pump must causally reach at least 30%.
- Two consecutive probability confirmations.
- Pump episode must be at least four hours old.
- No required probability pullback, local-price reversal, or drawdown gate.
- One Entry 1 per six-hour-separated episode and a 24-hour symbol cooldown.
- Model threshold: 0.39.
- Policy lock SHA-256: `ba8ccac68fb824a952b60c998d5b0ff86977119d85692626adde7fb9f7371305`.

This policy was selected from 144 causal state-machine variants using four
fold-specific historical OOS probability streams. Only labels whose 48-hour
resolution was knowable before 1 August were allowed. Historical OOS result:
139 signals, 50 TP, 35.97% precision, 17.36% episode recall and -3.25% EV.

## August protocol and coverage

The policy and research model were hashed before August outcome loading.
August labels did not participate in model fitting, calibration, threshold or
timing-policy selection. This is nevertheless a post-hoc strict-OOS
reconstruction, not a model that was literally running live on 1 August.

- 5,703 hourly pump candidates in `feature_results`.
- 5,703 exact Entry-1 price matches in `live.kline` (100%).
- 5,074 candidates had a resolvable 48-hour path (88.97%).
- 629 were incomplete because the live kline snapshot ends on 26 August.
- 40 champion signals were selected; 36 resolved and four remain excluded.
- 518 candidate episodes, including 191 positive episodes.
- 155 positive episodes received no Entry 1; 22 had an Entry 1 at a losing time.

`quant_master` matched only 125/5,703 exact August candidate snapshots, so it
is reported as a coverage audit only and was not used for entry prices or
outcome labels.

## Weekly stability

| ISO week | Evaluable signals | TP | Precision | EV |
|---|---:|---:|---:|---:|
| 2026-W31 | 1 | 0 | 0.00% | -16.20% |
| 2026-W32 | 20 | 5 | 25.00% | -7.20% |
| 2026-W33 | 8 | 4 | 50.00% | +1.80% |
| 2026-W34 | 7 | 5 | 71.43% | +9.51% |
| 2026-W35 | 0 | 0 | no coverage | n/a |

The late-period improvement is interesting but not stable evidence: sample
sizes are small and the aggregate Wilson lower bound is only 24.78%.

## Promotion audit

Promotion failed: fewer than 100 evaluable signals, precision below 50%, and
the Wilson lower bound below the 45% break-even threshold. Live configuration
was not changed.

Artifacts:

- `artifacts/forward48_timing_20260913/forward48_timing_lock.json`
- `artifacts/forward48_timing_20260913/forward48_timing_locked_forward_report.json`
- `artifacts/forward48_timing_20260913/forward48_timing_august_signals_live.csv`
- `artifacts/forward48_timing_20260913/forward48_timing_historical_grid.csv`
