"""Public market evidence for follow-up and paper journals; no order API."""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from dao_vang.scanner.tracking_evidence import _timestamp

FIVE_MINUTES_MS = 300_000


def public_data(path: str, params: dict[str, Any]) -> list[Any]:
    with httpx.Client(timeout=10) as client:
        response = client.get(f"https://fapi.binance.com/fapi/v1/{path}", params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("Market history unavailable")
    return payload


def reference_price(symbol: str, at: datetime) -> dict[str, Any]:
    end = int(at.timestamp() * 1000)
    rows = public_data("klines", {"symbol": symbol, "interval": "5m", "endTime": end, "limit": 2})
    closed = [row for row in rows if int(row[6]) <= end and 0 <= end - int(row[6]) <= FIVE_MINUTES_MS]
    if not closed:
        raise ValueError("No closed reference candle")
    row = max(closed, key=lambda candle: int(candle[6]))
    price = float(row[4])
    if not math.isfinite(price) or price <= 0:
        raise ValueError("Invalid reference price")
    return {"source_price": price, "source_price_time": datetime.fromtimestamp(int(row[6]) / 1000, timezone.utc).isoformat(),
            "source_price_evidence": "binance_closed_5m"}


def checkpoint(entry: dict[str, Any], hours: int, rows: list[Any], now: datetime) -> dict[str, Any]:
    """Describe a full contiguous path, separately from the model outcome label."""
    start = _timestamp(entry.get("source_price_time"))
    price = entry.get("source_price")
    if start is None or not price or entry.get("source_price_evidence") != "binance_closed_5m":
        return {"status": "MISSING", "reason": "reference_unverified"}
    end = start + timedelta(hours=hours)
    if now < end:
        return {"status": "PENDING", "due_at": end.isoformat()}
    first_open = int(start.timestamp() * 1000) + 1
    expected = [first_open + i * FIVE_MINUTES_MS for i in range(hours * 12)]
    candles: dict[int, list[Any]] = {}
    try:
        for row in rows:
            opened = int(row[0])
            if opened not in range(first_open, first_open + hours * 3_600_000):
                continue
            if opened in candles and candles[opened] != row:
                return {"status": "MISSING", "reason": "conflicting_candles"}
            values = [float(row[i]) for i in (1, 2, 3, 4)]
            if not all(math.isfinite(v) and v > 0 for v in values) or int(row[6]) != opened + FIVE_MINUTES_MS - 1:
                return {"status": "MISSING", "reason": "invalid_candles"}
            if not values[2] <= min(values[0], values[3]) <= max(values[0], values[3]) <= values[1]:
                return {"status": "MISSING", "reason": "invalid_candles"}
            candles[opened] = row
    except (ValueError, TypeError, IndexError, OverflowError):
        return {"status": "MISSING", "reason": "invalid_candles"}
    if sorted(candles) != expected:
        return {"status": "MISSING", "reason": "price_gaps", "observed": len(candles), "expected": len(expected)}
    ordered = [candles[t] for t in expected]
    return {"status": "READY", "at": end.isoformat(), "price": float(ordered[-1][4]),
            "return_pct": (float(ordered[-1][4]) / price - 1) * 100,
            "max_rise_pct": (max(float(row[2]) for row in ordered) / price - 1) * 100,
            "max_drop_pct": (1 - min(float(row[3]) for row in ordered) / price) * 100,
            "candle_count": len(ordered), "source": "binance_closed_5m"}


def fetch_checkpoint(entry: dict[str, Any], hours: int, now: datetime) -> dict[str, Any]:
    start = _timestamp(entry.get("source_price_time"))
    if start is None or now < start + timedelta(hours=hours):
        return checkpoint(entry, hours, [], now)
    rows = public_data("klines", {"symbol": entry["symbol"], "interval": "5m",
                                 "startTime": int(start.timestamp() * 1000) + 1,
                                 "endTime": int((start + timedelta(hours=hours)).timestamp() * 1000), "limit": 1000})
    return checkpoint(entry, hours, rows, now)


def funding_cashflow(trade: dict[str, Any], rows: list[Any], closed_at: datetime) -> dict[str, Any]:
    start = _timestamp(trade["opened_at"])
    if start is None or len(rows) >= 1000:
        return {"status": "MISSING", "cashflow": None}
    total = 0.0
    seen: dict[int, tuple[float, float]] = {}
    try:
        for row in rows:
            settled = int(row["fundingTime"])
            if not start.timestamp() * 1000 < settled < closed_at.timestamp() * 1000:
                continue
            rate, mark = float(row["fundingRate"]), float(row["markPrice"])
            if not math.isfinite(rate) or not math.isfinite(mark) or mark <= 0:
                raise ValueError("invalid settlement")
            if settled in seen:
                if seen[settled] != (rate, mark):
                    raise ValueError("conflicting settlement")
                continue
            seen[settled] = (rate, mark)
            total += trade["quantity"] * mark * rate * (-1 if trade["side"] == "LONG" else 1)
    except (ValueError, TypeError, KeyError, OverflowError):
        return {"status": "MISSING", "cashflow": None}
    return {"status": "VERIFIED", "cashflow": total, "settlements": len(seen),
            "source": "binance_funding_history", "through": closed_at.isoformat()}


def fetch_funding(symbol: str, trade: dict[str, Any], closed_at: datetime) -> dict[str, Any]:
    start = _timestamp(trade["opened_at"])
    if start is None:
        return {"status": "MISSING", "cashflow": None}
    try:
        rows = public_data("fundingRate", {"symbol": symbol, "startTime": int(start.timestamp() * 1000) + 1,
                                          "endTime": int(closed_at.timestamp() * 1000) - 1, "limit": 1000})
        return funding_cashflow(trade, rows, closed_at)
    except (httpx.HTTPError, ValueError, OSError):
        return {"status": "MISSING", "cashflow": None}
