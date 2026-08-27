"""Regression tests for live funding-rate mapping in the coin detail API."""

from __future__ import annotations

from dao_vang.web.api_server import (
    _format_funding_rate,
    _funding_asof,
    _infer_funding_interval_ms,
    _parse_funding_history,
    _parse_live_funding,
)


def test_funding_asof_never_uses_a_future_settlement() -> None:
    points = [(100, 0.0001), (200, 0.0002)]

    assert _funding_asof(points, 150) == (0.0001, 100)
    assert _funding_asof(points, 50) is None


def test_funding_asof_can_mark_an_old_event_unavailable() -> None:
    points = [(100, 0.0001)]

    assert _funding_asof(points, 149, max_age_ms=50) == (0.0001, 100)
    assert _funding_asof(points, 151, max_age_ms=50) is None


def test_funding_history_is_normalized_and_deduplicated() -> None:
    payload = [
        {"fundingTime": 200, "fundingRate": "0.0002"},
        {"fundingTime": 100, "fundingRate": "0.0001"},
        {"fundingTime": 200, "fundingRate": "0.0003"},
        {"fundingTime": 300, "fundingRate": "not-a-number"},
    ]

    assert _parse_funding_history(payload) == [(100, 0.0001), (200, 0.0003)]
    assert _infer_funding_interval_ms(_parse_funding_history(payload)) == 100


def test_live_premium_index_returns_latest_and_next_funding_times() -> None:
    payload = {
        "symbol": "TACUSDT",
        "lastFundingRate": "0.0005",
        "nextFundingTime": 500,
        "time": 450,
    }

    assert _parse_live_funding(payload, "TACUSDT") == (0.0005, 500, 450)
    assert _parse_live_funding({**payload, "symbol": "BTCUSDT"}, "TACUSDT") == (None, None, None)


def test_invalid_live_premium_index_does_not_become_zero() -> None:
    assert _parse_live_funding({"symbol": "TACUSDT"}, "TACUSDT") == (None, None, None)
    assert _format_funding_rate(None) == "N/A"
    assert _format_funding_rate(0.0005) == "+0.050%"
