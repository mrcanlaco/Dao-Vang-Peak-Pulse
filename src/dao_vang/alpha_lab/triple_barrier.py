"""Triple-Barrier Method for Financial Event Labeling.

Implements the Marcos López de Prado Triple-Barrier labeling technique
with dynamic volatility scaling (ATR / return volatility), asymmetric profit-taking
and stop-loss boundaries, and vertical expiration barriers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd


@dataclass(frozen=True)
class BarrierConfig:
    """Configuration for Triple-Barrier Labeling."""

    pt_multiplier: float = 2.0  # Multiplier for Take Profit (e.g., 2 * volatility)
    sl_multiplier: float = 1.0  # Multiplier for Stop Loss (e.g., 1 * volatility)
    min_return: float = 0.005  # Minimum return threshold (0.5%)
    max_holding_bars: int = 144  # 144 bars of 5m = 12h (or timedelta)
    time_barrier_hours: float | None = 12.0  # Explicit time barrier in hours


def compute_atr(
    df: pd.DataFrame,
    period: int = 14,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.Series:
    """Compute Average True Range (ATR) as fractional volatility (ATR / Close)."""
    high = df[high_col].astype(float)
    low = df[low_col].astype(float)
    close = df[close_col].astype(float)
    prev_close = close.shift(1)

    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean()
    # Normalize by close price to get relative volatility percentage
    rel_atr = (atr / close).clip(lower=1e-4)
    return rel_atr


def compute_daily_volatility(
    close: pd.Series,
    span: int = 100,
) -> pd.Series:
    """Compute Exponential Moving Average of return standard deviation."""
    returns = close.pct_change()
    vol = returns.ewm(span=span, min_periods=10).std()
    return vol.fillna(vol.median() if not vol.dropna().empty else 0.01)


def apply_triple_barrier(
    prices: pd.DataFrame,
    events: pd.DataFrame,
    pt_sl: list[float] | tuple[float, float] = (2.0, 1.0),
    min_ret: float = 0.005,
    volatility: pd.Series | None = None,
    time_horizon_bars: int = 144,
    time_horizon_hours: float | None = None,
    price_cols: tuple[str, str, str, str] = ("open", "high", "low", "close"),
    default_side: Literal[-1, 1] = -1,
) -> pd.DataFrame:
    """Apply Marcos López de Prado's Triple Barrier Method.

    Parameters
    ----------
    prices : pd.DataFrame
        Historical price data with DateTimeIndex or datetime column.
        Must contain [open, high, low, close].
    events : pd.DataFrame
        Signal events to label. Must contain index matching prices or timestamp column.
        Optional column 'side': 1 for Long, -1 for Short. If missing, uses default_side.
    pt_sl : list[float] or tuple[float, float]
        Multipliers for [Take Profit, Stop Loss] relative to volatility.
    min_ret : float
        Minimum absolute barrier distance in return space.
    volatility : pd.Series, optional
        Precomputed volatility series aligned with prices. If None, computes ATR.
    time_horizon_bars : int
        Maximum number of bars before the vertical time barrier expires.
    time_horizon_hours : float, optional
        If specified and timestamps are datetime-aware, overrides time_horizon_bars.
    price_cols : tuple[str, str, str, str]
        Column names for (open, high, low, close).
    default_side : Literal[-1, 1]
        Default trade side if not present in events (-1 for Short, 1 for Long).

    Returns
    -------
    pd.DataFrame
        Labeled events with columns:
        - `entry_time`: Timestamp of signal entry
        - `entry_price`: Price at signal entry
        - `side`: Trade direction (+1 Long, -1 Short)
        - `target_vol`: Volatility at entry
        - `tp_price`: Upper/Lower Take Profit price barrier
        - `sl_price`: Stop Loss price barrier
        - `exit_time`: Timestamp when barrier touched or expired
        - `exit_price`: Price at exit
        - `touch_type`: 'tp', 'sl', or 'time'
        - `label`: +1 (Hit TP), -1 (Hit SL), 0 (Expired at Time Barrier)
        - `raw_return`: Realized arithmetic return (accounting for side)
        - `holding_bars`: Number of bars trade was active
    """
    open_col, high_col, low_col, close_col = price_cols

    # Ensure clean price index
    prices_df = prices.copy()
    if not isinstance(prices_df.index, pd.DatetimeIndex):
        if "timestamp" in prices_df.columns:
            prices_df["timestamp"] = pd.to_datetime(prices_df["timestamp"])
            prices_df = prices_df.set_index("timestamp")
        elif "open_time" in prices_df.columns:
            prices_df["open_time"] = pd.to_datetime(prices_df["open_time"])
            prices_df = prices_df.set_index("open_time")

    prices_df = prices_df.sort_index()

    # Calculate volatility if not provided
    if volatility is None:
        vol_series = compute_atr(
            prices_df,
            period=14,
            high_col=high_col,
            low_col=low_col,
            close_col=close_col,
        )
    else:
        vol_series = volatility.reindex(prices_df.index).ffill().bfill()

    pt_mult, sl_mult = pt_sl

    results = []

    # Ensure events timestamps are aligned
    events_df = events.copy()
    if not isinstance(events_df.index, pd.DatetimeIndex):
        if "timestamp" in events_df.columns:
            events_df["timestamp"] = pd.to_datetime(events_df["timestamp"])
            events_df = events_df.set_index("timestamp")
        elif "open_time" in events_df.columns:
            events_df["open_time"] = pd.to_datetime(events_df["open_time"])
            events_df = events_df.set_index("open_time")

    for t0, event_row in events_df.iterrows():
        # Find integer location of t0 in prices
        if t0 not in prices_df.index:
            # Nearest preceding index
            locs = prices_df.index.get_indexer([t0], method="ffill")
            if locs[0] == -1:
                continue
            idx_start = locs[0]
            actual_t0 = prices_df.index[idx_start]
        else:
            idx_start = prices_df.index.get_loc(t0)
            if isinstance(idx_start, slice):
                idx_start = idx_start.start
            actual_t0 = t0

        entry_price = float(prices_df.iloc[idx_start][close_col])
        entry_vol = float(vol_series.iloc[idx_start])
        target_vol = max(entry_vol, min_ret)

        side = int(event_row.get("side", default_side))
        if side not in (1, -1):
            side = default_side

        # Calculate Barrier widths
        tp_width = target_vol * pt_mult
        sl_width = target_vol * sl_mult

        if side == 1:  # LONG
            tp_price = entry_price * (1.0 + tp_width)
            sl_price = entry_price * (1.0 - sl_width)
        else:  # SHORT
            tp_price = entry_price * (1.0 - tp_width)
            sl_price = entry_price * (1.0 + sl_width)

        # Determine time horizon end
        if time_horizon_hours is not None:
            t1 = actual_t0 + pd.Timedelta(hours=time_horizon_hours)
            future_slice = prices_df.loc[actual_t0:t1]
        else:
            idx_end = min(idx_start + time_horizon_bars + 1, len(prices_df))
            future_slice = prices_df.iloc[idx_start:idx_end]

        if len(future_slice) <= 1:
            continue

        # Iterate forward bar by bar from t0 + 1
        touch_type = "time"
        touch_idx = len(future_slice) - 1
        exit_time = future_slice.index[-1]
        exit_price = float(future_slice.iloc[-1][close_col])
        label = 0

        for i in range(1, len(future_slice)):
            bar = future_slice.iloc[i]
            bar_high = float(bar[high_col])
            bar_low = float(bar[low_col])
            bar_time = future_slice.index[i]

            if side == 1:  # Long
                hit_tp = bar_high >= tp_price
                hit_sl = bar_low <= sl_price
            else:  # Short
                hit_tp = bar_low <= tp_price
                hit_sl = bar_high >= sl_price

            # If both hit in the same bar, assume conservative outcome (SL hit)
            if hit_tp and hit_sl:
                touch_type = "sl"
                exit_time = bar_time
                exit_price = sl_price
                label = -1
                touch_idx = i
                break
            elif hit_tp:
                touch_type = "tp"
                exit_time = bar_time
                exit_price = tp_price
                label = 1
                touch_idx = i
                break
            elif hit_sl:
                touch_type = "sl"
                exit_time = bar_time
                exit_price = sl_price
                label = -1
                touch_idx = i
                break

        # Calculate realized return
        if side == 1:  # Long
            raw_ret = (exit_price - entry_price) / entry_price
        else:  # Short
            raw_ret = (entry_price - exit_price) / entry_price

        results.append(
            {
                "entry_time": actual_t0,
                "entry_price": entry_price,
                "side": side,
                "target_vol": target_vol,
                "tp_price": tp_price,
                "sl_price": sl_price,
                "exit_time": exit_time,
                "exit_price": exit_price,
                "touch_type": touch_type,
                "label": label,
                "raw_return": raw_ret,
                "holding_bars": touch_idx,
            }
        )

    if not results:
        return pd.DataFrame(
            columns=[
                "entry_time",
                "entry_price",
                "side",
                "target_vol",
                "tp_price",
                "sl_price",
                "exit_time",
                "exit_price",
                "touch_type",
                "label",
                "raw_return",
                "holding_bars",
            ]
        )

    res_df = pd.DataFrame(results)
    res_df = res_df.set_index("entry_time")
    return res_df
