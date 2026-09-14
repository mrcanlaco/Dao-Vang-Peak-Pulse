# Universe and episode-policy sensitivity — distribution v2

## Decision

This is a research-only sensitivity test. No model was frozen and no live
configuration was changed. None of the tested variants achieved positive,
stable development EV.

The least-bad development variant was locked before opening the sealed holdout:

- 24-hour pump return at least 30%;
- no liquidity exclusion;
- 24-hour per-symbol cooldown.

On the sealed holdout it produced 24 episode signals, 41.67% precision, 3.42%
recall and -1.20% conservative EV per signal. The break-even precision for the
fixed +20% / -16% / 0.20% cost payoff is 45%. It therefore remains below the
minimum economic gate.

## Protocol

- Label: fall at least 20% within 24 hours before +16% adverse excursion.
- Candidate sampling: one PIT snapshot per hour at minute 04.
- Pump universes: at least 10%, 15%, 20% or 30% trailing 24-hour return.
- Episode cooldowns: 12, 24 or 48 hours.
- Optional liquidity gate: exclude the bottom cross-sectional quartile using
  trailing 24-hour quote volume computed only from bars available at the signal.
- Market cap was not used because no reliable PIT market-cap field exists in the
  historical feature store.
- Same 5-minute bar target/stop collisions are excluded; none occurred in this
  sample.
- All fit, calibration and threshold-policy partitions are chronological and use
  a 24-hour label embargo.
- Variant selection used only three development walk-forward folds and maximized
  `mean fold EV - 0.5 * fold EV standard deviation` among variants with at least
  30 OOS episode signals.
- The final 20% of timestamps was sealed during selection and evaluated once
  after pump threshold, liquidity policy and cooldown were locked.

## Dataset and coverage

- Base PIT universe: 24,685 labeled rows, 2,188 positives, 179 symbols.
- Period: 2025-12-02 through 2026-07-31.
- Development: through 2026-06-14; sealed holdout: 2026-06-15 through 2026-07-31.
- Selected development universe: 2,368 rows, 598 positives, 49 symbols.
- Selected row coverage versus the pump >=10% base: 13.16%.
- Selected positive coverage versus the base: 40.96%.
- Selected-universe development prevalence: 25.25%.

## Selected development result

Across three OOS folds, the selected variant produced 90 episode signals, 30.00%
precision, 7.65% recall and -5.40% aggregate conservative EV per signal.
Fold EVs were -8.37%, -4.89% and -3.82%; zero of three folds were positive.
The mean fold EV was -5.69%, standard deviation 1.94%, and minimum fold EV
-8.37%.

| Fold | Signals | Precision | Recall | Conservative EV |
|---|---:|---:|---:|---:|
| 1 | 23 | 21.74% | 6.25% | -8.37% |
| 2 | 35 | 31.43% | 8.73% | -4.89% |
| 3 | 32 | 34.38% | 7.48% | -3.82% |

## Sensitivity findings

- Raising the pump threshold to 30% was the only change that consistently moved
  precision materially toward break-even. It also reduced coverage sharply.
- The PIT liquidity exclusion did not improve the selected result. Relative
  volume percentile and absolute market liquidity are different concepts; the
  experiment used trailing quote volume, not the existing per-coin volume
  percentile feature.
- A 24-hour cooldown was best only inside the 30% pump universe. Longer cooldown
  generally reduced recall without compensating precision; shorter cooldown
  created more premature episode entries.
- The sealed model ranked the very top rows reasonably (61.90% precision in the
  top 2%), but its locked episode entry rule achieved only 41.67%. This supports
  the next hypothesis: improve timing/rising-edge confirmation rather than widen
  the candidate universe.
- Sealed probability quality was weak (AP 32.51%, ROC-AUC 0.543, Brier 0.2353
  versus null Brier 0.2025). The 30%/24h setting is not production-ready despite
  being the grid winner.

## Artifacts

- Script: `scripts/universe_policy_sensitivity.py`
- Full machine-readable report: `artifacts/universe_policy_sensitivity_20260913.json`
- Cached labeled PIT dataset: `artifacts/universe_policy_v2.duckdb`
