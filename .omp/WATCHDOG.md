# Watchdog — DAO VANG review priorities

## Data integrity and lookahead bias
- Any feature builder change: verify time index is sorted ascending and the window only looks
  backward. A shift-by-1 bug leaks the future into training.
- Walk-forward splitter changes: confirm embargo gap still prevents label leakage between folds.
- DuckDB join changes: check `as-of` direction. Joins that use `>=` on future timestamps are bugs.
- Label engine changes (`labels/`): ensure the 8% drop / MAE <= 4% spec is not relaxed without
  a documented re-calibration.

## Frozen model serving
- Any edit to `scoring/frozen_inference.py`: confirm checksum verification code path is intact.
  The function `_verify_bundle_checksums` must be called before inference, not after.
- Watch for `except` blocks that swallow `FrozenInferenceError` silently — that turns
  fail-closed logic into fail-open.
- Threshold selection code: `y_test` labels must never enter `_threshold_contract`. Flag any
  function signature that passes test-fold targets to threshold logic.

## Telegram and alert delivery
- Any change touching `alerts/telegram.py` or `scanner/daemon.py` alert dispatch: verify
  `_mode_allows_tier()` is called before any send. Research mode (`operating_mode: research`)
  must never reach a real Telegram endpoint.
- Rate-limit variables (`global_daily_alert_limit`, `coin_daily_alert_limit`, `cooldown_minutes`):
  changes must be intentional and documented. Reducing limits without cause is a risk.
- Challenger comparison (`scanner/candidate_filter_comparison.py`): must never trigger sends.
  Flag any path from the challenger branch to `TelegramNotifier`.

## Self-learning guardrails
- `experiments/self_learning.py`: must not write to `scanner.frozen_model_id` in config.
  The champion model is changed only by an explicit human decision after validation.
- New challenger bundles go to `artifacts/self_learning/runs/` only.

## Config and environment isolation
- Code that reads `scanner.db_path` or `paths.data_dir`: check that dev sessions use `data/`
  not `data_live/`. A wrong path silently corrupts live data.
- Any new endpoint in `web/api_server.py`: check it does not expose raw model artifacts,
  internal file paths, or unauthenticated write access.

## Frontend / API contract
- New REST endpoints: confirm matching TypeScript type is added to `frontend/src/types.ts`.
  Type drift causes silent runtime failures in the dashboard.
- Polling interval changes in `MainWorkspace.tsx`: confirm the backend can sustain the load.
