"""Regression tests for market cap and signal setup enrichment in API server."""

from __future__ import annotations

from dao_vang.web.api_server import (
    _build_market_cap_info,
    _build_signal_outcomes,
    _build_signal_trade_setup,
    _build_signal_trigger_pattern,
)


def test_build_market_cap_info_large_cap() -> None:
    info_btc = _build_market_cap_info("BTCUSDT", 25_000_000_000.0)
    assert info_btc["market_cap_tier"] == "LARGE"
    assert info_btc["market_cap_usd"] > 1_000_000_000_000
    assert "T" in info_btc["market_cap_str"]

    info_eth = _build_market_cap_info("ETHUSDT", 10_000_000_000.0)
    assert info_eth["market_cap_tier"] == "LARGE"
    assert info_eth["market_cap_usd"] > 100_000_000_000
    assert "B" in info_eth["market_cap_str"]


def test_build_market_cap_info_mid_cap() -> None:
    info_fet = _build_market_cap_info("FETUSDT", 500_000_000.0)
    assert info_fet["market_cap_tier"] == "MID"
    assert "B" in info_fet["market_cap_str"]

    info_wif = _build_market_cap_info("WIFUSDT", 300_000_000.0)
    assert info_wif["market_cap_tier"] == "MID"


def test_build_market_cap_info_small_cap_fallback() -> None:
    info_small = _build_market_cap_info("UNKNOWNCOINUSDT", 5_000_000.0)
    assert info_small["market_cap_tier"] == "SMALL"
    assert info_small["market_cap_usd"] > 0
    assert "M" in info_small["market_cap_str"]
    assert info_small["market_cap_is_estimate"] is True
    assert info_small["market_cap_source"] == "volume_estimate"


def test_build_market_cap_info_uses_provider_value_and_provenance() -> None:
    info = _build_market_cap_info(
        "NEWTOKENUSDT",
        25_000_000.0,
        market_cap_usd=2_250_000_000.0,
        source="binance_agent_os",
        updated_at="2026-09-03T00:00:00+07:00",
    )
    assert info["market_cap_tier"] == "MID"
    assert info["market_cap_usd"] == 2_250_000_000.0
    assert info["market_cap_is_estimate"] is False
    assert info["market_cap_source"] == "binance_agent_os"
    assert info["market_cap_updated_at"] == "2026-09-03T00:00:00+07:00"


def test_build_signal_trade_setup() -> None:
    setup = _build_signal_trade_setup(180.0, 0.82)
    assert setup["entry_price"] == 180.0
    assert setup["stop_loss"] > 180.0
    assert setup["tp1"] < 180.0
    assert setup["tp2"] < setup["tp1"]
    assert setup["rr_ratio"] > 1.5


def test_build_signal_trigger_pattern() -> None:
    anomalies = [{"code": "funding_trap", "title": "Funding Trap"}]
    pat_en, pat_vi = _build_signal_trigger_pattern([], anomalies)
    assert "Funding" in pat_en
    assert "Funding" in pat_vi
    assert len(pat_vi) > 0


def test_build_signal_outcomes() -> None:
    status, mfe, mae = _build_signal_outcomes(True, 12.0)
    assert status == "TARGET_HIT"
    assert mfe is not None
    assert mae is not None

    status_exp, _, _ = _build_signal_outcomes(None, 0.0)
    assert status_exp == "EXPIRED"


