"""Unit tests for Market Regime Classifier."""

import numpy as np
import pandas as pd
import pytest

from dao_vang.alpha_lab.regime_classifier import (
    MarketRegime,
    classify_market_regimes,
    compute_adx,
    compute_bollinger_bandwidth,
    get_current_regime,
)


@pytest.fixture
def trending_bull_data() -> pd.DataFrame:
    """Strong uptrend prices."""
    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    prices = np.linspace(100, 200, 100)
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + 1.0,
            "low": prices - 0.5,
            "close": prices + 0.5,
        },
        index=dates,
    )


@pytest.fixture
def sideway_data() -> pd.DataFrame:
    """Sideway range prices."""
    dates = pd.date_range("2026-01-01", periods=100, freq="1h")
    prices = 100.0 + np.sin(np.linspace(0, 20, 100)) * 2.0
    return pd.DataFrame(
        {
            "open": prices,
            "high": prices + 0.5,
            "low": prices - 0.5,
            "close": prices,
        },
        index=dates,
    )


def test_compute_adx(trending_bull_data: pd.DataFrame) -> None:
    adx_df = compute_adx(trending_bull_data, period=14)
    assert "adx" in adx_df.columns
    assert "plus_di" in adx_df.columns
    assert "minus_di" in adx_df.columns
    # In a strong uptrend, plus_di should exceed minus_di
    assert adx_df["plus_di"].iloc[-1] > adx_df["minus_di"].iloc[-1]


def test_compute_bollinger_bandwidth(sideway_data: pd.DataFrame) -> None:
    bb_w = compute_bollinger_bandwidth(sideway_data["close"], period=20)
    assert len(bb_w) == len(sideway_data)
    assert (bb_w >= 0).all()


def test_classify_market_regimes(trending_bull_data: pd.DataFrame) -> None:
    classified = classify_market_regimes(trending_bull_data)
    assert "regime" in classified.columns
    assert "allow_short" in classified.columns
    assert "allow_long" in classified.columns
    assert classified["regime"].iloc[-1] == MarketRegime.TRENDING_BULL.value
    assert (
        bool(classified["allow_short"].iloc[-1]) is False
    )  # Counter-trend short filtered
    assert bool(classified["allow_long"].iloc[-1]) is True


def test_get_current_regime(sideway_data: pd.DataFrame) -> None:
    state = get_current_regime(sideway_data)
    assert isinstance(state.regime, MarketRegime)
    assert state.risk_multiplier > 0
