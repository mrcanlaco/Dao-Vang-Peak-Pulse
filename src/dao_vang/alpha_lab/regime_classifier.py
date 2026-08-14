"""Market Regime Classifier.

Detects macro and multi-timeframe market regimes using ADX (trend strength),
Bollinger Bands Width (volatility expansion/contraction), EMA Trend Slope,
and ATR volatility to prevent counter-trend trades and whipsaws.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd


class MarketRegime(str, Enum):
    """Enumeration of recognized macro market regimes."""

    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    HIGH_VOLATILITY_CHOP = "HIGH_VOLATILITY_CHOP"
    SIDEWAY_DISTRIBUTION = "SIDEWAY_DISTRIBUTION"


@dataclass(frozen=True)
class RegimeState:
    """Snapshot of market regime analysis at a specific timestamp."""

    timestamp: pd.Timestamp
    regime: MarketRegime
    adx: float
    bb_width: float
    trend_slope: float
    atr_pct: float
    allow_short: bool
    allow_long: bool
    risk_multiplier: float  # Multiplier to scale position size (e.g., 0.5 in chop)


def compute_adx(
    df: pd.DataFrame,
    period: int = 14,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.DataFrame:
    """Compute Average Directional Index (ADX) and +DI / -DI lines."""
    high = df[high_col].astype(float)
    low = df[low_col].astype(float)
    close = df[close_col].astype(float)

    up_move = high - high.shift(1)
    down_move = low.shift(1) - low

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    atr = tr.rolling(window=period, min_periods=1).mean()
    plus_di = 100 * (
        pd.Series(plus_dm, index=df.index).rolling(window=period, min_periods=1).mean()
        / (atr + 1e-8)
    )
    minus_di = 100 * (
        pd.Series(minus_dm, index=df.index).rolling(window=period, min_periods=1).mean()
        / (atr + 1e-8)
    )

    dx = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di + 1e-8))
    adx = dx.rolling(window=period, min_periods=1).mean()

    return pd.DataFrame(
        {
            "adx": adx.fillna(0.0),
            "plus_di": plus_di.fillna(0.0),
            "minus_di": minus_di.fillna(0.0),
        },
        index=df.index,
    )


def compute_bollinger_bandwidth(
    close: pd.Series,
    period: int = 20,
    num_std: float = 2.0,
) -> pd.Series:
    """Compute normalized Bollinger Bands Width (Upper - Lower) / Middle."""
    sma = close.rolling(window=period, min_periods=1).mean()
    std = close.rolling(window=period, min_periods=1).std().fillna(0.0)
    upper = sma + (num_std * std)
    lower = sma - (num_std * std)
    bb_width = (upper - lower) / (sma + 1e-8)
    return bb_width.fillna(0.0)


def classify_market_regimes(
    df: pd.DataFrame,
    adx_trend_threshold: float = 25.0,
    bb_width_high_pct: float = 75.0,
    high_col: str = "high",
    low_col: str = "low",
    close_col: str = "close",
) -> pd.DataFrame:
    """Classify historical market regimes across all bars in the dataset.

    Parameters
    ----------
    df : pd.DataFrame
        OHLCV DataFrame.
    adx_trend_threshold : float
        Threshold above which market is considered in a strong trend (default: 25.0).
    bb_width_high_pct : float
        Percentile of Bollinger Bandwidth considered as High Volatility / Expansion.

    Returns
    -------
    pd.DataFrame
        Input DataFrame enriched with `regime`, `adx`, `bb_width`, `trend_slope`,
        `allow_short`, `allow_long`, `risk_multiplier`.
    """
    res = df.copy()
    close = res[close_col].astype(float)
    high = res[high_col].astype(float)
    low = res[low_col].astype(float)

    # 1. Trend indicators
    adx_df = compute_adx(
        res, period=14, high_col=high_col, low_col=low_col, close_col=close_col
    )
    res["adx"] = adx_df["adx"]
    res["plus_di"] = adx_df["plus_di"]
    res["minus_di"] = adx_df["minus_di"]

    # 2. Moving Average Trend Slope (EMA 50 vs EMA 200)
    ema50 = close.ewm(span=50, min_periods=1).mean()
    ema200 = close.ewm(span=200, min_periods=1).mean()
    res["trend_slope"] = (ema50 - ema200) / (ema200 + 1e-8)

    # 3. Volatility Width
    res["bb_width"] = compute_bollinger_bandwidth(close, period=20)
    rolling_bb_threshold = (
        res["bb_width"]
        .rolling(window=100, min_periods=20)
        .quantile(bb_width_high_pct / 100.0)
    )
    rolling_bb_threshold = rolling_bb_threshold.fillna(res["bb_width"].median())

    # 4. Relative ATR
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    res["atr_pct"] = (tr.rolling(14, min_periods=1).mean() / close).clip(lower=1e-4)

    # Classification logic
    regimes = []
    allow_shorts = []
    allow_longs = []
    risk_multipliers = []

    for i in range(len(res)):
        row_adx = res["adx"].iloc[i]
        row_slope = res["trend_slope"].iloc[i]
        row_plus_di = res["plus_di"].iloc[i]
        row_minus_di = res["minus_di"].iloc[i]
        row_bb = res["bb_width"].iloc[i]
        row_bb_thresh = rolling_bb_threshold.iloc[i]

        if row_adx >= adx_trend_threshold:
            if row_slope > 0 and row_plus_di > row_minus_di:
                reg = MarketRegime.TRENDING_BULL
                a_short = False  # Avoid counter-trend shorting in bull trend
                a_long = True
                risk_mult = 1.0
            else:
                reg = MarketRegime.TRENDING_BEAR
                a_short = True
                a_long = False
                risk_mult = 1.0
        elif row_bb >= row_bb_thresh:
            reg = MarketRegime.HIGH_VOLATILITY_CHOP
            a_short = True
            a_long = True
            risk_mult = 0.5  # Reduce position size during high volatility whipsaws
        else:
            reg = MarketRegime.SIDEWAY_DISTRIBUTION
            a_short = True  # Ideal for PeakPulse distribution setups
            a_long = True
            risk_mult = 1.0

        regimes.append(reg.value)
        allow_shorts.append(a_short)
        allow_longs.append(a_long)
        risk_multipliers.append(risk_mult)

    res["regime"] = regimes
    res["allow_short"] = allow_shorts
    res["allow_long"] = allow_longs
    res["risk_multiplier"] = risk_multipliers

    return res


def get_current_regime(df: pd.DataFrame) -> RegimeState:
    """Analyze the latest bar and return current regime state."""
    classified = classify_market_regimes(df)
    latest = classified.iloc[-1]
    ts = (
        classified.index[-1]
        if isinstance(classified.index, pd.DatetimeIndex)
        else pd.Timestamp.now()
    )

    return RegimeState(
        timestamp=ts,
        regime=MarketRegime(latest["regime"]),
        adx=float(latest["adx"]),
        bb_width=float(latest["bb_width"]),
        trend_slope=float(latest["trend_slope"]),
        atr_pct=float(latest["atr_pct"]),
        allow_short=bool(latest["allow_short"]),
        allow_long=bool(latest["allow_long"]),
        risk_multiplier=float(latest["risk_multiplier"]),
    )
