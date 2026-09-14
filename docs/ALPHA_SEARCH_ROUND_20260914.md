# Alpha search round — frozen Challenger 48h

## Decision

No new alpha is validated and no live setting changed. Three independent
branches tested 74 predeclared rows/variants in total: 21 regime/context rows,
37 timing variants and 16 execution/risk variants. All started from the frozen
48h timing+compact Challenger and used the research library only to generate
hypotheses.

One narrow scout is worth freezing for future shadow evaluation:
`funding_exhaustion_rising + compact`. Its opened results are encouraging, but
coverage and statistical gates fail, so none of those results may support a
promotion.

## Results by branch

| Branch | Development selection | Recycled holdout result | Decision |
|---|---|---|---|
| Regime/context | `btc_not_hot`, EV -0.51% vs baseline -0.74% | Fold4 -2.17% vs -1.57%; August +0.23% vs +0.46% | Reject |
| Episode timing | `gap_12h`, EV -3.85% vs -4.64% conservative | Same binary signals/EV as baseline on fold4 | Reject |
| Execution/risk | volatility offsets + Entry1 exhaustion snapshot + price reversal | Actual EV +0.238% vs -1.559%; CI crosses zero, p=.188 | Risk scout only |

The execution candidate cut average deployed capital from 71.33% to 21.67%
and sequential MDD from 55.01% to 16.01% on fold 4, but only one of 30 trades
added Entry 2 and none added Entry 3. The improvement is mainly avoided
exposure, not evidence of superior scale-in timing. Development failed Holm
multiple-testing control.

## Research-library conclusions retested

- Sideway/bear gates, blocking bull, high-volatility interactions, BTC trend,
  breadth, liquidity 10M–500M and the dominance proxy did not improve robustly.
- Raw high funding and long/short spread behaved inconsistently, supporting
  their use as negative controls rather than standalone triggers.
- Shorter 12/24/36h time stops all underperformed 48h for the -20% target.
- Longer scale-in windows, mechanical back-loading, partial TP at -10% and
  standalone risk-normalized sizing did not produce stable gains.
- `gap_12h` merely removed a few duplicated/nearby signals and produced no
  holdout binary delta.

These results also resolve several contradictions in the archived reports:
Regime Gate previously reduced alert volume more reliably than it increased
precision; high volatility is not equivalent to high-volatility chop; and the
later report's zero importance for smart-money/LS features is more consistent
with the new negative-control results than the earlier whale-divergence claim.

## Funding-exhaustion scout

The point-in-time gate is:

- funding percentile over 30 days >=80%;
- funding persistence over seven days >0;
- funding change over eight hours >0 at Entry 1;
- all other frozen timing and compact execution rules unchanged.

| Opened period | n | Target rate | Actual-path EV |
|---|---:|---:|---:|
| Development folds 1–3 | 25 | 44.00% | +2.202% |
| Recycled fold 4 | 7 | 71.43% | +5.516% |
| Recycled August | 10 | 80.00% | +6.969% |

This is not validated alpha: development coverage is only 22.9%, fold 3 lost
6.24%, the adjusted multiple-testing score failed, and fold4/August samples
are tiny and already opened. The scout is frozen only to prevent later tuning.

## Why waiting for a true funding rollover did not help

The first execution candidate used funding/momentum from the Entry-1 snapshot;
only its price reversal was intratrade. A separate feasibility test then used
later stored feature rows and required both `funding_change_8h <= 0` and a lower
funding rate than at Entry 1 before adding.

Strict transition coverage improved from 44–60% with a 6h window to 64–90%
with 12h. Nevertheless, compact beat the 12h transition rule in absolute EV on
development (+2.202% vs +0.882%), fold4 (+5.516% vs +4.846%) and August
(+6.969% vs +0.153%). Waiting discarded the weighted-average benefit. Predicted
funding was not tested because it is not persisted point-in-time.

## Evidence discipline and next test

All historical/August slices are recycled or branch holdouts, not globally
sealed evidence. The only future scout eligible for a new forward test is
`configs/distribution_v2_4_research_48h_funding_scout.yaml`. Keep the parent
Challenger alongside it on identical rows and do not tune either.

Wait for at least 100 newly resolved scout signals across three chronological
windows. Promotion requires positive actual and conservative EV, precision
>=50%, episode recall >=10%, Wilson lower bound above 45%, and a positive paired
EV lower confidence bound. Any live change remains a separate decision.

## Artifacts

- `docs/RESEARCH_LIBRARY_HYPOTHESIS_MAP_20260914.md`
- `docs/forward48_regime_context_20260914.md`
- `artifacts/forward48_episode_timing_alpha_20260914/report.md`
- `artifacts/forward48_execution_risk_20260914/report.md`
- `artifacts/forward48_funding_execution_compatibility_20260914/report.md`
- `artifacts/forward48_true_funding_transition_20260914/report.md`
