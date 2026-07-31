# FEATURE SPECIFICATION v0.1

## Nguyên tắc

Mỗi feature cần:

- ID và version;
- cơ chế liên quan Distribution;
- nguồn;
- công thức;
- lookback;
- minimum observations;
- missing policy;
- point-in-time rule;
- test;
- retirement condition.

## Feature MVP dự kiến

### Price
- returns 5m/1h/4h/24h;
- rolling volatility;
- distance from rolling high;
- volume percentile;
- momentum deceleration.

### Funding
- last known raw;
- percentile 7d/30d;
- z-score 30d;
- change 8h/24h;
- persistence high funding.

### Open Interest
- change 1h/4h/24h;
- z-score/percentile;
- acceleration;
- price-OI divergence.

### Taker
- buy ratio;
- trend 1h/4h;
- change;
- price-flow divergence.

### Ratios
- global long/short;
- top trader account ratio;
- retail-top spread;
- spread trend.

## Cấm

- center rolling;
- future normalization;
- global percentile fit toàn bộ dataset;
- feature dùng label;
- feature không có business rationale.
