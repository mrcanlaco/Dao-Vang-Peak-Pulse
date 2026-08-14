"""Unit tests for Signal Attribution and EV calculation."""

import numpy as np
import pandas as pd
import pytest

from dao_vang.alpha_lab.signal_attribution import (
    calculate_expected_value,
    compute_mfe_mae,
    evaluate_signal_performance,
)


@pytest.fixture
def sample_labeled_events() -> pd.DataFrame:
    dates = pd.date_range("2026-01-01", periods=10, freq="1h")
    df = pd.DataFrame(
        {
            "entry_time": dates,
            "exit_time": dates + pd.Timedelta(hours=4),
            "entry_price": [100.0] * 10,
            "exit_price": [
                95.0,
                96.0,
                94.0,
                95.0,
                102.0,
                93.0,
                101.0,
                94.0,
                95.0,
                103.0,
            ],
            "side": [-1] * 10,
            "label": [1, 1, 1, 1, -1, 1, -1, 1, 1, -1],  # 7 wins, 3 losses
            "raw_return": [
                0.05,
                0.04,
                0.06,
                0.05,
                -0.02,
                0.07,
                -0.01,
                0.06,
                0.05,
                -0.03,
            ],
            "holding_bars": [12, 10, 8, 15, 6, 9, 4, 14, 11, 5],
        },
        index=dates,
    )
    return df


def test_calculate_expected_value() -> None:
    # 70% winrate with +5% win and 30% loss with -2% loss
    returns = np.array([0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, -0.02, -0.02, -0.02])
    ev = calculate_expected_value(returns, fee_bps=8.0)
    assert ev > 0.02  # Expecting positive EV around ~2.8%
    assert ev < 0.05


def test_evaluate_signal_performance(sample_labeled_events: pd.DataFrame) -> None:
    summary = evaluate_signal_performance(sample_labeled_events, fee_bps=8.0)

    assert summary.total_signals == 10
    assert summary.win_count == 7
    assert summary.loss_count == 3
    assert summary.win_rate == 0.70
    assert summary.profit_factor > 2.0
    assert summary.expected_value > 0.0
    assert summary.expected_value_bps > 0.0
    assert summary.sharpe_ratio > 0.0


def test_compute_mfe_mae(sample_labeled_events: pd.DataFrame) -> None:
    # Construct matching price series
    prices_dates = pd.date_range("2026-01-01", periods=100, freq="15min")
    prices_df = pd.DataFrame(
        {
            "open": [100.0] * 100,
            "high": [102.0] * 100,
            "low": [92.0] * 100,
            "close": [95.0] * 100,
        },
        index=prices_dates,
    )

    enriched = compute_mfe_mae(prices=prices_df, labeled_events=sample_labeled_events)

    assert "mfe" in enriched.columns
    assert "mae" in enriched.columns
    assert (enriched["mfe"] >= 0).all()
    assert (enriched["mae"] >= 0).all()
