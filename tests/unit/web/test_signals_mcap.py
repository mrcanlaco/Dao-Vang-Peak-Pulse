"""Regression tests for market cap and signal setup enrichment in API server."""

from __future__ import annotations

from dao_vang.web.api_server import (
    _apply_stored_execution_policy,
    _build_market_cap_info,
    _build_signal_outcomes,
    _build_signal_trade_setup,
    _build_signal_trigger_pattern,
)


def test_build_market_cap_info_large_cap() -> None:
    # Now that fallbacks are removed, without a provider value, it returns N/A
    info_btc = _build_market_cap_info("BTCUSDT", 25_000_000_000.0)
    assert info_btc["market_cap_tier"] == "UNKNOWN"
    assert info_btc["market_cap_usd"] is None
    assert info_btc["market_cap_str"] == "N/A"

    info_eth = _build_market_cap_info("ETHUSDT", 10_000_000_000.0)
    assert info_eth["market_cap_tier"] == "UNKNOWN"
    assert info_eth["market_cap_usd"] is None
    assert info_eth["market_cap_str"] == "N/A" 


def test_build_market_cap_info_mid_cap() -> None:
    info_fet = _build_market_cap_info("FETUSDT", 500_000_000.0)
    assert info_fet["market_cap_tier"] == "UNKNOWN"
    assert info_fet["market_cap_str"] == "N/A"

    info_wif = _build_market_cap_info("WIFUSDT", 300_000_000.0)
    assert info_wif["market_cap_tier"] == "UNKNOWN" 


def test_build_market_cap_info_small_cap_fallback() -> None:
    # Volume-based estimation is completely removed
    info_small = _build_market_cap_info("UNKNOWNCOINUSDT", 5_000_000.0)
    assert info_small["market_cap_tier"] == "UNKNOWN"
    assert info_small["market_cap_usd"] is None
    assert info_small["market_cap_str"] == "N/A"
    assert info_small["market_cap_is_estimate"] is False
    assert info_small["market_cap_source"] == "unavailable" 


def test_build_market_cap_info_uses_provider_value_and_provenance() -> None:
    info = _build_market_cap_info(
        "NEWTOKENUSDT",
        25_000_000.0,
        market_cap_usd=2_250_000_000.0,
        source="coingecko",
        updated_at="2026-09-03T00:00:00+07:00",
    )
    assert info["market_cap_tier"] == "MID"
    assert info["market_cap_usd"] == 2_250_000_000.0
    assert info["market_cap_is_estimate"] is False
    assert info["market_cap_source"] == "coingecko"
    assert info["market_cap_updated_at"] == "2026-09-03T00:00:00+07:00"

def test_build_market_cap_info_formatting() -> None:
    # Mid/Small Boundary ($1B)
    b_info = _build_market_cap_info("B", market_cap_usd=1_000_000_000.0)
    assert b_info["market_cap_str"] == "$1.0B"
    assert b_info["market_cap_tier"] == "MID"

    m_info = _build_market_cap_info("M1", market_cap_usd=999_999_999.0)
    assert m_info["market_cap_str"] == "$1000M"
    assert m_info["market_cap_tier"] == "SMALL"
    
    # Small/Micro Boundary ($10M)
    m_info2 = _build_market_cap_info("M2", market_cap_usd=10_000_000.0)
    assert m_info2["market_cap_str"] == "$10M"
    assert m_info2["market_cap_tier"] == "SMALL"

    # Microcap (<$10M)
    k_info = _build_market_cap_info("K", market_cap_usd=9_999_999.0)
    assert k_info["market_cap_str"] == "$10M"
    assert k_info["market_cap_tier"] == "MICRO"
    
    k_info2 = _build_market_cap_info("K2", market_cap_usd=500_000.0)
    assert k_info2["market_cap_str"] == "$500,000"
    assert k_info2["market_cap_tier"] == "MICRO" 


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
    assert mfe is None
    assert mae is None

    status_fail, mfe_fail, mae_fail = _build_signal_outcomes(False, 12.0)
    assert status_fail == "EXPIRED"
    assert mfe_fail is None
    assert mae_fail is None

    status_exp, _, _ = _build_signal_outcomes(None, 0.0)
    assert status_exp == "EXPIRED"

def test_stored_execution_policy_overrides_current_config_plan() -> None:
    current = _build_signal_trade_setup(120.0, 0.82)
    stored = {
        "entry_legs": [
            {"index": 1, "price": 100.0, "offset_pct": 0.0, "allocation_pct": 20.0},
            {"index": 2, "price": 105.0, "offset_pct": 5.0, "allocation_pct": 30.0},
            {"index": 3, "price": 110.0, "offset_pct": 10.0, "allocation_pct": 50.0},
        ],
        "projected_average_entry": 106.5,
        "projected_target_price": 85.2,
        "hard_stop_price": 116.0,
        "hard_stop_pct": 16.0,
        "target_drawdown_pct": 20.0,
        "projected_stop_risk_pct": 8.9202,
        "projected_rr_ratio": 2.2421,
        "policy_id": "scale_in_balanced",
        "policy_version": "scale_in_balanced:1.0",
    }

    setup = _apply_stored_execution_policy(current, stored)

    assert setup["entry_price"] == 100.0
    assert setup["projected_average_entry"] == 106.5
    assert setup["tp2"] == 85.2
    assert setup["execution_policy"]["policy_version"] == "scale_in_balanced:1.0"

