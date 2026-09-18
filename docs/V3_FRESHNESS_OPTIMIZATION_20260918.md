# V3 freshness optimization — 18 September 2026

Production inspection at 06:31 Asia/Saigon found 13–21 minute scanner cycles,
discovery older than the existing 15-minute freshness limit, and radar features
several hours behind. Binance requests succeeded; there was no persisted rate
limit cooldown. Backfill repeatedly exhausted its cycle budget.

## Changes

- Scanner materializes the existing deduplicated ingestion source queries once
  per cycle. Alignment, scoring and statistics reuse those same rows. Other
  callers of `build_raw_timeline` retain the existing view mode by default.
- System statistics enumerate persistent tables only. They exclude temporary
  relations, `bf_*` working tables and views such as `v3_runtime_prices` that
  used to repeat expensive Parquet scans. The snapshot declares its scope as
  `persistent_tables`; removed working relations are not fabricated as zeroes.
- Backfill inventories each source kind once per pass, routes hashed legacy
  backfills using Parquet footer metadata and caches that metadata by file
  version. Unknown, mixed-symbol and invalid files stay eligible. Downloads
  register directly with the inventory; neither receipt provenance nor original
  timestamps are rewritten. File pruning stays anchored to the evaluated window.
- Current radar precedes retained off-radar coins. Actual processing attempts
  determine rotation; display updates and jobs that received no request budget
  do not consume a turn. Per-coin request limits prevent one large gap consuming
  the complete pass. Retry-After/global cooldown and exponential backoff remain.
- Defaults are 64 range requests, 90 seconds to start work, and 8 requests per
  symbol per pass. The deadline is checked before loading another symbol as well
  as before requests. Already-running IO/materialization can finish after it.
- `discovery.backfill_cycle` reports elapsed time, request count, attempted and
  ready symbols, and explicit deferral reasons: time budget, request budget,
  per-symbol budget, rate limit, or retry backoff.
- A new ticker pass preserves the last validated feature/return and last
  completed backfill metrics, with their original timestamps. Their freshness
  still expires after 15 minutes. New episodes do not inherit old feature cards.
- Scanner logs phase durations and writes heartbeats at completed phase
  boundaries. The 15-minute data freshness threshold is unchanged; an alive
  process does not make old market/features fresh.
- Prediction-outcome maintenance intersects the historical backlog with exact
  signal keys present in the current timeline, and skips metrics for labels
  whose future window is incomplete. Absent signals remain pending, not losses
  or exclusions; a later historical-data run can still resolve them. This
  removes thousands of repeated queries on every maintenance cycle/startup.

## Invariants and verification

No model, thresholds, episode/confirmation timing, observation ledger or Entry
rules change. Source materialization is tested against the existing timeline
values. Regression tests cover real collectors and normalizers through feature
materialization, late hourly scans, restart/resume, no duplicate downloads,
backoff, quality rejection and no historical confirmation replay. Additional
tests cover file routing/cache invalidation, bounded inventory traversal,
radar priority, fair rotation after restart, time-budget termination, and
statistics that must never evaluate expensive views.

A read-only GCP inventory benchmark over 27 tracked symbols and approximately
282,000 source files took 7.7 seconds cold and 4.5 seconds warm. This measures
source selection only, not a complete scanner cycle; deployment acceptance
requires actual cycle durations and fresh radar features across live passes.
