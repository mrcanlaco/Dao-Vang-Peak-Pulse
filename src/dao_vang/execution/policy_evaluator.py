"""Deterministic, point-in-time evaluator for frozen scale-in templates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from dao_vang.config.settings import ScaleInTemplateConfig


@dataclass(frozen=True, slots=True)
class PriceBar:
    timestamp: datetime
    high: float
    low: float
    close: float | None = None


@dataclass(frozen=True, slots=True)
class FilledLeg:
    index: int
    timestamp: datetime
    price: float
    allocation: float


@dataclass(frozen=True, slots=True)
class PolicyOutcome:
    status: str
    filled_legs: tuple[FilledLeg, ...]
    average_entry: float | None
    target_price: float | None
    stop_price: float
    exit_time: datetime | None
    realized_return: float | None
    max_adverse_excursion: float | None
    max_favorable_excursion: float | None

    @property
    def target_hit(self) -> bool:
        return self.status == "target"


def evaluate_price_path(
    template: ScaleInTemplateConfig,
    *,
    signal_time: datetime,
    signal_price: float,
    bars: Iterable[PriceBar],
    target_drawdown: float = 0.20,
) -> PolicyOutcome:
    """Evaluate one policy without future features or intrabar optimism.

    Entry orders can fill only during the scale-in window. The stop is fixed
    relative to signal price. The target is recomputed from the weighted
    average of legs filled so far. If a bar touches both stop and target, the
    conservative assumption is that the stop happened first.
    """

    if signal_price <= 0:
        raise ValueError("signal_price must be positive")
    if not 0 < target_drawdown < 1:
        raise ValueError("target_drawdown must be between 0 and 1")

    ordered = sorted(
        (bar for bar in bars if bar.timestamp >= signal_time),
        key=lambda bar: bar.timestamp,
    )
    horizon_end = signal_time + timedelta(hours=template.horizon_hours)
    entry_end = signal_time + timedelta(hours=template.scale_in_hours)
    entry_prices = tuple(
        signal_price * (1.0 + offset) for offset in template.entry_offsets
    )
    stop_price = signal_price * (1.0 + template.hard_stop_pct)
    filled: list[FilledLeg] = []
    filled_indices: set[int] = set()
    max_high: float | None = None
    min_low: float | None = None
    exit_time: datetime | None = None
    last_close: float | None = None
    status = "not_filled"

    for bar in ordered:
        if bar.timestamp > horizon_end:
            break
        if bar.high < bar.low:
            raise ValueError("bar high must be greater than or equal to low")
        if bar.close is not None:
            if not bar.low <= bar.close <= bar.high:
                raise ValueError("bar close must be between low and high")
            last_close = bar.close

        if bar.timestamp <= entry_end:
            for index, (price, allocation) in enumerate(
                zip(entry_prices, template.allocations, strict=True)
            ):
                if index not in filled_indices and bar.high >= price:
                    filled.append(
                        FilledLeg(index + 1, bar.timestamp, price, allocation)
                    )
                    filled_indices.add(index)

        if not filled:
            continue

        total_allocation = sum(leg.allocation for leg in filled)
        average = sum(
            leg.price * leg.allocation for leg in filled
        ) / total_allocation
        target_price = average * (1.0 - target_drawdown)
        max_high = bar.high if max_high is None else max(max_high, bar.high)
        min_low = bar.low if min_low is None else min(min_low, bar.low)

        stop_touched = bar.high >= stop_price
        target_touched = bar.low <= target_price
        if stop_touched:
            status = "stop_ambiguous" if target_touched else "stop"
            exit_time = bar.timestamp
            break
        if target_touched:
            status = "target"
            exit_time = bar.timestamp
            break
        status = "timeout"

    if not filled:
        return PolicyOutcome(
            status=status,
            filled_legs=(),
            average_entry=None,
            target_price=None,
            stop_price=stop_price,
            exit_time=None,
            realized_return=None,
            max_adverse_excursion=None,
            max_favorable_excursion=None,
        )

    total_allocation = sum(leg.allocation for leg in filled)
    average = sum(leg.price * leg.allocation for leg in filled) / total_allocation
    target_price = average * (1.0 - target_drawdown)
    mae = None if max_high is None else (max_high - average) / average
    mfe = None if min_low is None else (average - min_low) / average
    realized = (
        target_drawdown
        if status == "target"
        else -((stop_price - average) / average)
        if status in {"stop", "stop_ambiguous"}
        else (average - last_close) / average
        if status == "timeout" and last_close is not None
        else None
    )
    return PolicyOutcome(
        status=status,
        filled_legs=tuple(filled),
        average_entry=average,
        target_price=target_price,
        stop_price=stop_price,
        exit_time=exit_time,
        realized_return=realized,
        max_adverse_excursion=mae,
        max_favorable_excursion=mfe,
    )


__all__ = ["FilledLeg", "PolicyOutcome", "PriceBar", "evaluate_price_path"]
