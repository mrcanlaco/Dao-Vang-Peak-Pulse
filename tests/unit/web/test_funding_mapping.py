"""Regression tests for live funding-rate mapping in the coin detail API."""

from __future__ import annotations

from dao_vang.web.api_server import (
    _format_funding_rate,
    _funding_apr,
    _funding_asof,
    _funding_payer,
    _infer_funding_interval_ms,
    _parse_funding_history,
    _parse_funding_interval_info,
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


def test_funding_info_overrides_history_inference_for_non_standard_cadence() -> None:
    payload = [
        {"symbol": "BTCUSDT", "fundingIntervalHours": 4},
        {"symbol": "TACUSDT", "fundingIntervalHours": 2},
    ]

    assert _parse_funding_interval_info(payload, "TACUSDT") == 2.0
    assert _parse_funding_interval_info(payload, "ETHUSDT") is None


def test_funding_apr_and_payer_use_the_selected_cadence() -> None:
    assert _funding_apr(0.0005, 8.0) == 0.5475
    assert _funding_apr(0.0005, 2.0) == 2.19
    assert _funding_payer(0.0005) == "long"
    assert _funding_payer(-0.0005) == "short"
    assert _funding_payer(0.0) == "none"
