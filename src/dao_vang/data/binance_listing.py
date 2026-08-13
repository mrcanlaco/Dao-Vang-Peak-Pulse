"""Binance listing stats — daily snapshot of coin/symbol counts on Spot & Futures.

Persists a daily history to ``data/binance_listing_history.json`` so the app
always has data available (even when the Binance API is unreachable) and only
re-fetches once per day.

Schema of one snapshot::

    {
        "date": "2026-08-03",          # Vietnam date (YYYY-MM-DD)
        "fetched_at": "2026-08-03T...", # ISO timestamp
        "spot_symbols": 1371,
        "spot_coins": 480,
        ...
    }

The history file is a JSON list of snapshots, oldest-first, deduplicated by
``date`` (a re-scan for the same day overwrites the previous entry).
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from typing import Any

from dao_vang.logging import get_logger
from dao_vang.domain.time import system_now

logger = get_logger(__name__)

DEFAULT_HISTORY_PATH = Path("data/binance_listing_history.json")

# Endpoints
_SPOT_URL = "https://api.binance.com/api/v3/exchangeInfo"
_USDM_URL = "https://fapi.binance.com/fapi/v1/exchangeInfo"
_COINM_URL = "https://dapi.binance.com/dapi/v1/exchangeInfo"


def _http_get(url: str, timeout: float = 20.0) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "dao_vang/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def fetch_listing_stats() -> dict[str, Any]:
    """Fetch a fresh snapshot of Binance listing counts from all 3 exchanges.

    Returns an empty dict on failure.
    """
    try:
        spot = _http_get(_SPOT_URL)
        usdm = _http_get(_USDM_URL)
        coinm = _http_get(_COINM_URL)
    except Exception as e:
        logger.warning("binance_listing_stats_error", error=str(e))
        return {}

    spot_trading = [s for s in spot.get("symbols", []) if s.get("status") == "TRADING"]
    usdm_trading = [s for s in usdm.get("symbols", []) if s.get("status") == "TRADING"]
    # COIN-M uses contractStatus instead of status
    coinm_trading = [s for s in coinm.get("symbols", []) if s.get("contractStatus") == "TRADING"]

    spot_bases = {s.get("baseAsset") for s in spot_trading if s.get("baseAsset")}
    usdm_bases = {s.get("baseAsset") for s in usdm_trading if s.get("baseAsset")}
    coinm_bases = {s.get("baseAsset") for s in coinm_trading if s.get("baseAsset")}
    futures_bases = usdm_bases | coinm_bases
    all_bases = spot_bases | futures_bases

    spot_usdt = [s for s in spot_trading if s.get("quoteAsset") == "USDT"]
    usdm_usdt = [s for s in usdm_trading if s.get("quoteAsset") == "USDT"]

    now = system_now()
    return {
        "date": now.strftime("%Y-%m-%d"),
        "fetched_at": now.isoformat(timespec="seconds"),
        "spot_symbols": len(spot_trading),
        "spot_coins": len(spot_bases),
        "spot_usdt_pairs": len(spot_usdt),
        "usdm_symbols": len(usdm_trading),
        "usdm_coins": len(usdm_bases),
        "usdm_usdt_pairs": len(usdm_usdt),
        "coinm_symbols": len(coinm_trading),
        "coinm_coins": len(coinm_bases),
        "futures_coins": len(futures_bases),
        "all_coins": len(all_bases),
        "spot_only": len(spot_bases - futures_bases),
        "futures_only": len(futures_bases - spot_bases),
        "both": len(spot_bases & futures_bases),
    }


def load_history(path: Path = DEFAULT_HISTORY_PATH) -> list[dict[str, Any]]:
    """Load the full history list from disk. Returns [] if file missing/invalid."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        logger.warning("listing_history_invalid_format", path=str(path))
        return []
    except Exception as e:
        logger.warning("listing_history_load_error", error=str(e), path=str(path))
        return []


def save_history(history: list[dict[str, Any]], path: Path = DEFAULT_HISTORY_PATH) -> None:
    """Persist the history list to disk (atomic-ish write)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _upsert(history: list[dict[str, Any]], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """Insert or replace a snapshot by its `date` key, keep sorted ascending."""
    date = snapshot.get("date")
    if not date:
        return history
    new = [s for s in history if s.get("date") != date]
    new.append(snapshot)
    new.sort(key=lambda s: s.get("date", ""))
    return new


def run_daily_scan(path: Path = DEFAULT_HISTORY_PATH, max_days: int = 365) -> dict[str, Any]:
    """Fetch a fresh snapshot and append to history (overwriting same-day entry).

    Returns the snapshot dict (empty on failure). Trims history to ``max_days``
    most recent entries to avoid unbounded growth.
    """
    snapshot = fetch_listing_stats()
    if not snapshot:
        return {}
    history = load_history(path)
    history = _upsert(history, snapshot)
    if len(history) > max_days:
        history = history[-max_days:]
    save_history(history, path)
    logger.info(
        "listing_daily_scan_saved",
        path=str(path),
        date=snapshot["date"],
        history_size=len(history),
    )
    return snapshot


def get_latest_snapshot(path: Path = DEFAULT_HISTORY_PATH) -> dict[str, Any]:
    """Return the most recent snapshot from history, or {} if none."""
    history = load_history(path)
    if not history:
        return {}
    return history[-1]


def get_stats_for_today(
    path: Path = DEFAULT_HISTORY_PATH,
    auto_scan: bool = True,
) -> dict[str, Any]:
    """Return today's snapshot, fetching it if missing.

    - If history already has a snapshot for today (UTC+7) → return it (no API call).
    - Else if ``auto_scan`` → fetch fresh, persist, return it.
    - Else → return latest available snapshot (could be from a previous day).
    """
    today = system_now().strftime("%Y-%m-%d")
    history = load_history(path)
    if history:
        latest = history[-1]
        if latest.get("date") == today:
            return latest

    if auto_scan:
        snapshot = run_daily_scan(path)
        if snapshot:
            return snapshot

    # Fall back to whatever we have
    return history[-1] if history else {}


def is_today(snapshot: dict[str, Any]) -> bool:
    """Check whether a snapshot is from today (UTC+7)."""
    if not snapshot:
        return False
    return snapshot.get("date") == system_now().strftime("%Y-%m-%d")
