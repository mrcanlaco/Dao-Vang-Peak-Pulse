# Distribution v2 version search — 2026-09-13

## Decision

No tested version is eligible for production. The best **research champion** is
the end-to-end universe policy below because it produced the strongest sealed
holdout result with more than a handful of independent episodes:

- Pump universe: 24h return >= 30%.
- PIT liquidity gate: none.
- Episode cooldown: 24 hours.
- Signal model: reference LightGBM, serving-compatible 25-feature schema.
- Probability calibration: isotonic, fit on a separate chronological partition.
- Threshold: selected on the pre-test policy partition; never on the test fold.
- Status: `research_only`; live configuration remains unchanged.

This is named `distribution_v2_1_research_pump30` for continued forward shadow
evaluation. It is not a release candidate yet.

## Common contract

- Target: price falls 20% within 24 hours.
- Failure boundary: price rises 16% before the target.
- Same 5-minute bar touches target and stop: exclude as ambiguous.
- Round-trip cost used by the conservative gate: 0.20%.
- Break-even precision under the conservative +20%/-16% payoff: 45%.
- All model inputs and liquidity filters are point-in-time.
- Fit, calibration, threshold-policy and test partitions are chronological with
  a 24-hour label embargo.

## Independent searches

| Search branch | Variants | Development result | Sealed holdout | Decision |
|---|---:|---|---|---|
| Model/calibration | 24 | Champion precision 18.78%, EV -9.44%, 229 episodes | 8 episodes, precision 37.50%, EV -2.70% | Reject |
| Universe/cooldown | 24 | Pump>=30%, cooldown 24h: 90 episodes, precision 30.00%, EV -5.40% | 24 episodes, precision 41.67%, EV -1.20% | Research champion, not deployable |
| Entry timing | 354 | Two confirmations + threshold+0.10 + 5% drawdown: 50 episodes, precision 46.00%, EV +0.36% | 0 signals; no measurable EV | Reject as overfit/no coverage |

The pre-registered timing baseline produced 11 holdout signals with five true
positives (45.45%, EV +0.164%), but the sample is below the minimum of 30 and
its development result was strongly negative. It is evidence to collect more
forward observations, not evidence to deploy.

## Why v2.1 research is the least-bad choice

Raising the pump threshold from 15% to 30% retains only 13.16% of candidate
rows while retaining 40.96% of positive labels. That materially improves the
base rate and gives 24 independent sealed-holdout signals, three times the
sample of the model-grid champion. However, it still misses break-even by 3.33
percentage points, all three development folds have negative EV, ROC-AUC on
the sealed period is only 0.543, and calibrated Brier score is worse than the
null forecast. These failures keep it out of production.

## Next validation rule

Do not create another post-hoc backtest winner on the already opened final
period. Freeze the v2.1 research policy specification and collect a new forward
shadow sample. Reconsider promotion only after at least 100 independent
episodes and all of the following hold:

- precision >= 50%;
- Wilson 95% lower bound above the 45% break-even precision;
- recall >= 10% at episode level;
- positive conservative EV in at least three chronological windows;
- calibrated Brier score better than the contemporaneous prevalence forecast.

## Evidence artifacts

- `artifacts/model_variants_20260913_151329.json`
- `artifacts/universe_policy_sensitivity_20260913.json`
- `artifacts/entry_timing_20260913/entry_timing_report.json`
- `artifacts/research_models/distribution_v2_20260913_130613/report.json`

Runners:

- `scripts/model_variants_distribution_v2.py`
- `scripts/universe_policy_sensitivity.py`
- `scripts/entry_timing_backtest.py`
