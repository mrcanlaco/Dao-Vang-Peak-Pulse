"""Signal Attribution and Quantitative Performance Analytics.

Calculates Maximum Favorable Excursion (MFE), Maximum Adverse Excursion (MAE),
Expected Value (EV), Win Rate, Profit Factor, and Regime Performance.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PerformanceSummary:
    """Comprehensive financial and statistical metrics for trade signals."""

    total_signals: int
    win_count: int
    loss_count: int
    expired_count: int
    win_rate: float
    profit_factor: float
    expected_value: float  # Arithmetic EV per trade
    expected_value_bps: float  # EV in basis points
    avg_win_return: float
    avg_loss_return: float
    max_favorable_excursion_mean: float  # Average MFE
    max_adverse_excursion_mean: float  # Average MAE
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    avg_holding_bars: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_mfe_mae(
    prices: pd.DataFrame,
    labeled_events: pd.DataFrame,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.DataFrame:
    """Calculate Maximum Favorable Excursion (MFE) and Maximum Adverse Excursion (MAE).

    Parameters
    ----------
    prices : pd.DataFrame
        Historical price data with DateTimeIndex.
    labeled_events : pd.DataFrame
        Output of apply_triple_barrier with entry_time, exit_time, entry_price, side.

    Returns
    -------
    pd.DataFrame
        labeled_events enriched with `mfe`, `mae`, `mfe_mae_ratio`.
    """
    df = labeled_events.copy()
    prices_df = prices.sort_index()

    mfes = []
    maes = []

    for _, row in df.iterrows():
        entry_time = row.get("entry_time", getattr(row, "name", None))
        exit_time = row.get("exit_time", None)
        entry_price = float(row["entry_price"])
        side = int(row.get("side", -1))

        if entry_time is None or exit_time is None:
            mfes.append(0.0)
            maes.append(0.0)
            continue

        trade_slice = prices_df.loc[entry_time:exit_time]
        if len(trade_slice) <= 1:
            mfes.append(0.0)
            maes.append(0.0)
            continue

        highest = float(trade_slice[high_col].max())
        lowest = float(trade_slice[low_col].min())

        if side == 1:  # Long
            mfe = (highest - entry_price) / entry_price
            mae = (entry_price - lowest) / entry_price
        else:  # Short
            mfe = (entry_price - lowest) / entry_price
            mae = (highest - entry_price) / entry_price

        mfes.append(max(mfe, 0.0))
        maes.append(max(mae, 0.0))

    df["mfe"] = mfes
    df["mae"] = maes
    df["mfe_mae_ratio"] = df["mfe"] / df["mae"].replace(0.0, 1e-4)

    return df


def calculate_expected_value(
    returns: pd.Series | np.ndarray,
    fee_bps: float = 8.0,  # 8 bps = 0.08% roundtrip fee + slippage
) -> float:
    """Calculate the Expected Value (EV) per trade accounting for fees and slippage."""
    arr = np.asarray(returns)
    if len(arr) == 0:
        return 0.0

    fee_rate = fee_bps / 10000.0
    net_returns = arr - fee_rate

    wins = net_returns[net_returns > 0]
    losses = net_returns[net_returns <= 0]

    p_win = len(wins) / len(net_returns)
    p_loss = 1.0 - p_win

    avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
    avg_loss = float(np.mean(np.abs(losses))) if len(losses) > 0 else 0.0

    ev = (p_win * avg_win) - (p_loss * avg_loss)
    return ev


def evaluate_signal_performance(
    labeled_events: pd.DataFrame,
    fee_bps: float = 8.0,
    annualization_factor: float = 365.25 * 24 * 12,  # 5-minute bars in a year
) -> PerformanceSummary:
    """Compute complete quantitative performance summary for a set of labeled signals.

    Parameters
    ----------
    labeled_events : pd.DataFrame
        Events labeled by Triple-Barrier and optionally enriched with MFE/MAE.
    fee_bps : float
        Roundtrip taker fee + slippage in basis points.
    annualization_factor : float
        Factor to annualize Sharpe/Sortino ratios based on bar frequency.

    Returns
    -------
    PerformanceSummary
        Statistical report with win rate, profit factor, EV, and risk metrics.
    """
    total = len(labeled_events)
    if total == 0:
        return PerformanceSummary(
            total_signals=0,
            win_count=0,
            loss_count=0,
            expired_count=0,
            win_rate=0.0,
            profit_factor=0.0,
            expected_value=0.0,
            expected_value_bps=0.0,
            avg_win_return=0.0,
            avg_loss_return=0.0,
            max_favorable_excursion_mean=0.0,
            max_adverse_excursion_mean=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            max_drawdown=0.0,
            avg_holding_bars=0.0,
        )

    labels = labeled_events["label"].to_numpy()
    raw_returns = labeled_events["raw_return"].to_numpy()
    fee_rate = fee_bps / 10000.0
    net_returns = raw_returns - fee_rate

    win_count = int(np.sum(labels == 1))
    loss_count = int(np.sum(labels == -1))
    expired_count = int(np.sum(labels == 0))

    win_rate = win_count / total if total > 0 else 0.0

    gains = net_returns[net_returns > 0]
    losses = net_returns[net_returns <= 0]

    sum_gains = float(np.sum(gains)) if len(gains) > 0 else 0.0
    sum_losses = float(np.abs(np.sum(losses))) if len(losses) > 0 else 0.0

    profit_factor = (
        (sum_gains / sum_losses)
        if sum_losses > 1e-6
        else (99.0 if sum_gains > 0 else 0.0)
    )

    avg_win_ret = float(np.mean(gains)) if len(gains) > 0 else 0.0
    avg_loss_ret = float(np.mean(losses)) if len(losses) > 0 else 0.0

    ev = calculate_expected_value(raw_returns, fee_bps=fee_bps)
    ev_bps = ev * 10000.0

    # MFE / MAE means
    mfe_mean = (
        float(labeled_events["mfe"].mean()) if "mfe" in labeled_events.columns else 0.0
    )
    mae_mean = (
        float(labeled_events["mae"].mean()) if "mae" in labeled_events.columns else 0.0
    )

    # Risk metrics: Sharpe & Sortino
    mean_ret = float(np.mean(net_returns))
    std_ret = float(np.std(net_returns)) if len(net_returns) > 1 else 1e-4

    downside_returns = net_returns[net_returns < 0]
    downside_std = (
        float(np.std(downside_returns)) if len(downside_returns) > 1 else 1e-4
    )

    sharpe = (mean_ret / (std_ret + 1e-8)) * np.sqrt(min(total, 252))
    sortino = (mean_ret / (downside_std + 1e-8)) * np.sqrt(min(total, 252))

    # Max Drawdown of cumulative returns curve
    cum_returns = np.cumprod(1.0 + net_returns)
    running_max = np.maximum.accumulate(cum_returns)
    drawdowns = (cum_returns - running_max) / running_max
    max_dd = float(np.min(drawdowns)) if len(drawdowns) > 0 else 0.0

    avg_holding = (
        float(labeled_events["holding_bars"].mean())
        if "holding_bars" in labeled_events.columns
        else 0.0
    )

    return PerformanceSummary(
        total_signals=total,
        win_count=win_count,
        loss_count=loss_count,
        expired_count=expired_count,
        win_rate=win_rate,
        profit_factor=profit_factor,
        expected_value=ev,
        expected_value_bps=ev_bps,
        avg_win_return=avg_win_ret,
        avg_loss_return=avg_loss_ret,
        max_favorable_excursion_mean=mfe_mean,
        max_adverse_excursion_mean=mae_mean,
        sharpe_ratio=sharpe,
        sortino_ratio=sortino,
        max_drawdown=max_dd,
        avg_holding_bars=avg_holding,
    )
