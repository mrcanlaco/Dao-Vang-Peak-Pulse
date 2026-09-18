"""Conservative presentation of market observations and saved signal outcomes."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any


def _timestamp(value: Any) -> datetime | None:
    try:
        if isinstance(value, datetime):
            parsed = value
        elif isinstance(value, (int, float)):
            parsed = datetime.fromtimestamp(value / 1000, timezone.utc)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def market_observation(
    ticker: dict[str, Any], scan: dict[str, Any] | None, *, now: datetime,
    max_age_minutes: float = 15,
) -> dict[str, Any]:
    """Choose the freshest timestamped quote; never substitute the saved entry."""
    observations = []
    for source, price, timestamp in (
        ("ticker", ticker.get("lastPrice"), ticker.get("closeTime")),
        ("scan", (scan or {}).get("close_price"), (scan or {}).get("scan_time")),
    ):
        observed_at = _timestamp(timestamp)
        try:
            price = float(price)
        except (ValueError, TypeError, OverflowError):
            continue
        if not math.isfinite(price) or price <= 0 or observed_at is None:
            continue
        age = (now - observed_at).total_seconds() / 60
        if age < -1:
            continue
        observations.append((observed_at, price, source, max(0.0, age)))
    if not observations:
        return dict(current_price=None, last_market_update=None,
                    market_data_status="MISSING", market_data_age_minutes=None,
                    market_data_source=None)
    observed_at, price, source, age = max(observations, key=lambda row: row[0])
    return dict(current_price=price, last_market_update=observed_at.isoformat(),
                market_data_status="FRESH" if age <= max_age_minutes else "STALE",
                market_data_age_minutes=round(age, 2), market_data_source=source)


def signal_outcome(hit: bool | None, invalidation_time: Any, *, now: datetime) -> str:
    """Expiry is not a negative outcome; unresolved evidence remains explicit."""
    if hit is True:
        return "HIT"
    if hit is False:
        return "MISS"
    deadline = _timestamp(invalidation_time)
    if deadline is None:
        return "NO_SIGNAL"
    return "EXPIRED" if deadline <= now else "ACTIVE"
