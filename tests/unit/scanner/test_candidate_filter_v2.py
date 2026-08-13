from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import pytest

from dao_vang.scanner.candidate_filter_v2 import (
    CandidateV2Decision,
    CandidateV2Policy,
    evaluate_candidate_v2,
    rank_candidate_v2,
    scan_candidate_filter_v2,
)

NOW = datetime(2026, 8, 13, 4, 0, tzinfo=timezone.utc)


def _bar(
    open_time: datetime,
    close_time: datetime,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
    quote_volume: float = 1_000.0,
    taker_buy_ratio: float = 0.5,
) -> dict[str, Any]:
    return {
        "open_time": open_time,
        "close_time": close_time,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "quote_volume": quote_volume,
        "taker_buy_quote_volume": quote_volume * taker_buy_ratio,
    }


def _pump_bars(
    *,
    now: datetime = NOW,
    start_hours_ago: int = 24,
    pump_return: float = 0.15,
) -> list[dict[str, Any]]:
    count = start_hours_ago // 4
    target = 100.0 * (1.0 + pump_return)
    bars: list[dict[str, Any]] = []
    start = now - timedelta(hours=start_hours_ago)
    for index in range(count):
        opened_at = start + timedelta(hours=4 * index)
        closed_at = opened_at + timedelta(hours=4)
        price = 100.0 if index == 0 else target
        bars.append(
            _bar(
                opened_at,
                closed_at,
                open_price=100.0 if index == 0 else target,
                high=price,
                low=100.0 if index == 0 else target,
                close=price,
            )
        )
    return bars


def _flat_bars(
    *,
    now: datetime,
    price: float,
    interval: timedelta,
    count: int,
    taker_buy_ratio: float = 0.5,
) -> list[dict[str, Any]]:
    start = now - interval * count
    return [
        _bar(
            start + interval * index,
            start + interval * (index + 1),
            open_price=price,
            high=price,
            low=price,
            close=price,
            taker_buy_ratio=taker_buy_ratio,
        )
        for index in range(count)
    ]


def _latest_5m(
    *,
    now: datetime = NOW,
    peak: float,
    close: float,
    red: bool = True,
    taker_buy_ratio: float = 0.5,
) -> list[dict[str, Any]]:
    open_price = peak if red else close * 0.99
    return [
        _bar(
            now - timedelta(minutes=5),
            now,
            open_price=open_price,
            high=peak,
            low=min(open_price, close),
            close=close,
            taker_buy_ratio=taker_buy_ratio,
        )
    ]


def _evaluate(
    bars_4h: list[dict[str, Any]],
    bars_5m: list[dict[str, Any]],
    *,
    now: datetime = NOW,
    previous_state: Any = None,
) -> tuple[CandidateV2Decision, dict[str, Any]]:
    return evaluate_candidate_v2(
        "testusdt",
        bars_4h,
        bars_5m,
        12_000_000.0,
        now,
        previous_state,
        CandidateV2Policy(),
    )


def test_policy_defaults_are_versioned() -> None:
    policy = CandidateV2Policy()

    assert policy.version == "candidate_filter_v2"
    assert (
        policy.pump_threshold_24h,
        policy.pump_threshold_72h,
        policy.pump_threshold_120h,
    ) == (0.15, 0.30, 0.50)
    assert policy.memory_hours == 72
    assert policy.max_candidates == 30
    assert (
        policy.exhaustion_drawdown,
        policy.distribution_drawdown,
        policy.dumped_drawdown,
    ) == (0.02, 0.05, 0.25)
    assert policy.min_evidence_groups == 2


@pytest.mark.parametrize(
    ("hours", "pump_return", "reason"),
    [
        (24, 0.15, "pump_threshold_24h"),
        (72, 0.30, "pump_threshold_72h"),
        (120, 0.50, "pump_threshold_120h"),
    ],
)
def test_each_pump_horizon_is_an_independent_or_condition(
    hours: int,
    pump_return: float,
    reason: str,
) -> None:
    peak = 100.0 * (1.0 + pump_return)
    decision, _ = _evaluate(
        _pump_bars(start_hours_ago=hours, pump_return=pump_return),
        _latest_5m(peak=peak, close=peak),
    )

    assert decision.selected is True
    assert decision.stage == "PUMPING"
    assert reason in decision.reason_codes


def test_pump_below_every_threshold_is_rejected() -> None:
    peak = 114.9
    decision, _ = _evaluate(
        _pump_bars(start_hours_ago=24, pump_return=0.149),
        _latest_5m(peak=peak, close=peak),
    )

    assert decision.selected is False
    assert "pump_threshold_not_met" in decision.reason_codes


def test_memory_keeps_episode_for_exactly_72_hours() -> None:
    peak = 115.0
    initial, state = _evaluate(
        _pump_bars(start_hours_ago=24, pump_return=0.15),
        _latest_5m(peak=peak, close=peak),
    )
    assert initial.selected is True

    within_memory = NOW + timedelta(hours=72)
    remembered, remembered_state = _evaluate(
        _flat_bars(
            now=within_memory,
            price=114.0,
            interval=timedelta(hours=4),
            count=6,
        ),
        _latest_5m(now=within_memory, peak=114.0, close=114.0),
        now=within_memory,
        previous_state=state,
    )
    assert remembered.selected is True
    assert remembered.episode_id == initial.episode_id
    assert "pump_memory_active" in remembered.reason_codes
    assert remembered_state["last_pump_at"] == NOW

    expired_at = NOW + timedelta(hours=72, microseconds=1)
    expired, _ = _evaluate(
        _flat_bars(
            now=expired_at,
            price=114.0,
            interval=timedelta(hours=4),
            count=6,
        ),
        _latest_5m(now=expired_at, peak=114.0, close=114.0),
        now=expired_at,
        previous_state=state,
    )
    assert expired.selected is False


@pytest.mark.parametrize(
    ("drawdown", "expected_stage", "selected"),
    [
        (0.03, "EXHAUSTING", True),
        (0.10, "DISTRIBUTING", True),
        (0.30, "DUMPED", False),
    ],
)
def test_drawdown_drives_three_transition_states(
    drawdown: float,
    expected_stage: str,
    selected: bool,
) -> None:
    peak = 115.0
    decision, _ = _evaluate(
        _pump_bars(start_hours_ago=24, pump_return=0.15),
        _latest_5m(
            peak=peak,
            close=peak * (1.0 - drawdown),
            taker_buy_ratio=0.3,
        ),
    )

    assert decision.stage == expected_stage
    assert decision.selected is selected


def test_evidence_counts_groups_not_number_of_signals() -> None:
    peak = 115.0
    current = peak * 0.94
    bars_5m = [
        _bar(
            NOW - timedelta(minutes=10),
            NOW - timedelta(minutes=5),
            open_price=current * 0.98,
            high=peak,
            low=current * 0.98,
            close=current * 0.99,
            quote_volume=2_000.0,
            taker_buy_ratio=0.2,
        ),
        _bar(
            NOW - timedelta(minutes=5),
            NOW,
            open_price=current * 0.99,
            high=current,
            low=current * 0.99,
            close=current,
            quote_volume=2_000.0,
            taker_buy_ratio=0.2,
        ),
    ]

    decision, _ = _evaluate(
        _pump_bars(start_hours_ago=24, pump_return=0.15),
        bars_5m,
    )

    assert decision.evidence_groups == ("price_structure", "order_flow")
    assert "independent_evidence_met" in decision.reason_codes


def test_rank_cap_and_symbol_tie_break_are_deterministic() -> None:
    decisions = [
        CandidateV2Decision(
            symbol="BBBUSDT",
            selected=True,
            stage="EXHAUSTING",
            rank_score=2.0,
        ),
        CandidateV2Decision(
            symbol="CCCUSDT",
            selected=True,
            stage="DISTRIBUTING",
            rank_score=3.0,
        ),
        CandidateV2Decision(
            symbol="AAAUSDT",
            selected=True,
            stage="EXHAUSTING",
            rank_score=2.0,
        ),
    ]

    ranked = rank_candidate_v2(decisions, max_candidates=2)

    assert [decision.symbol for decision in ranked] == [
        "CCCUSDT",
        "AAAUSDT",
        "BBBUSDT",
    ]
    assert [decision.rank for decision in ranked] == [1, 2, 3]
    assert [decision.selected for decision in ranked] == [True, True, False]
    assert "rank_cap_exceeded" in ranked[2].reason_codes


def test_future_bars_never_affect_decision() -> None:
    bars_4h = _pump_bars(start_hours_ago=24, pump_return=0.10)
    bars_4h.append(
        _bar(
            NOW + timedelta(minutes=1),
            NOW + timedelta(hours=4),
            open_price=110.0,
            high=1_000.0,
            low=110.0,
            close=1_000.0,
        )
    )
    bars_5m = _latest_5m(peak=110.0, close=110.0)
    bars_5m.append(
        _bar(
            NOW + timedelta(seconds=1),
            NOW + timedelta(minutes=5),
            open_price=110.0,
            high=2_000.0,
            low=1.0,
            close=1.0,
            taker_buy_ratio=0.0,
        )
    )

    decision, _ = _evaluate(bars_4h, bars_5m)

    assert decision.selected is False
    assert decision.peak_price == pytest.approx(110.0)
    assert decision.stage == "PUMPING"


def _as_binance_kline(bar: dict[str, Any]) -> list[Any]:
    return [
        int(bar["open_time"].timestamp() * 1_000),
        str(bar["open"]),
        str(bar["high"]),
        str(bar["low"]),
        str(bar["close"]),
        "1",
        int(bar["close_time"].timestamp() * 1_000),
        str(bar["quote_volume"]),
        1,
        "0",
        str(bar["taker_buy_quote_volume"]),
        "0",
    ]


def test_scan_partial_network_failure_fails_closed_per_symbol() -> None:
    peak = 115.0
    raw_4h = [
        _as_binance_kline(bar)
        for bar in _pump_bars(start_hours_ago=24, pump_return=0.15)
    ]
    raw_5m = [_as_binance_kline(bar) for bar in _latest_5m(peak=peak, close=peak)]
    requests: list[tuple[str, str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        symbol = request.url.params["symbol"]
        interval = request.url.params["interval"]
        limit = request.url.params["limit"]
        requests.append((symbol, interval, limit))
        if symbol == "BADUSDT":
            return httpx.Response(503, request=request)
        payload = raw_4h if interval == "4h" else raw_5m
        return httpx.Response(200, json=payload, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        decisions, observations, next_state = scan_candidate_filter_v2(
            ["GOODUSDT", "BADUSDT"],
            NOW,
            {},
            CandidateV2Policy(),
            base_url="https://unit.test",
            max_workers=2,
            client=client,
        )

    by_symbol = {decision.symbol: decision for decision in decisions}
    assert by_symbol["GOODUSDT"].selected is True
    assert by_symbol["BADUSDT"].selected is False
    assert by_symbol["BADUSDT"].stage == "DATA_UNAVAILABLE"
    assert [observation.symbol for observation in observations] == ["GOODUSDT"]
    assert observations[0].observed_at == NOW
    assert set(next_state) == {"GOODUSDT", "BADUSDT"}
    assert ("GOODUSDT", "4h", "32") in requests
    assert ("GOODUSDT", "5m", "14") in requests


def test_scan_keeps_market_observation_when_only_4h_history_fails() -> None:
    raw_5m = [_as_binance_kline(bar) for bar in _latest_5m(peak=115.0, close=114.0)]

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["interval"] == "4h":
            return httpx.Response(503, request=request)
        return httpx.Response(200, json=raw_5m, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        decisions, observations, _ = scan_candidate_filter_v2(
            ["TESTUSDT"],
            NOW,
            client=client,
            base_url="https://unit.test",
            max_workers=1,
        )

    assert decisions[0].selected is False
    assert decisions[0].stage == "DATA_UNAVAILABLE"
    assert len(observations) == 1
    assert observations[0].symbol == "TESTUSDT"
    assert observations[0].close == pytest.approx(114.0)


def test_scan_opens_batch_circuit_after_repeated_network_failures() -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.params["symbol"])
        return httpx.Response(503, request=request)

    symbols = [f"TEST{index}USDT" for index in range(30)]
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        decisions, observations, _ = scan_candidate_filter_v2(
            symbols,
            NOW,
            client=client,
            base_url="https://unit.test",
            max_workers=4,
        )

    assert len(decisions) == len(symbols)
    assert all(decision.stage == "DATA_UNAVAILABLE" for decision in decisions)
    assert observations == []
    assert len(requests) < len(symbols)
