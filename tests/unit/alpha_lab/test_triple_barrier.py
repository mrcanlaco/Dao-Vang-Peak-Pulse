"""Unit tests for Triple-Barrier labeling."""

import numpy as np
import pandas as pd
import pytest

from dao_vang.alpha_lab.triple_barrier import (
    apply_triple_barrier,
    compute_atr,
    compute_daily_volatility,
)


@pytest.fixture
def sample_price_data() -> pd.DataFrame:
    """Generate synthetic 5-minute price series with known trends."""
    dates = pd.date_range(start="2026-01-01 00:00:00", periods=200, freq="5min")
    # Base price starting at 100 with a slight downward trend (ideal for short test)
    prices = [100.0]
    for i in range(1, 200):
        if i < 50:
            change = -0.3  # dropping
        elif i < 100:
            change = 0.5  # rising
        else:
            change = np.random.normal(0, 0.2)
        prices.append(prices[-1] + change)

    prices = np.array(prices)
    df = pd.DataFrame(
        {
            "open": prices,
            "high": prices + 0.5,
            "low": prices - 0.5,
            "close": prices,
        },
        index=dates,
    )
    return df


def test_compute_atr(sample_price_data: pd.DataFrame) -> None:
    atr = compute_atr(sample_price_data, period=14)
    assert len(atr) == len(sample_price_data)
    assert (atr > 0).all()
    assert isinstance(atr, pd.Series)


def test_compute_daily_volatility(sample_price_data: pd.DataFrame) -> None:
    vol = compute_daily_volatility(sample_price_data["close"], span=50)
    assert len(vol) == len(sample_price_data)
    assert (vol >= 0).all()


def test_apply_triple_barrier_short_win(sample_price_data: pd.DataFrame) -> None:
    # Event at t=0 when price will drop from 100 down towards 85
    event_time = sample_price_data.index[0]
    events = pd.DataFrame({"side": [-1]}, index=[event_time])

    labeled = apply_triple_barrier(
        prices=sample_price_data,
        events=events,
        pt_sl=(1.0, 2.0),
        min_ret=0.01,
        time_horizon_bars=40,
    )

    assert len(labeled) == 1
    row = labeled.iloc[0]
    assert row["side"] == -1
    assert row["touch_type"] == "tp"
    assert row["label"] == 1
    assert row["raw_return"] > 0


def test_apply_triple_barrier_long_loss(sample_price_data: pd.DataFrame) -> None:
    # Long event at t=0 when price will drop
    event_time = sample_price_data.index[0]
    events = pd.DataFrame({"side": [1]}, index=[event_time])

    labeled = apply_triple_barrier(
        prices=sample_price_data,
        events=events,
        pt_sl=(2.0, 0.5),
        min_ret=0.01,
        time_horizon_bars=40,
    )

    assert len(labeled) == 1
    row = labeled.iloc[0]
    assert row["side"] == 1
    assert row["touch_type"] == "sl"
    assert row["label"] == -1
    assert row["raw_return"] < 0
