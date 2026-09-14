"""Independent live universe for v3; discovery never constitutes an Entry."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import httpx

from dao_vang.experiments.distribution_v3 import canonical, time_value
from dao_vang.labels.specs.distribution_short_v3 import TIMING
from dao_vang.scanner.watchlist import _is_stablecoin

DISCOVERY_VERSION = "market_discovery_v1"


def fetch_tickers(base_url: str) -> list[dict]:
    """Fail visibly on network failure; never label cached prices as fresh."""
    with httpx.Client(timeout=15) as client:
        response = client.get(f"{base_url.rstrip('/')}/fapi/v1/ticker/24hr")
        response.raise_for_status()
        rows = response.json()
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty or invalid market discovery response")
    return rows


def retained_entries(storage: Path, now: datetime) -> list[str]:
    """Keep collecting price paths even after an entered coin leaves gainers."""
    path = storage / "observations.sqlite"
    if not path.exists():
        return []
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as ledger:
        rows = ledger.execute("""
            SELECT o.symbol, o.timestamp, r.payload FROM observations o
            LEFT JOIN outcomes r ON o.id=r.id WHERE o.selected=1
        """).fetchall()
    return list(
        dict.fromkeys(
            symbol
            for symbol, timestamp, outcome in rows
            if now < time_value(timestamp) + timedelta(hours=49)
            and (outcome is None or json.loads(outcome)["status"] == "open")
        )
    )


def discover(
    tickers: list[dict],
    *,
    storage: Path,
    now: datetime,
    min_volume: float = 1_000_000,
    capacity: int = 150,
) -> dict:
    """Persist first-seen time and each poll; retain episodes through short dips."""
    storage.mkdir(parents=True, exist_ok=True)
    current = {}
    for ticker in tickers:
        symbol = str(ticker.get("symbol", ""))
        if not symbol.endswith("USDT") or _is_stablecoin(symbol):
            continue
        try:
            change = float(ticker["priceChangePercent"]) / 100
            price = float(ticker["lastPrice"])
            volume = float(ticker["quoteVolume"])
            source_ms = float(ticker["closeTime"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            not all(math.isfinite(v) for v in (change, price, volume, source_ms))
            or price <= 0
        ):
            continue
        if change < TIMING.min_return_24h:
            continue
        age = now.timestamp() - source_ms / 1000
        current[symbol] = {
            "symbol": symbol,
            "ticker_return_24h": change,
            "ticker_price": price,
            "volume_24h": volume,
            "ticker_time": datetime.fromtimestamp(source_ms / 1000, now.tzinfo),
            "last_seen": now,
            "market_eligible": volume >= min_volume and -60 <= age <= 900,
            "discovery_reason": "ticker_stale"
            if not -60 <= age <= 900
            else "below_volume"
            if volume < min_volume
            else "collecting",
        }
    with sqlite3.connect(storage / "discovery.sqlite") as ledger:
        ledger.executescript("""
            CREATE TABLE IF NOT EXISTS coins (symbol TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS polls (timestamp TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)
        previous = {
            symbol: json.loads(payload)
            for symbol, payload in ledger.execute(
                "SELECT symbol,payload FROM coins"
            ).fetchall()
        }
        for symbol, item in current.items():
            old = previous.get(symbol, {})
            continuous = old and now - time_value(old["last_seen"]) <= timedelta(
                hours=6
            )
            item["first_seen"] = old["first_seen"] if continuous else now
            previous[symbol] = json.loads(canonical(item))
            ledger.execute(
                "INSERT OR REPLACE INTO coins VALUES (?,?)", [symbol, canonical(item)]
            )
        tracked = [
            row
            for row in previous.values()
            if row["market_eligible"]
            and now - time_value(row["last_seen"]) <= timedelta(hours=6)
        ]
        tracked.sort(
            key=lambda row: (
                row["symbol"] not in current,
                -row["ticker_return_24h"],
                row["symbol"],
            )
        )
        pinned = retained_entries(storage, now)
        unpinned = [row["symbol"] for row in tracked if row["symbol"] not in pinned]
        selected = pinned + unpinned[: max(0, capacity - len(pinned))]
        rows = sorted(
            current.values(), key=lambda row: (-row["ticker_return_24h"], row["symbol"])
        )
        for row in rows:
            if row["market_eligible"] and row["symbol"] not in selected:
                row["discovery_reason"] = "capacity_deferred"
        payload = {
            "version": DISCOVERY_VERSION,
            "status": "running",
            "updated_at": now,
            "min_return_24h": TIMING.min_return_24h,
            "min_volume_usd": min_volume,
            "capacity": capacity,
            "market_count": len(rows),
            "collection_symbols": selected,
            "deferred_count": sum(
                row["discovery_reason"] == "capacity_deferred" for row in rows
            ),
            "first_seen": {row["symbol"]: row["first_seen"] for row in tracked},
            "items": rows,
        }
        ledger.execute(
            "INSERT OR REPLACE INTO polls VALUES (?,?)",
            [now.isoformat(), canonical(payload)],
        )
    return json.loads(canonical(payload))


def enrich(database, discovery: dict, *, now: datetime) -> dict:
    """Explain missing features without dropping the coin or imputing its return."""
    if not discovery.get("items"):
        return discovery
    symbols = [item["symbol"] for item in discovery["items"]]
    feature_source = "v3_live_features" if discovery.get("feature_source") == "v3_live_features" else "feature_results"
    if feature_source == "v3_live_features" and not database.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_name='v3_live_features'"
    ).fetchone():
        return discovery
    placeholders = ",".join("?" for _ in symbols)
    rows = database.execute(
        f"""
        SELECT symbol,feature_time,price_ret_24h FROM {feature_source}
        WHERE symbol IN ({placeholders}) AND feature_time < ?
        QUALIFY row_number() OVER (PARTITION BY symbol ORDER BY feature_time DESC)=1
    """,
        [*symbols, now],
    ).fetchall()
    latest = {symbol: (when, change) for symbol, when, change in rows}
    hourly = dict(
        database.execute(
            f"""
        SELECT symbol,max(feature_time) FROM {feature_source}
        WHERE symbol IN ({placeholders}) AND feature_time < ?
          AND EXTRACT(MINUTE FROM feature_time)=4 AND price_ret_24h >= ?
        GROUP BY symbol
    """,
            [*symbols, now, TIMING.min_return_24h],
        ).fetchall()
    )
    items = []
    for row in discovery["items"]:
        item = dict(row)
        when, change = latest.get(row["symbol"], (None, None))
        item.update(
            feature_time=when,
            feature_return_24h=change,
            hourly_feature_time=hourly.get(row["symbol"]),
        )
        if item["discovery_reason"] == "collecting":
            if when is None:
                reason = "features_pending"
            elif now - when > timedelta(minutes=15):
                reason = "features_stale"
            elif change is None or not math.isfinite(change):
                reason = "history_24h_pending"
            elif change < TIMING.min_return_24h:
                reason = "closed_return_below_15pct"
            else:
                reason = "waiting_hourly_confirmation"
            item["discovery_reason"] = reason
        items.append(item)
    return {**discovery, "features_checked_at": now, "items": items}
