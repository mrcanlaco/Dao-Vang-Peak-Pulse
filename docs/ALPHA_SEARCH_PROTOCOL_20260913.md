# Alpha search protocol — frozen 48h challenger

## Baseline

Every branch starts from
`configs/distribution_v2_3_research_48h_timing_compact.yaml`. A branch changes
one layer only: regime filter, episode timing, or execution/risk. It must report
the unchanged challenger on the exact same rows.

## Evidence tiers

1. **Development:** historical walk-forward folds. Variants may be ranked here.
2. **Recycled holdout:** any period whose outcomes were already opened in an
   earlier experiment, including August 2026. It may reject a fragile idea but
   cannot promote one.
3. **Future sealed forward:** data strictly after
   `2026-08-26T01:54:59.999+07:00`, collected after the complete candidate is
   frozen. Only this tier can support promotion.

A chronological slice created inside a new branch is a branch holdout, not a
globally sealed holdout, if its outcomes were previously inspected elsewhere.

## Selection controls

- Use point-in-time features only and embargo at least the 48-hour label horizon.
- Keep an explicit denominator audit for features, exact entry prices, complete
  paths, ambiguous bars and excluded rows.
- Enforce a minimum coverage floor before ranking variants.
- Penalize wide searches; report number of variants and the selection objective.
- Prefer fold median or worst-fold behavior over aggregate EV.
- A variant cannot win from one small week, one symbol cluster or lower deployed
  capital alone.
- No threshold, timing, offset, allocation or exit retuning on future sealed data.

## Required metrics

- independent episode count and temporal distribution;
- target rate/precision, episode recall and Wilson interval;
- conservative binary EV and actual-path EV after fees, slippage and funding;
- Entry 2/3 fill rates and average deployed allocation for scale-in policies;
- chronological-window EV and a clearly defined drawdown/risk metric;
- comparison with the frozen challenger on identical eligible rows.

## Promotion gates

Promotion remains disabled until at least 100 future resolved independent
episodes exist across at least three chronological windows. The candidate must
simultaneously achieve precision >=50%, episode recall >=10%, Wilson 95% lower
bound above the 45% break-even level, positive actual-path EV and positive EV in
at least three windows. A live change requires separate approval.
