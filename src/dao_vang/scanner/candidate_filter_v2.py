"""Deterministic, side-effect-free candidate filter for pump episodes.

The module deliberately owns no persistence.  ``evaluate_candidate_v2``
returns a plain mapping that callers may persist and pass back on the next
scan.  Network access is isolated in ``scan_candidate_filter_v2`` and one
symbol failing never invalidates the rest of a batch.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import isfinite
from typing import Any, Literal, TypeAlias, cast

import httpx

CandidateV2Stage: TypeAlias = Literal[
    "PUMPING",
    "EXHAUSTING",
    "DISTRIBUTING",
    "DUMPED",
    "DATA_UNAVAILABLE",
]
SymbolState: TypeAlias = dict[str, Any]

_BINANCE_KLINES_PATH = "/fapi/v1/klines"
_MAX_SCAN_WORKERS = 16
_BATCH_FAILURE_LIMIT = 8
_EPSILON = 1e-12
_EVIDENCE_ORDER = (
    "price_structure",
    "order_flow",
    "volume_distribution",
)
_STAGE_ORDER: dict[str, int] = {
    "PUMPING": 0,
    "EXHAUSTING": 1,
    "DISTRIBUTING": 2,
    "DUMPED": 3,
}


def _as_utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class CandidateV2Policy:
    """Versioned thresholds for candidate filter v2."""

    version: str = "candidate_filter_v2"
    pump_threshold_24h: float = 0.15
    pump_threshold_72h: float = 0.30
    pump_threshold_120h: float = 0.50
    memory_hours: int = 72
    max_candidates: int = 30
    exhaustion_drawdown: float = 0.02
    distribution_drawdown: float = 0.05
    dumped_drawdown: float = 0.25
    min_evidence_groups: int = 2

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("version must not be empty")
        thresholds = (
            self.pump_threshold_24h,
            self.pump_threshold_72h,
            self.pump_threshold_120h,
        )
        if any(not isfinite(value) or value <= 0.0 for value in thresholds):
            raise ValueError("pump thresholds must be finite and positive")
        if self.memory_hours < 0:
            raise ValueError("memory_hours must be non-negative")
        if self.max_candidates < 0:
            raise ValueError("max_candidates must be non-negative")
        if not (
            0.0
            <= self.exhaustion_drawdown
            < self.distribution_drawdown
            < self.dumped_drawdown
            < 1.0
        ):
            raise ValueError("drawdown thresholds must be increasing within [0, 1)")
        if not 1 <= self.min_evidence_groups <= len(_EVIDENCE_ORDER):
            raise ValueError("min_evidence_groups must be between 1 and 3")

    # Read-only aliases keep the horizon naming natural for different callers.
    @property
    def pump_24h_threshold(self) -> float:
        return self.pump_threshold_24h

    @property
    def pump_72h_threshold(self) -> float:
        return self.pump_threshold_72h

    @property
    def pump_120h_threshold(self) -> float:
        return self.pump_threshold_120h


@dataclass(frozen=True, slots=True)
class MarketObservation:
    """Latest fully closed 5-minute market candle for one symbol."""

    symbol: str
    observed_at: datetime
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "observed_at",
            _as_utc(self.observed_at, name="observed_at"),
        )


@dataclass(frozen=True, slots=True)
class CandidateV2Decision:
    """Auditable result for one symbol before or after batch ranking."""

    symbol: str
    filter_version: str = "candidate_filter_v2"
    selected: bool = False
    stage: CandidateV2Stage = "DATA_UNAVAILABLE"
    rank: int | None = None
    rank_score: float = 0.0
    pump_score: float = 0.0
    transition_score: float = 0.0
    reference_price: float | None = None
    peak_price: float | None = None
    peak_time: datetime | None = None
    peak_age_hours: float | None = None
    drawdown_from_peak: float | None = None
    volume_24h_usd: float = 0.0
    evidence_groups: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    episode_id: str | None = None

    def __post_init__(self) -> None:
        if self.peak_time is not None:
            object.__setattr__(
                self,
                "peak_time",
                _as_utc(self.peak_time, name="peak_time"),
            )
        object.__setattr__(self, "evidence_groups", tuple(self.evidence_groups))
        object.__setattr__(self, "reason_codes", tuple(self.reason_codes))


@dataclass(frozen=True, slots=True)
class _Bar:
    open_time: datetime
    close_time: datetime
    open: float
    high: float
    low: float
    close: float
    quote_volume: float
    taker_buy_quote_volume: float | None


@dataclass(frozen=True, slots=True)
class _Runup:
    horizon_hours: int
    threshold: float
    return_value: float
    reference_price: float
    reference_time: datetime
    peak_price: float
    peak_time: datetime

    @property
    def normalized_score(self) -> float:
        return self.return_value / self.threshold


def _number(value: Any, *, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _timestamp(value: Any, *, name: str) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value, name=name)
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a datetime or epoch timestamp")
    if isinstance(value, (int, float)):
        numeric = float(value)
    elif isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError(f"{name} must not be empty")
        try:
            numeric = float(raw)
        except ValueError:
            try:
                parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"{name} is not a valid timestamp") from exc
            return _as_utc(parsed, name=name)
    else:
        raise ValueError(f"{name} must be a datetime or epoch timestamp")

    if not isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    # Binance emits milliseconds.  Seconds are accepted to keep replay input
    # convenient, while very large values are interpreted as microseconds.
    magnitude = abs(numeric)
    if magnitude >= 100_000_000_000_000:
        numeric /= 1_000_000.0
    elif magnitude >= 100_000_000_000:
        numeric /= 1_000.0
    try:
        return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError(f"{name} is outside the supported datetime range") from exc


def _mapping_bar(raw: Mapping[str, Any], *, now: datetime) -> _Bar | None:
    open_time = _timestamp(raw.get("open_time"), name="open_time")
    close_time = _timestamp(raw.get("close_time"), name="close_time")
    if open_time > now or close_time > now:
        return None
    if close_time < open_time:
        raise ValueError("close_time must not precede open_time")

    open_price = _number(raw.get("open"), name="open")
    high = _number(raw.get("high"), name="high")
    low = _number(raw.get("low"), name="low")
    close = _number(raw.get("close"), name="close")
    quote_volume = _number(raw.get("quote_volume", 0.0), name="quote_volume")
    taker_raw = raw.get("taker_buy_quote_volume")
    taker_buy = (
        None if taker_raw is None else _number(taker_raw, name="taker_buy_quote_volume")
    )
    if min(open_price, high, low, close) <= 0.0:
        raise ValueError("OHLC prices must be positive")
    if high < low:
        raise ValueError("high must not be below low")
    if quote_volume < 0.0 or (taker_buy is not None and taker_buy < 0.0):
        raise ValueError("volumes must be non-negative")
    return _Bar(
        open_time=open_time,
        close_time=close_time,
        open=open_price,
        high=high,
        low=low,
        close=close,
        quote_volume=quote_volume,
        taker_buy_quote_volume=taker_buy,
    )


def _array_bar(raw: Sequence[Any], *, now: datetime) -> _Bar | None:
    if len(raw) < 8:
        raise ValueError("Binance kline must contain at least eight values")
    mapped: dict[str, Any] = {
        "open_time": raw[0],
        "open": raw[1],
        "high": raw[2],
        "low": raw[3],
        "close": raw[4],
        "close_time": raw[6],
        "quote_volume": raw[7],
        "taker_buy_quote_volume": raw[10] if len(raw) > 10 else None,
    }
    return _mapping_bar(mapped, now=now)


def _closed_bars(raw_bars: Iterable[Any], *, now: datetime) -> list[_Bar]:
    bars: list[_Bar] = []
    for raw in raw_bars:
        try:
            if isinstance(raw, Mapping):
                bar = _mapping_bar(cast(Mapping[str, Any], raw), now=now)
            elif isinstance(raw, Sequence) and not isinstance(
                raw, (str, bytes, bytearray)
            ):
                bar = _array_bar(cast(Sequence[Any], raw), now=now)
            else:
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        if bar is not None:
            bars.append(bar)
    bars.sort(key=lambda item: (item.close_time, item.open_time))
    return bars


def _best_runup(
    bars: Sequence[_Bar],
    *,
    now: datetime,
    horizon_hours: int,
    threshold: float,
) -> _Runup | None:
    cutoff = now - timedelta(hours=horizon_hours)
    window = [bar for bar in bars if bar.close_time > cutoff]
    if not window:
        return None

    reference_price = window[0].open
    reference_time = window[0].open_time
    best_return = -1.0
    best_reference = reference_price
    best_reference_time = reference_time
    best_peak = window[0].high
    best_peak_time = window[0].close_time

    for bar in window:
        runup = bar.high / reference_price - 1.0
        if runup > best_return + _EPSILON:
            best_return = runup
            best_reference = reference_price
            best_reference_time = reference_time
            best_peak = bar.high
            best_peak_time = bar.close_time
        # The low is eligible only for a later candle.  This avoids assuming
        # whether an intrabar low happened before or after the same bar's high.
        if bar.low < reference_price:
            reference_price = bar.low
            reference_time = bar.close_time

    return _Runup(
        horizon_hours=horizon_hours,
        threshold=threshold,
        return_value=max(0.0, best_return),
        reference_price=best_reference,
        reference_time=best_reference_time,
        peak_price=best_peak,
        peak_time=best_peak_time,
    )


def _pump_result(
    bars: Sequence[_Bar],
    *,
    now: datetime,
    policy: CandidateV2Policy,
) -> tuple[bool, float, _Runup | None, tuple[str, ...]]:
    definitions = (
        (24, policy.pump_threshold_24h),
        (72, policy.pump_threshold_72h),
        (120, policy.pump_threshold_120h),
    )
    runups = tuple(
        runup
        for hours, threshold in definitions
        if (
            runup := _best_runup(
                bars,
                now=now,
                horizon_hours=hours,
                threshold=threshold,
            )
        )
        is not None
    )
    if not runups:
        return False, 0.0, None, ()

    best = max(
        runups,
        key=lambda item: (
            item.normalized_score,
            -item.horizon_hours,
            -item.peak_time.timestamp(),
        ),
    )
    passed = tuple(
        f"pump_threshold_{runup.horizon_hours}h"
        for runup in runups
        if runup.return_value + _EPSILON >= runup.threshold
    )
    return bool(passed), max(0.0, best.normalized_score), best, passed


def _state_get(state: Any, *names: str, default: Any = None) -> Any:
    if state is None:
        return default
    for name in names:
        if isinstance(state, Mapping) and name in state:
            return state[name]
        if hasattr(state, name):
            return getattr(state, name)
    return default


def _optional_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        return _timestamp(value, name="state timestamp")
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_positive(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) and result > 0.0 else None


def _state_dict(state: Any) -> SymbolState:
    if isinstance(state, Mapping):
        return {str(key): value for key, value in state.items()}
    if state is None:
        return {}
    names = (
        "symbol",
        "filter_version",
        "stage",
        "episode_id",
        "pump_active",
        "pump_started_at",
        "last_pump_at",
        "memory_expires_at",
        "reference_price",
        "reference_time",
        "peak_price",
        "peak_time",
        "pump_score",
        "last_evaluated_at",
    )
    return {
        name: value
        for name in names
        if (value := getattr(state, name, None)) is not None
    }


def _episode_id(
    symbol: str,
    *,
    reference_time: datetime,
    reference_price: float,
    policy: CandidateV2Policy,
) -> str:
    seed = (
        f"{policy.version}|{symbol}|{reference_time.isoformat()}|{reference_price:.16g}"
    )
    return f"cfv2-{sha256(seed.encode('utf-8')).hexdigest()[:20]}"


def _stage_for_drawdown(
    drawdown: float,
    *,
    policy: CandidateV2Policy,
) -> CandidateV2Stage:
    if drawdown + _EPSILON >= policy.dumped_drawdown:
        return "DUMPED"
    if drawdown + _EPSILON >= policy.distribution_drawdown:
        return "DISTRIBUTING"
    if drawdown + _EPSILON >= policy.exhaustion_drawdown:
        return "EXHAUSTING"
    return "PUMPING"


def _monotonic_stage(
    calculated: CandidateV2Stage,
    *,
    previous_stage: Any,
    same_episode: bool,
) -> CandidateV2Stage:
    previous = str(previous_stage or "").upper()
    if not same_episode or previous not in _STAGE_ORDER:
        return calculated
    if _STAGE_ORDER[previous] > _STAGE_ORDER[calculated]:
        return cast(CandidateV2Stage, previous)
    return calculated


def _evidence_groups(
    bars_5m: Sequence[_Bar],
    *,
    drawdown: float,
    policy: CandidateV2Policy,
) -> tuple[str, ...]:
    found: set[str] = set()
    if drawdown + _EPSILON >= policy.exhaustion_drawdown:
        found.add("price_structure")

    usable_flow = [
        bar
        for bar in bars_5m
        if bar.quote_volume > 0.0 and bar.taker_buy_quote_volume is not None
    ]
    total_flow_volume = sum(bar.quote_volume for bar in usable_flow)
    total_taker_buy = sum(
        min(
            cast(float, bar.taker_buy_quote_volume),
            bar.quote_volume,
        )
        for bar in usable_flow
    )
    if total_flow_volume > 0.0 and total_taker_buy / total_flow_volume < 0.5:
        found.add("order_flow")

    directional = [bar for bar in bars_5m if bar.quote_volume > 0.0]
    directional_volume = sum(bar.quote_volume for bar in directional)
    red_volume = sum(bar.quote_volume for bar in directional if bar.close < bar.open)
    if directional_volume > 0.0 and red_volume / directional_volume > 0.5:
        found.add("volume_distribution")

    return tuple(group for group in _EVIDENCE_ORDER if group in found)


def _transition_score(
    stage: CandidateV2Stage,
    *,
    evidence_count: int,
    policy: CandidateV2Policy,
) -> float:
    stage_component = {
        "PUMPING": 0.0,
        "EXHAUSTING": 0.35,
        "DISTRIBUTING": 0.75,
        "DUMPED": 1.0,
        "DATA_UNAVAILABLE": 0.0,
    }[stage]
    evidence_component = min(1.0, evidence_count / policy.min_evidence_groups)
    return 0.7 * stage_component + 0.3 * evidence_component


def _safe_volume(value: Any) -> float:
    try:
        volume = float(value)
    except (TypeError, ValueError):
        return 0.0
    return volume if isfinite(volume) and volume >= 0.0 else 0.0


def _unavailable_result(
    symbol: str,
    *,
    now: datetime,
    previous_state: Any,
    policy: CandidateV2Policy,
    volume_24h_usd: float,
    reason: str = "data_unavailable",
) -> tuple[CandidateV2Decision, SymbolState]:
    state = _state_dict(previous_state)
    if "stage" not in state:
        state["stage"] = "DATA_UNAVAILABLE"
    state.update(
        {
            "symbol": symbol,
            "filter_version": policy.version,
            "last_scan_status": "DATA_UNAVAILABLE",
            "last_scan_at": now,
        }
    )
    decision = CandidateV2Decision(
        symbol=symbol,
        filter_version=policy.version,
        selected=False,
        stage="DATA_UNAVAILABLE",
        volume_24h_usd=volume_24h_usd,
        reason_codes=(reason, "candidate_rejected"),
        episode_id=cast(str | None, state.get("episode_id")),
    )
    return decision, state


def evaluate_candidate_v2(
    symbol: str,
    bars_4h: Iterable[Mapping[str, Any] | Sequence[Any]],
    bars_5m: Iterable[Mapping[str, Any] | Sequence[Any]],
    quote_volume_24h: float,
    now: datetime,
    previous_state: Any = None,
    policy: CandidateV2Policy | None = None,
) -> tuple[CandidateV2Decision, SymbolState]:
    """Evaluate one symbol using only bars fully closed at or before ``now``.

    A pump qualifies when any horizon threshold passes.  Once direct pump
    evidence disappears, the episode remains eligible through the policy's
    memory window.  Stages are monotonic within one episode and a 25% drawdown
    is terminal until a genuinely newer peak starts a new episode.
    """

    resolved = policy or CandidateV2Policy()
    evaluated_at = _as_utc(now, name="now")
    normalized_symbol = str(symbol).strip().upper()
    volume = _safe_volume(quote_volume_24h)
    closed_4h = _closed_bars(bars_4h, now=evaluated_at)
    closed_5m = _closed_bars(bars_5m, now=evaluated_at)
    current_bar = closed_5m[-1] if closed_5m else (closed_4h[-1] if closed_4h else None)
    if current_bar is None:
        return _unavailable_result(
            normalized_symbol,
            now=evaluated_at,
            previous_state=previous_state,
            policy=resolved,
            volume_24h_usd=volume,
        )

    direct_pump, current_pump_score, runup, pump_reasons = _pump_result(
        closed_4h,
        now=evaluated_at,
        policy=resolved,
    )

    previous_episode = _state_get(previous_state, "episode_id")
    previous_stage = str(_state_get(previous_state, "stage", default="")).upper()
    previous_reference = _optional_positive(
        _state_get(previous_state, "reference_price")
    )
    previous_reference_time = _optional_timestamp(
        _state_get(previous_state, "reference_time", "pump_started_at")
    )
    previous_peak = _optional_positive(_state_get(previous_state, "peak_price"))
    previous_peak_time = _optional_timestamp(_state_get(previous_state, "peak_time"))
    previous_last_pump = _optional_timestamp(
        _state_get(
            previous_state,
            "last_pump_at",
            "last_pump_time",
            "pump_detected_at",
        )
    )
    previous_memory_end = _optional_timestamp(
        _state_get(previous_state, "memory_expires_at", "memory_until")
    )
    if previous_memory_end is None and previous_last_pump is not None:
        previous_memory_end = previous_last_pump + timedelta(
            hours=resolved.memory_hours
        )
    memory_active = (
        previous_episode is not None
        and previous_reference is not None
        and previous_peak is not None
        and previous_memory_end is not None
        and evaluated_at <= previous_memory_end
        and previous_stage != "DUMPED"
    )

    candidate_has_new_peak = bool(
        direct_pump
        and runup is not None
        and (
            previous_peak_time is None
            or runup.peak_time > previous_peak_time
            or runup.peak_price > (previous_peak or 0.0) + _EPSILON
        )
    )
    start_new_episode = bool(
        direct_pump
        and runup is not None
        and (
            previous_episode is None
            or (previous_stage == "DUMPED" and candidate_has_new_peak)
        )
    )
    continue_episode = bool(
        previous_episode is not None
        and direct_pump
        and not start_new_episode
        and previous_stage != "DUMPED"
    )

    episode: str | None
    reference_price: float | None
    reference_time: datetime | None
    peak_price: float | None
    peak_time: datetime | None
    pump_started_at: datetime | None
    last_pump_at: datetime | None
    memory_expires_at: datetime | None
    pump_score: float

    if start_new_episode and runup is not None:
        reference_price = runup.reference_price
        reference_time = runup.reference_time
        peak_price = runup.peak_price
        peak_time = runup.peak_time
        pump_started_at = reference_time
        last_pump_at = evaluated_at
        memory_expires_at = evaluated_at + timedelta(hours=resolved.memory_hours)
        pump_score = current_pump_score
        episode = _episode_id(
            normalized_symbol,
            reference_time=reference_time,
            reference_price=reference_price,
            policy=resolved,
        )
    elif continue_episode and runup is not None:
        if previous_reference is None or runup.reference_price < previous_reference:
            reference_price = runup.reference_price
            reference_time = runup.reference_time
        else:
            reference_price = previous_reference
            reference_time = previous_reference_time or runup.reference_time
        if previous_peak is None or runup.peak_price > previous_peak:
            peak_price = runup.peak_price
            peak_time = runup.peak_time
        else:
            peak_price = previous_peak
            peak_time = previous_peak_time or runup.peak_time
        pump_started_at = (
            _optional_timestamp(_state_get(previous_state, "pump_started_at"))
            or reference_time
        )
        last_pump_at = evaluated_at
        memory_expires_at = evaluated_at + timedelta(hours=resolved.memory_hours)
        pump_score = max(
            current_pump_score,
            _safe_volume(_state_get(previous_state, "pump_score", default=0.0)),
        )
        episode = str(previous_episode)
    elif memory_active:
        episode = str(previous_episode)
        reference_price = previous_reference
        reference_time = previous_reference_time
        peak_price = previous_peak
        peak_time = previous_peak_time
        pump_started_at = (
            _optional_timestamp(_state_get(previous_state, "pump_started_at"))
            or reference_time
        )
        last_pump_at = previous_last_pump
        memory_expires_at = previous_memory_end
        pump_score = _safe_volume(
            _state_get(previous_state, "pump_score", default=current_pump_score)
        )
    elif previous_stage == "DUMPED" and previous_episode is not None:
        episode = str(previous_episode)
        reference_price = previous_reference
        reference_time = previous_reference_time
        peak_price = previous_peak
        peak_time = previous_peak_time
        pump_started_at = (
            _optional_timestamp(_state_get(previous_state, "pump_started_at"))
            or reference_time
        )
        last_pump_at = previous_last_pump
        memory_expires_at = previous_memory_end
        pump_score = _safe_volume(
            _state_get(previous_state, "pump_score", default=current_pump_score)
        )
    else:
        episode = None
        reference_price = runup.reference_price if runup is not None else None
        reference_time = runup.reference_time if runup is not None else None
        peak_price = runup.peak_price if runup is not None else current_bar.high
        peak_time = runup.peak_time if runup is not None else current_bar.close_time
        pump_started_at = None
        last_pump_at = None
        memory_expires_at = None
        pump_score = current_pump_score

    # A new fully closed 5m high refines the episode peak between 4h closes.
    if peak_price is not None:
        for bar in closed_5m:
            if bar.high > peak_price + _EPSILON:
                peak_price = bar.high
                peak_time = bar.close_time
    if peak_price is None or current_bar.close > peak_price:
        peak_price = current_bar.close
        peak_time = current_bar.close_time

    drawdown = max(0.0, 1.0 - current_bar.close / peak_price)
    calculated_stage = _stage_for_drawdown(drawdown, policy=resolved)
    same_episode = bool(episode is not None and episode == previous_episode)
    stage = _monotonic_stage(
        calculated_stage,
        previous_stage=previous_stage,
        same_episode=same_episode,
    )
    active = bool(direct_pump or memory_active)
    if previous_stage == "DUMPED" and not start_new_episode:
        active = False
        stage = "DUMPED"
    selected = active and stage != "DUMPED"

    groups = _evidence_groups(
        closed_5m,
        drawdown=drawdown,
        policy=resolved,
    )
    transition_score = _transition_score(
        stage,
        evidence_count=len(groups),
        policy=resolved,
    )
    rank_score = 0.7 * pump_score + 0.3 * transition_score
    peak_age_hours = (
        max(0.0, (evaluated_at - peak_time).total_seconds() / 3600.0)
        if peak_time is not None
        else None
    )

    reasons: list[str] = list(pump_reasons)
    if direct_pump:
        reasons.append("pump_active")
    elif memory_active:
        reasons.append("pump_memory_active")
    else:
        reasons.append("pump_threshold_not_met")
    reasons.append(f"stage_{stage.lower()}")
    reasons.extend(f"evidence_{group}" for group in groups)
    if len(groups) >= resolved.min_evidence_groups:
        reasons.append("independent_evidence_met")
    else:
        reasons.append("insufficient_independent_evidence")
    reasons.append("preliminary_selected" if selected else "candidate_rejected")

    decision = CandidateV2Decision(
        symbol=normalized_symbol,
        filter_version=resolved.version,
        selected=selected,
        stage=stage,
        rank=None,
        rank_score=rank_score,
        pump_score=pump_score,
        transition_score=transition_score,
        reference_price=reference_price,
        peak_price=peak_price,
        peak_time=peak_time,
        peak_age_hours=peak_age_hours,
        drawdown_from_peak=drawdown,
        volume_24h_usd=volume,
        evidence_groups=groups,
        reason_codes=tuple(dict.fromkeys(reasons)),
        episode_id=episode,
    )
    next_state: SymbolState = {
        "symbol": normalized_symbol,
        "filter_version": resolved.version,
        "stage": stage,
        "episode_id": episode,
        "pump_active": active,
        "pump_started_at": pump_started_at,
        "last_pump_at": last_pump_at,
        "memory_expires_at": memory_expires_at,
        "reference_price": reference_price,
        "reference_time": reference_time,
        "peak_price": peak_price,
        "peak_time": peak_time,
        "pump_score": pump_score,
        "last_evaluated_at": evaluated_at,
        "last_scan_status": "OK",
    }
    return decision, next_state


def rank_candidate_v2(
    decisions: Iterable[CandidateV2Decision],
    max_candidates: int,
) -> list[CandidateV2Decision]:
    """Rank preliminary candidates and keep only the deterministic top N."""

    if max_candidates < 0:
        raise ValueError("max_candidates must be non-negative")
    values = list(decisions)
    eligible = sorted(
        (
            (index, decision)
            for index, decision in enumerate(values)
            if decision.selected
            and decision.stage not in {"DUMPED", "DATA_UNAVAILABLE"}
        ),
        key=lambda item: (
            -item[1].rank_score,
            item[1].symbol.upper(),
            item[1].symbol,
            item[0],
        ),
    )

    ranked: list[CandidateV2Decision] = []
    eligible_indexes: set[int] = set()
    for rank, (index, decision) in enumerate(eligible, start=1):
        eligible_indexes.add(index)
        selected = rank <= max_candidates
        reasons = list(decision.reason_codes)
        if not selected:
            reasons.append("rank_cap_exceeded")
        ranked.append(
            replace(
                decision,
                rank=rank,
                selected=selected,
                reason_codes=tuple(dict.fromkeys(reasons)),
            )
        )

    rejected = sorted(
        (
            (index, decision)
            for index, decision in enumerate(values)
            if index not in eligible_indexes
        ),
        key=lambda item: (
            item[1].stage == "DATA_UNAVAILABLE",
            item[1].symbol.upper(),
            item[1].symbol,
            item[0],
        ),
    )
    ranked.extend(
        replace(decision, rank=None, selected=False) for _, decision in rejected
    )
    return ranked


def _fetch_klines(
    client: httpx.Client,
    *,
    base_url: str,
    symbol: str,
    interval: str,
    limit: int,
) -> list[Any]:
    response = client.get(
        f"{base_url.rstrip('/')}{_BINANCE_KLINES_PATH}",
        params={"symbol": symbol, "interval": interval, "limit": limit},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise ValueError(f"empty or invalid {interval} kline response")
    return cast(list[Any], payload)


def _derived_24h_volume(bars: Sequence[_Bar], *, now: datetime) -> float:
    cutoff = now - timedelta(hours=24)
    return sum(bar.quote_volume for bar in bars if bar.close_time > cutoff)


def _scan_one_symbol(
    symbol: str,
    *,
    client: httpx.Client,
    base_url: str,
    now: datetime,
    previous_state: Any,
    policy: CandidateV2Policy,
    volume_override: float | None,
) -> tuple[CandidateV2Decision, MarketObservation, SymbolState]:
    raw_4h = _fetch_klines(
        client,
        base_url=base_url,
        symbol=symbol,
        interval="4h",
        limit=32,
    )
    raw_5m = _fetch_klines(
        client,
        base_url=base_url,
        symbol=symbol,
        interval="5m",
        limit=14,
    )
    closed_4h = _closed_bars(raw_4h, now=now)
    closed_5m = _closed_bars(raw_5m, now=now)
    if not closed_4h or not closed_5m:
        raise ValueError("symbol has no fully closed 4h or 5m bars")
    volume = (
        _safe_volume(volume_override)
        if volume_override is not None
        else _derived_24h_volume(closed_4h, now=now)
    )
    decision, state = evaluate_candidate_v2(
        symbol,
        raw_4h,
        raw_5m,
        volume,
        now,
        previous_state,
        policy,
    )
    latest = closed_5m[-1]
    observation = MarketObservation(
        symbol=symbol,
        observed_at=latest.close_time,
        high=latest.high,
        low=latest.low,
        close=latest.close,
    )
    return decision, observation, state


def scan_candidate_filter_v2(
    symbols: Iterable[str],
    now: datetime,
    previous_state: Mapping[str, Any] | None = None,
    policy: CandidateV2Policy | None = None,
    *,
    quote_volumes_24h: Mapping[str, float] | None = None,
    base_url: str = "https://fapi.binance.com",
    timeout_seconds: float = 10.0,
    max_workers: int = 8,
    client: httpx.Client | None = None,
) -> tuple[
    list[CandidateV2Decision],
    list[MarketObservation],
    dict[str, SymbolState],
]:
    """Fetch and rank a batch while failing closed per individual symbol.

    The caller may inject an ``httpx.Client`` (including one backed by
    ``MockTransport``); injected clients remain caller-owned and are not closed.
    Worker count is always bounded to sixteen and to the number of symbols.
    """

    resolved = policy or CandidateV2Policy()
    evaluated_at = _as_utc(now, name="now")
    if timeout_seconds <= 0.0:
        raise ValueError("timeout_seconds must be positive")
    if max_workers <= 0:
        raise ValueError("max_workers must be positive")

    normalized_symbols = sorted(
        {normalized for value in symbols if (normalized := str(value).strip().upper())}
    )
    previous = previous_state or {}
    next_state: dict[str, SymbolState] = {
        str(key): _state_dict(value) for key, value in previous.items()
    }
    if not normalized_symbols:
        return [], [], next_state

    def prior_for(symbol: str) -> Any:
        return previous.get(symbol, previous.get(symbol.lower()))

    def volume_for(symbol: str) -> float | None:
        if quote_volumes_24h is None:
            return None
        value = quote_volumes_24h.get(
            symbol,
            quote_volumes_24h.get(symbol.lower()),
        )
        return None if value is None else float(value)

    decisions: list[CandidateV2Decision] = []
    observations: list[MarketObservation] = []
    failure_lock = threading.Lock()
    failure_count = 0
    batch_circuit_open = threading.Event()
    owns_client = client is None
    active_client: httpx.Client | None = client

    def scan_one(
        symbol: str,
    ) -> tuple[CandidateV2Decision, MarketObservation, SymbolState]:
        nonlocal failure_count
        if batch_circuit_open.is_set():
            raise RuntimeError("candidate-v2 batch circuit open")
        try:
            return _scan_one_symbol(
                symbol,
                client=cast(httpx.Client, active_client),
                base_url=base_url,
                now=evaluated_at,
                previous_state=prior_for(symbol),
                policy=resolved,
                volume_override=volume_for(symbol),
            )
        except Exception:
            with failure_lock:
                failure_count += 1
                failure_limit = min(
                    _BATCH_FAILURE_LIMIT,
                    max(2, len(normalized_symbols)),
                )
                if failure_count >= failure_limit:
                    batch_circuit_open.set()
            raise

    try:
        if active_client is None:
            active_client = httpx.Client(timeout=timeout_seconds)
        worker_count = min(_MAX_SCAN_WORKERS, max_workers, len(normalized_symbols))
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="candidate-v2",
        ) as executor:
            futures = {
                executor.submit(
                    scan_one,
                    symbol,
                ): symbol
                for symbol in normalized_symbols
            }
            for future in as_completed(futures):
                symbol = futures[future]
                try:
                    decision, observation, state = future.result()
                except Exception:
                    decision, state = _unavailable_result(
                        symbol,
                        now=evaluated_at,
                        previous_state=prior_for(symbol),
                        policy=resolved,
                        volume_24h_usd=_safe_volume(volume_for(symbol)),
                        reason="symbol_fetch_failed",
                    )
                    # The 4h history may fail while the latest closed 5m bar
                    # is still available. Retry only that lightweight tape so
                    # champion and challenger can share an outcome anchor even
                    # though the challenger decision remains fail-closed.
                    try:
                        if batch_circuit_open.is_set():
                            raise RuntimeError("candidate-v2 batch circuit open")
                        raw_5m = _fetch_klines(
                            active_client,
                            base_url=base_url,
                            symbol=symbol,
                            interval="5m",
                            limit=14,
                        )
                        closed_5m = _closed_bars(raw_5m, now=evaluated_at)
                        if closed_5m:
                            latest = closed_5m[-1]
                            observations.append(
                                MarketObservation(
                                    symbol=symbol,
                                    observed_at=latest.close_time,
                                    high=latest.high,
                                    low=latest.low,
                                    close=latest.close,
                                )
                            )
                    except Exception:
                        pass
                else:
                    observations.append(observation)
                decisions.append(decision)
                next_state[symbol] = state
    except Exception:
        # Client construction or executor setup can fail before per-symbol
        # futures exist.  Preserve the same fail-closed batch contract.
        completed = {decision.symbol for decision in decisions}
        for symbol in normalized_symbols:
            if symbol in completed:
                continue
            decision, state = _unavailable_result(
                symbol,
                now=evaluated_at,
                previous_state=prior_for(symbol),
                policy=resolved,
                volume_24h_usd=_safe_volume(volume_for(symbol)),
                reason="symbol_fetch_failed",
            )
            decisions.append(decision)
            next_state[symbol] = state
    finally:
        if owns_client and active_client is not None:
            active_client.close()

    observations.sort(key=lambda item: item.symbol)
    ranked = rank_candidate_v2(decisions, resolved.max_candidates)
    return ranked, observations, next_state


__all__ = [
    "CandidateV2Decision",
    "CandidateV2Policy",
    "CandidateV2Stage",
    "MarketObservation",
    "evaluate_candidate_v2",
    "rank_candidate_v2",
    "scan_candidate_filter_v2",
]
