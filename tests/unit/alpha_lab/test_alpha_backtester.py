"""Integration tests for Alpha Backtester and Meta-Labeling Simulation."""

import numpy as np
import pandas as pd
import pytest

from dao_vang.alpha_lab.alpha_backtester import AlphaBacktester, BacktestComparison


@pytest.fixture
def sample_simulation_market() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Create market price history and a sequence of candidate signals."""
    np.random.seed(42)
    n_bars = 1000
    dates = pd.date_range(start="2026-01-01", periods=n_bars, freq="5min")

    # Generate synthetic price path with alternating regimes
    returns = np.random.normal(0, 0.002, n_bars)
    prices = 100.0 * np.exp(np.cumsum(returns))

    price_df = pd.DataFrame(
        {
            "open": prices,
            "high": prices * (1.0 + np.abs(np.random.normal(0, 0.001, n_bars))),
            "low": prices * (1.0 - np.abs(np.random.normal(0, 0.001, n_bars))),
            "close": prices,
        },
        index=dates,
    )

    # Generate 60 candidate short signals at random intervals
    signal_indices = np.sort(
        np.random.choice(range(50, n_bars - 150), size=60, replace=False)
    )
    sig_dates = dates[signal_indices]

    signals_df = pd.DataFrame(
        {
            "side": [-1] * len(sig_dates),
            "primary_probability": np.random.uniform(0.65, 0.90, len(sig_dates)),
            "taker_buy_ratio": np.random.uniform(0.45, 0.65, len(sig_dates)),
            "oi_change_pct": np.random.normal(0.01, 0.03, len(sig_dates)),
        },
        index=sig_dates,
    )

    return price_df, signals_df


def test_alpha_backtester_simulation(
    sample_simulation_market: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    prices, signals_df = sample_simulation_market

    backtester = AlphaBacktester(
        pt_sl=(2.0, 1.0),
        min_ret=0.005,
        fee_bps=8.0,
        meta_threshold=0.55,
    )

    comparison = backtester.run_simulation(
        prices=prices,
        signals_df=signals_df,
        train_ratio=0.65,
    )

    assert isinstance(comparison, BacktestComparison)
    assert comparison.total_test_signals > 0
    assert comparison.executed_signals <= comparison.total_test_signals
    assert comparison.dropped_signals >= 0
    assert 0.0 <= comparison.pass_rate <= 1.0

    report_dict = comparison.to_dict()
    assert "ev_improvement_bps" in report_dict
    assert "filtered_summary" in report_dict
    assert "unfiltered_summary" in report_dict
