# Horizon sensitivity: 24h vs 48h vs 72h

## Decision

The 48-hour horizon is the strongest **research challenger**, but it is not yet
eligible for production. The 72-hour horizon improves recall but loses too much
precision and remains negative EV.

Each horizon was trained and calibrated against its own target-before-stop
label. The embargo was also increased to match the label horizon (24/48/72h).
Universe, liquidity and cooldown variants were selected only on three
development folds before the sealed period was evaluated.

| Horizon | Selected policy | Development | Sealed holdout | Wilson 95% precision |
|---|---|---|---|---|
| 24h | pump>=30%, cooldown 24h | 90 signals, P 30.00%, R 7.65%, EV -5.40% | 24 signals, P 41.67%, R 3.42%, EV -1.20% | 24.47%-61.17% |
| 48h | pump>=15%, cooldown 24h | 117 signals, P 29.91%, R 3.50%, EV -5.43% | 64 signals, P 56.25%, R 4.16%, EV +4.05% | 44.09%-67.71% |
| 72h | pump>=30%, cooldown 24h | 130 signals, P 33.85%, R 10.38%, EV -4.02% | 111 signals, P 39.64%, R 10.21%, EV -1.93% | 31.03%-48.94% |

The conservative break-even precision is 45% for +20% target, -16% stop and
0.20% round-trip costs.

## Interpretation

- 48h catches a useful group of delayed distributions in the final regime.
- Its 95% lower confidence bound is still just below break-even.
- All three 48h development folds are negative EV (-5.99%, -5.53%, -3.68%).
  Therefore the positive holdout result is not yet regime-stable.
- 72h raises target prevalence and recall, but adds too many late false entries
  or stop-before-target cases; it should not replace 48h.
- Because the three horizons have now been compared on the same final period,
  choosing 48h is itself a research selection. A new forward sample is required
  before any production claim.

## Research candidate

`distribution_v2_2_research_48h`:

- pump return over 24h >=15%;
- 48h invalidation horizon;
- hard stop/MAE +16%;
- target -20% before stop;
- no additional liquidity gate;
- one Entry 1 per episode, 24h cooldown;
- reference LightGBM with the existing 25 serving features;
- chronological fit/calibration/policy partitions with 48h embargo.

Keep it shadow-only until at least 100 new independent episodes are resolved,
precision is at least 50%, the Wilson 95% lower bound is above 45%, and EV is
positive in at least three chronological windows.

## Artifacts

- `artifacts/universe_policy_sensitivity_20260913.json`
- `artifacts/universe_policy_sensitivity_48h_20260913.json`
- `artifacts/universe_policy_sensitivity_72h_20260913.json`
- Dataset caches use the matching `universe_policy_v2_<horizon>h.duckdb` names.
