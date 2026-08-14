# Post-MVP scanner, alerting, composite scoring and dashboard scope

## Status
Approved — documents scope already implemented in code, not yet reflected in `01_Product/MVP_SCOPE.md` v1.0.

## Context
`01_Product/MVP_SCOPE.md` §7 ("Ngoài phạm vi") lists real-time signals,
dashboard, Telegram/Discord alerts, and AI/LLM as explicitly out of MVP
scope. In practice, the codebase already implements all of these
(`src/dao_vang/scanner/daemon.py`, `src/dao_vang/alerts/`,
`src/dao_vang/scoring/distribution_scorer.py`, `src/dao_vang/web/`) and has
been running as a 24/7 process. This ADR formally records that expansion so
future changes are evaluated against an accurate scope, per Constitution §9
("Code không phải nguồn chân lý nếu trái specification") and the pending
`phase3/DOCUMENTATION_V1_1_PLAN.md` task `P3-DOC-AUDIT-001`.

This ADR does **not** change Constitution §5 principle #9 ("Không tự động
giao dịch"). Auto-trading, order execution, and exchange API keys remain
explicitly out of scope. The system remains decision-support only: it
produces watchlist entries and Telegram alerts; a human decides whether and
how to trade.

## Decision
1. Formally bring into scope (post-MVP, not "MVP" per `MVP_SCOPE.md`):
   - 24/7 scanner daemon (`scanner.daemon.ScannerDaemon`) polling Binance on
     a configurable interval and scanning a dynamic symbol list (manual
     watchlist + auto market scan by mode).
   - Composite heuristic distribution scorer
     (`scoring.distribution_scorer.compute_distribution_score`) as the
     production alerting signal, in addition to the frozen
     walk-forward-validated ML model path (`experiments.forward_test`).
   - Telegram alerting (`alerts.telegram.TelegramNotifier`).
   - Full audit trail of every scored symbol, not only alerted ones
     (`scanner.scan_results_store.ScanResultStore`), and of every alert plus
     its resolved outcome (`alerts.store.AlertStore`).
   - Web dashboard (React `frontend/` + real-data backend
     `web/api_server.py`) for reviewing signals, scanner health, and
     historical accuracy. Streamlit (`web/app.py`) is deprecated in favor of
     this once feature parity is reached (see Phase 5 of the production
     readiness plan).
2. The composite heuristic scorer is **not** currently statistically
   validated against Label v0.1 (fixed hand-tuned weights). It MUST be
   backtested against historical labels (Constitution Khối 7) before its
   output is treated as more than an unvalidated heuristic. Until validated,
   every alert must carry `evidence_precision` — the *empirical* rolling
   precision computed from resolved outcomes (`AlertStore.precision_by_risk_level`)
   — so users see real track record, not just the raw heuristic score.
3. Self-learning is retrain-with-human-approval, not fully autonomous:
   outcomes are resolved automatically (`scanner.outcomes.resolve_pending_outcomes`),
   but promoting a new frozen model to production requires an explicit
   human approval step (Constitution §5 principle #10 — "AI không được thay
   thế kiểm chứng thống kê").

## Consequences
- `01_Product/MVP_SCOPE.md` should be superseded by a Documentation v1.1
  revision reflecting this scope (tracked separately, not blocking this ADR).
- Any new scanner/alert/scoring feature must be justified against the same
  Constitution §1 criteria (precision, recall, false positives, calibration,
  stability, explainability, data quality) as core MVP features — post-MVP
  status does not exempt a feature from scrutiny.
- Auto-trading remains a separate, not-yet-approved decision requiring its
  own ADR if ever proposed.
