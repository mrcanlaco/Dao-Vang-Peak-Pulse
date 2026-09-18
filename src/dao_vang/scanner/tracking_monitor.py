"""Bounded follow-up worker owned by the web process, independent of page visits."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from dao_vang.scanner.tracking_evidence import _timestamp, market_observation
from dao_vang.scanner.tracking_market import fetch_checkpoint, fetch_funding
from dao_vang.scanner.tracking_watchlist import TrackingWatchlistStore
from dao_vang.scanner.watchlist import fetch_all_tickers

logger = logging.getLogger(__name__)


def refresh_tracking(store: TrackingWatchlistStore, *, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    entries = sorted(store.list(include_archived=True), key=lambda item: item.get("monitor_checked_at") or "")
    if not entries:
        return 0
    tickers = {row["symbol"]: row for row in fetch_all_tickers()}
    refreshed = 0
    history_requests = 0
    for entry in entries:
        last_check = _timestamp(entry.get("monitor_checked_at"))
        if last_check and (now - last_check).total_seconds() < 60:
            continue
        if refreshed >= 20:
            break
        results = {}
        for hours in (24, 48):
            old = entry.get("checkpoints", {}).get(str(hours), {})
            checked_at = _timestamp(old.get("checked_at"))
            if old.get("status") == "READY" or (checked_at and (now - checked_at).total_seconds() < 3600):
                continue
            if history_requests >= 4:
                break
            history_requests += 1
            try:
                result = fetch_checkpoint(entry, hours, now)
            except Exception:
                logger.warning("tracking_history_unavailable symbol=%s", entry["symbol"])
                result = {"status": "MISSING", "reason": "history_unavailable"}
            results[str(hours)] = {**result, "checked_at": now.isoformat()}
        observation = market_observation(tickers.get(entry["symbol"], {}), None, now=now)
        store.monitor(entry["id"], observation, results, now=now)
        trade = entry.get('paper_trade') or {}
        closed_at = _timestamp(trade.get('closed_at'))
        checked = _timestamp(trade.get('funding_checked_at'))
        if closed_at and trade.get('funding', {}).get('status') != 'VERIFIED' and (checked is None or (now - checked).total_seconds() >= 3600):
            store.reconcile_funding(entry['id'], fetch_funding(entry['symbol'], trade, closed_at), now=now)
        refreshed += 1
    return refreshed


def start_tracking_monitor(store: TrackingWatchlistStore) -> threading.Event:
    stop = threading.Event()

    def run() -> None:
        while not stop.is_set():
            try:
                refresh_tracking(store)
            except Exception:
                logger.exception("tracking_monitor_failed")
            stop.wait(60)

    threading.Thread(target=run, name="tracking-monitor", daemon=True).start()
    return stop
