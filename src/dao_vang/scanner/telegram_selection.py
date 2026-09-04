"""Deterministic selection of the strongest Telegram candidates.

The scanner can evaluate more candidates than it should deliver.  This module
keeps delivery policy separate from scoring: only candidates that already
passed the serving/calibration gates enter the ranker, and the ranker applies a
rolling 24-hour cap plus a per-cycle cap.  A target minimum is reported for
observability only; it never weakens the fail-closed gates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class TelegramSelection:
    """Result of ranking one cycle's already-qualified alert candidates."""

    selected: list[dict[str, Any]]
    candidate_count: int
    eligible_count: int
    sent_24h: int
    daily_limit: int
    max_per_cycle: int
    target_min: int

    @property
    def projected_24h(self) -> int:
        return self.sent_24h + len(self.selected)

    @property
    def target_unmet(self) -> bool:
        return self.projected_24h < self.target_min


def _number(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def _evidence_count(item: Mapping[str, Any]) -> int:
    groups = item.get("evidence_groups")
    if isinstance(groups, Sequence) and not isinstance(groups, (str, bytes)):
        return len(groups)
    return int(max(0.0, _number(item.get("evidence_n_groups"), 0.0)))


def alert_rank_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    """Return the stable ordering used for Telegram delivery.

    Calibrated probability is the primary ranking signal.  Independent
    evidence, data quality, empirical evidence precision, heuristic score,
    liquidity and pump context break ties in that order.
    """

    symbol = str(item.get("symbol", "")).upper()
    return (
        -_number(item.get("model_probability"), -1.0),
        -_evidence_count(item),
        -_number(item.get("data_quality_score"), 0.0),
        -_number(item.get("evidence_precision"), 0.0),
        -_number(item.get("total_score"), 0.0),
        -_number(item.get("volume_24h_usd"), 0.0),
        -_number(item.get("pump_pct"), 0.0),
        symbol,
    )


def select_top_alerts(
    alerts: Sequence[Mapping[str, Any]],
    *,
    sent_24h: int,
    daily_limit: int,
    max_per_cycle: int,
    target_min: int,
    coin_sent_counts: Mapping[str, int] | None = None,
    coin_daily_limit: int = 1,
) -> TelegramSelection:
    """Deduplicate, rank and cap already-policy-qualified candidates.

    Missing/non-finite probability and non-valid quality are rejected here as
    a final defensive boundary.  ``coin_sent_counts`` is keyed by symbol and
    counts successful deliveries in the same rolling 24-hour window.
    """

    safe_daily_limit = max(1, int(daily_limit))
    safe_max_per_cycle = max(1, int(max_per_cycle))
    safe_target_min = max(0, int(target_min))
    safe_sent_24h = max(0, int(sent_24h))
    safe_coin_limit = max(1, int(coin_daily_limit))
    sent_by_symbol = {
        str(symbol).upper(): max(0, int(count))
        for symbol, count in (coin_sent_counts or {}).items()
    }

    deduplicated: dict[str, dict[str, Any]] = {}
    candidate_count = len(alerts)
    for raw in alerts:
        symbol = str(raw.get("symbol", "")).strip().upper()
        probability = _number(raw.get("model_probability"), float("nan"))
        quality_status = str(raw.get("quality_status", "valid")).lower()
        if not symbol or not math.isfinite(probability):
            continue
        if not 0.0 <= probability <= 1.0 or quality_status != "valid":
            continue
        item = dict(raw)
        item["symbol"] = symbol
        current = deduplicated.get(symbol)
        if current is None or alert_rank_key(item) < alert_rank_key(current):
            deduplicated[symbol] = item

    eligible = [
        item
        for symbol, item in deduplicated.items()
        if sent_by_symbol.get(symbol, 0) < safe_coin_limit
    ]
    eligible.sort(key=alert_rank_key)

    available = max(0, safe_daily_limit - safe_sent_24h)
    selection_limit = min(safe_max_per_cycle, available)
    selected: list[dict[str, Any]] = []
    for rank, item in enumerate(eligible[:selection_limit], start=1):
        selected_item = dict(item)
        selected_item["selection_rank"] = rank
        selected.append(selected_item)

    return TelegramSelection(
        selected=selected,
        candidate_count=candidate_count,
        eligible_count=len(eligible),
        sent_24h=safe_sent_24h,
        daily_limit=safe_daily_limit,
        max_per_cycle=safe_max_per_cycle,
        target_min=safe_target_min,
    )


__all__ = ["TelegramSelection", "alert_rank_key", "select_top_alerts"]
