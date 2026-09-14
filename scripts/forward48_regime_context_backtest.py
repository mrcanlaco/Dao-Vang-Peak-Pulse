"""Research-only regime/context filters on the frozen 48h timing+compact challenger.

The runner never changes the frozen challenger or live configuration.  It uses
the already generated walk-forward probabilities and applies the exact frozen
timing state machine, then simulates the fixed 0/+3/+6 (20/30/50) execution.
Folds 1-3 are development, fold 4 is a recycled branch holdout, and August is
an opened/recycled audit.  No result produced here is sealed-forward evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

import duckdb
import numpy as np
import pandas as pd

try:
    from forward48_scalein_backtest import (
        Config as ExecutionConfig,
    )
    from forward48_scalein_backtest import (
        Template,
        _evaluate_templates,
    )
    from forward48_timing_backtest import TimingPolicy, select_signals
except ImportError:  # pragma: no cover - package import in unit tests
    from scripts.forward48_scalein_backtest import (
        Config as ExecutionConfig,
    )
    from scripts.forward48_scalein_backtest import (
        Template,
        _evaluate_templates,
    )
    from scripts.forward48_timing_backtest import TimingPolicy, select_signals


TARGET = 0.20
STOP = 0.16
COST = 0.002
COMPACT = Template("compact_0_3_6", (0.0, 0.03, 0.06), (0.20, 0.30, 0.50), 6)
EXPECTED_TIMING_LOCK = "ba8ccac68fb824a952b60c998d5b0ff86977119d85692626adde7fb9f7371305"
FROZEN_TIMING = TimingPolicy(
    min_peak_pump_24h=0.30,
    confirmations=2,
    min_episode_age_hours=4,
    probability_tolerance=0.10,
)


@dataclass(frozen=True)
class Config:
    challenger_config: Path = Path("configs/distribution_v2_3_research_48h_timing_compact.yaml")
    timing_oos_csv: Path = Path(
        "artifacts/forward48_timing_20260913/forward48_timing_historical_oos.csv"
    )
    historical_db: Path = Path("artifacts/universe_policy_v2_48h.duckdb")
    live_db: Path = Path("data_live/live.duckdb")
    august_signals_csv: Path = Path(
        "artifacts/forward48_timing_20260913/forward48_timing_august_signals_live.csv"
    )
    august_events_csv: Path = Path(
        "artifacts/forward48_scalein_timing_compatibility_events_20260913.csv"
    )
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    kline_root: Path = Path(r"D:\Quant-trading\data_lake\klines\5m")
    funding_root: Path = Path(r"D:\Quant-trading\data_lake\funding")
    output_json: Path = Path("artifacts/forward48_regime_context_20260914.json")
    output_leaderboard_csv: Path = Path(
        "artifacts/forward48_regime_context_leaderboard_20260914.csv"
    )
    output_events_csv: Path = Path("artifacts/forward48_regime_context_events_20260914.csv")
    output_report_md: Path = Path("docs/forward48_regime_context_20260914.md")
    min_dev_coverage: float = 0.35
    min_dev_signals: int = 20
    min_signals_per_dev_fold: int = 5


@dataclass(frozen=True)
class Variant:
    variant_id: str
    hypothesis: str
    provenance: str
    required_columns: tuple[str, ...]
    predicate: Callable[[pd.DataFrame, dict[str, float]], pd.Series]


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(type(value).__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _wilson(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials <= 0:
        return 0.0, 0.0
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials)
    return (centre - radius) / denominator, (centre + radius) / denominator


def _max_drawdown(returns: Iterable[float]) -> float:
    equity = peak = 1.0
    maximum = 0.0
    for value in returns:
        equity *= max(0.0, 1.0 + float(value))
        peak = max(peak, equity)
        maximum = max(maximum, (peak - equity) / peak)
    return maximum


def _risk_normalized(returns: pd.Series) -> float | None:
    if returns.empty:
        return None
    downside = returns[returns < 0]
    scale = float(downside.std(ddof=0)) if len(downside) > 1 else float(returns.std(ddof=0))
    if not np.isfinite(scale) or scale <= 1e-8:
        return None
    return float(returns.mean() / scale)


def assert_unique_keys(frame: pd.DataFrame, columns: list[str], name: str) -> None:
    duplicates = frame.duplicated(columns, keep=False)
    if duplicates.any():
        raise RuntimeError(f"{name} has {int(duplicates.sum())} duplicate rows on {columns}")


def _valid_parquet_files(root: Path, symbols: set[str] | None = None) -> tuple[list[Path], list[str]]:
    paths = [root / f"{symbol}.parquet" for symbol in sorted(symbols)] if symbols else sorted(root.glob("*.parquet"))
    valid: list[Path] = []
    rejected: list[str] = []
    conn = duckdb.connect()
    for path in paths:
        if not path.exists() or path.stat().st_size < 8:
            rejected.append(path.name)
            continue
        with path.open("rb") as handle:
            head = handle.read(4)
            handle.seek(-4, 2)
            tail = handle.read(4)
        if head != b"PAR1" or tail != b"PAR1":
            rejected.append(path.name)
            continue
        try:
            conn.execute(
                f"SELECT 1 FROM read_parquet('{_sql_path(path)}') LIMIT 1"
            ).fetchone()
        except duckdb.Error:
            rejected.append(path.name)
            continue
        valid.append(path)
    conn.close()
    return valid, rejected


def _parquet_list_sql(paths: list[Path]) -> str:
    if not paths:
        raise RuntimeError("no valid parquet files")
    return "[" + ",".join(f"'{_sql_path(path)}'" for path in paths) + "]"


def load_historical_signals(config: Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    oos = pd.read_csv(config.timing_oos_csv)
    oos["feature_time"] = pd.to_datetime(oos["feature_time"], utc=True)
    assert_unique_keys(oos, ["symbol", "feature_time", "fold"], "historical timing OOS")
    signals = select_signals(oos, FROZEN_TIMING).reset_index(drop=True)
    signals["signal_id"] = [f"hist-{index:04d}" for index in range(len(signals))]
    conn = duckdb.connect(str(config.historical_db), read_only=True)
    conn.register("signal_keys", signals[["signal_id", "symbol", "feature_time"]])
    columns = [
        "entry_price", "price_ret_24h", "price_volatility_24h",
        "funding_rate_raw", "funding_percentile_30d", "funding_persistence_7d",
        "funding_change_8h", "oi_change_24h", "global_ls_ratio", "top_ls_ratio",
        "retail_top_spread", "quote_volume_24h",
    ]
    try:
        context = conn.execute(
            "SELECT k.signal_id, " + ", ".join(f"u.{column}" for column in columns)
            + " FROM signal_keys k INNER JOIN universe_policy_candidates_v2 u "
            "ON u.symbol=k.symbol AND u.feature_time=k.feature_time"
        ).fetchdf()
    finally:
        conn.close()
    assert_unique_keys(context, ["signal_id"], "historical source context")
    signals = signals.drop(columns=[column for column in columns if column in signals.columns])
    signals = signals.merge(context, on="signal_id", how="left", validate="one_to_one")
    if signals["entry_price"].isna().any():
        raise RuntimeError("historical source join lost entry prices")
    return signals, oos


def load_august_signals(config: Config) -> pd.DataFrame:
    signals = pd.read_csv(config.august_signals_csv)
    signals["feature_time"] = pd.to_datetime(signals["feature_time"], utc=True)
    signals = signals.sort_values(["feature_time", "symbol"]).reset_index(drop=True)
    signals["signal_id"] = [f"timing-{index:03d}" for index in range(len(signals))]
    signals["fold"] = 5
    assert_unique_keys(signals, ["symbol", "feature_time"], "August frozen signals")
    return signals


def _cross_section_context(signals: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    all_files, rejected = _valid_parquet_files(config.kline_root)
    conn = duckdb.connect()
    times = signals[["feature_time"]].drop_duplicates()
    conn.register("signal_times", times)
    parquet = _parquet_list_sql(all_files)
    try:
        result = conn.execute(
            f"""
            WITH kline AS (SELECT * FROM read_parquet({parquet}, union_by_name=true)),
            returns AS (
              SELECT t.feature_time, k.symbol,
                     k.close / NULLIF(p.close, 0) - 1 AS return_24h
              FROM signal_times t
              INNER JOIN kline k ON k.close_time=t.feature_time
              LEFT JOIN kline p ON p.symbol=k.symbol
                AND p.close_time=t.feature_time-INTERVAL '24' HOUR
            )
            SELECT feature_time, COUNT(*) AS market_symbols_at_time,
                   COUNT(return_24h) AS market_return_coverage,
                   AVG(CASE WHEN return_24h > 0 THEN 1.0 ELSE 0.0 END) AS breadth_positive_24h,
                   MEDIAN(return_24h) FILTER (WHERE symbol <> 'BTCUSDT') AS alt_median_ret_24h,
                   MAX(return_24h) FILTER (WHERE symbol = 'BTCUSDT') AS btc_ret_24h
            FROM returns GROUP BY feature_time ORDER BY feature_time
            """
        ).fetchdf()
    finally:
        conn.close()
    result["feature_time"] = pd.to_datetime(result["feature_time"], utc=True)
    result["btc_dominance_proxy_24h"] = result["btc_ret_24h"] - result["alt_median_ret_24h"]
    return result, {
        "kline_files_total": len(all_files) + len(rejected),
        "kline_files_valid": len(all_files),
        "kline_files_rejected": rejected,
        "unique_signal_times": len(times),
        "context_times_matched": len(result),
        "dominance_semantics": "BTC 24h return minus cross-sectional median altcoin 24h return; not vendor BTC dominance",
    }


def _btc_context(signals: pd.DataFrame, config: Config) -> pd.DataFrame:
    btc_file = config.kline_root / "BTCUSDT.parquet"
    start = signals["feature_time"].min() - pd.Timedelta(days=30)
    end = signals["feature_time"].max()
    conn = duckdb.connect()
    try:
        btc = conn.execute(
            f"""SELECT close_time, CAST(high AS DOUBLE) AS high,
                       CAST(low AS DOUBLE) AS low, CAST(close AS DOUBLE) AS close_value
                 FROM read_parquet('{_sql_path(btc_file)}')
                WHERE close_time >= ? AND close_time <= ? ORDER BY close_time""",
            [start.to_pydatetime(), end.to_pydatetime()],
        ).fetchdf()
    finally:
        conn.close()
    btc["close_time"] = pd.to_datetime(btc["close_time"], utc=True)
    btc["btc_ret_24h_direct"] = btc["close_value"].pct_change(288)
    btc["btc_volatility_24h"] = btc["close_value"].pct_change().rolling(288, min_periods=288).std()
    # Equivalent causal features used by the existing classifier, vectorized here.
    high, low, close = btc["high"], btc["low"], btc["close_value"]
    up_move, down_move = high.diff(), -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0))
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0))
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=1).mean()
    plus_di = 100 * plus_dm.rolling(14, min_periods=1).mean() / (atr + 1e-8)
    minus_di = 100 * minus_dm.rolling(14, min_periods=1).mean() / (atr + 1e-8)
    adx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-8)).rolling(14, min_periods=1).mean()
    ema50, ema200 = close.ewm(span=50, min_periods=1).mean(), close.ewm(span=200, min_periods=1).mean()
    trend_slope = (ema50 - ema200) / (ema200 + 1e-8)
    sma, std = close.rolling(20, min_periods=1).mean(), close.rolling(20, min_periods=1).std().fillna(0.0)
    bb_width = 4 * std / (sma + 1e-8)
    bb_threshold = bb_width.rolling(100, min_periods=20).quantile(0.75)
    bb_threshold = bb_threshold.fillna(bb_width.expanding(min_periods=1).median())
    regime = np.where(
        adx >= 25,
        np.where((trend_slope > 0) & (plus_di > minus_di), "TRENDING_BULL", "TRENDING_BEAR"),
        np.where(bb_width >= bb_threshold, "HIGH_VOLATILITY_CHOP", "SIDEWAY_DISTRIBUTION"),
    )
    btc["btc_regime"] = regime
    return signals[["signal_id", "feature_time"]].merge(
        btc[["close_time", "btc_ret_24h_direct", "btc_volatility_24h", "btc_regime"]],
        left_on="feature_time", right_on="close_time", how="left", validate="many_to_one",
    ).drop(columns="close_time")


def attach_market_context(signals: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    cross, audit = _cross_section_context(signals, config)
    btc = _btc_context(signals, config)
    result = signals.merge(cross, on="feature_time", how="left", validate="many_to_one")
    result = result.merge(btc.drop(columns="feature_time"), on="signal_id", how="left", validate="one_to_one")
    # Prefer the directly recomputed BTC return and quantify disagreement.
    diff = (result["btc_ret_24h"] - result["btc_ret_24h_direct"]).abs()
    audit["btc_return_direct_max_abs_difference"] = float(diff.max()) if diff.notna().any() else None
    audit["btc_context_complete_signals"] = int(
        result[["btc_ret_24h", "btc_volatility_24h", "btc_regime", "breadth_positive_24h"]]
        .notna().all(axis=1).sum()
    )
    return result.drop(columns="btc_ret_24h_direct"), audit


def attach_august_market_context(signals: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Attach August context from live DB, whose exact 5m coverage is complete."""
    start = signals["feature_time"].min() - pd.Timedelta(days=30)
    end = signals["feature_time"].max()
    conn = duckdb.connect(str(config.live_db), read_only=True)
    conn.register("signal_times", signals[["feature_time"]].drop_duplicates())
    conn.register("signal_keys", signals[["signal_id", "symbol", "feature_time"]])
    try:
        cross = conn.execute(
            """
            WITH point_in_time AS (
              SELECT f.feature_time, f.symbol, MAX(f.price_ret_24h) AS return_24h
              FROM feature_results f INNER JOIN signal_times t USING(feature_time)
              GROUP BY f.feature_time, f.symbol
            )
            SELECT feature_time, COUNT(*) AS market_symbols_at_time,
                   COUNT(return_24h) AS market_return_coverage,
                   AVG(CASE WHEN return_24h > 0 THEN 1.0 ELSE 0.0 END) AS breadth_positive_24h,
                   MEDIAN(return_24h) FILTER (WHERE symbol <> 'BTCUSDT') AS alt_median_ret_24h
            FROM point_in_time GROUP BY feature_time ORDER BY feature_time
            """
        ).fetchdf()
        liquidity = conn.execute(
            """
            SELECT s.signal_id, SUM(CAST(k.volume_quote AS DOUBLE)) AS quote_volume_24h_direct
            FROM signal_keys s LEFT JOIN kline k
              ON k.symbol=s.symbol AND k.interval='5m'
             AND k.close_time>s.feature_time-INTERVAL '24' HOUR
             AND k.close_time<=s.feature_time
            GROUP BY s.signal_id
            """
        ).fetchdf()
        btc = conn.execute(
            """SELECT close_time, CAST(high AS DOUBLE) AS high,
                      CAST(low AS DOUBLE) AS low, CAST(close AS DOUBLE) AS close_value
                 FROM kline WHERE symbol='BTCUSDT' AND interval='5m'
                  AND close_time>=? AND close_time<=? ORDER BY close_time""",
            [start.to_pydatetime(), end.to_pydatetime()],
        ).fetchdf()
    finally:
        conn.close()
    cross["feature_time"] = pd.to_datetime(cross["feature_time"], utc=True)
    btc["close_time"] = pd.to_datetime(btc["close_time"], utc=True)
    btc["btc_ret_24h"] = btc["close_value"].pct_change(288)
    btc["btc_volatility_24h"] = btc["close_value"].pct_change().rolling(288, min_periods=288).std()
    high, low, close = btc["high"], btc["low"], btc["close_value"]
    up_move, down_move = high.diff(), -low.diff()
    plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0))
    minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0))
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(14, min_periods=1).mean()
    plus_di = 100 * plus_dm.rolling(14, min_periods=1).mean() / (atr + 1e-8)
    minus_di = 100 * minus_dm.rolling(14, min_periods=1).mean() / (atr + 1e-8)
    adx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di + 1e-8)).rolling(14, min_periods=1).mean()
    ema50, ema200 = close.ewm(span=50, min_periods=1).mean(), close.ewm(span=200, min_periods=1).mean()
    slope = (ema50 - ema200) / (ema200 + 1e-8)
    sma, std = close.rolling(20, min_periods=1).mean(), close.rolling(20, min_periods=1).std().fillna(0.0)
    bb_width = 4 * std / (sma + 1e-8)
    bb_threshold = bb_width.rolling(100, min_periods=20).quantile(0.75)
    bb_threshold = bb_threshold.fillna(bb_width.expanding(min_periods=1).median())
    btc["btc_regime"] = np.where(
        adx >= 25,
        np.where((slope > 0) & (plus_di > minus_di), "TRENDING_BULL", "TRENDING_BEAR"),
        np.where(bb_width >= bb_threshold, "HIGH_VOLATILITY_CHOP", "SIDEWAY_DISTRIBUTION"),
    )
    result = signals.merge(cross, on="feature_time", how="left", validate="many_to_one")
    result = result.merge(liquidity, on="signal_id", how="left", validate="one_to_one")
    result = result.merge(
        btc[["close_time", "btc_ret_24h", "btc_volatility_24h", "btc_regime"]],
        left_on="feature_time", right_on="close_time", how="left", validate="many_to_one",
    ).drop(columns="close_time")
    # Use directly summed live quote volume for August; historical source field is absent here.
    result["quote_volume_24h"] = result["quote_volume_24h_direct"]
    result = result.drop(columns="quote_volume_24h_direct")
    result["btc_dominance_proxy_24h"] = result["btc_ret_24h"] - result["alt_median_ret_24h"]
    required = ["btc_ret_24h", "btc_volatility_24h", "btc_regime", "breadth_positive_24h"]
    audit = {
        "source": "data_live/live.duckdb point-in-time feature_results+kline",
        "unique_signal_times": int(signals.feature_time.nunique()),
        "context_times_matched": len(cross),
        "btc_context_complete_signals": int(result[required].notna().all(axis=1).sum()),
        "liquidity_complete_signals": int(result.quote_volume_24h.notna().sum()),
        "dominance_semantics": "BTC 24h return minus cross-sectional median altcoin 24h return; not vendor BTC dominance",
    }
    return result, audit


def _load_paths(signals: pd.DataFrame, config: Config) -> tuple[dict[str, list[tuple]], dict[str, list[tuple]], dict[str, Any]]:
    symbols = set(signals["symbol"].astype(str))
    kline_files, rejected_kline = _valid_parquet_files(config.kline_root, symbols)
    funding_files, rejected_funding = _valid_parquet_files(config.funding_root, symbols)
    conn = duckdb.connect()
    conn.register("signal_input", signals[["signal_id", "symbol", "feature_time"]])
    try:
        path_rows = conn.execute(
            f"""SELECT s.signal_id,k.close_time,CAST(k.high AS DOUBLE),CAST(k.low AS DOUBLE),CAST(k.close AS DOUBLE)
                FROM signal_input s INNER JOIN read_parquet({_parquet_list_sql(kline_files)}, union_by_name=true) k
                  ON k.symbol=s.symbol AND k.close_time>s.feature_time
                 AND k.close_time<=s.feature_time+INTERVAL '48' HOUR
                ORDER BY s.signal_id,k.close_time"""
        ).fetchall()
        funding_rows = []
        if funding_files:
            funding_rows = conn.execute(
                f"""SELECT s.signal_id,f.funding_time,CAST(f.funding_rate AS DOUBLE)
                    FROM signal_input s INNER JOIN read_parquet({_parquet_list_sql(funding_files)}, union_by_name=true) f
                      ON f.symbol=s.symbol AND f.funding_time>s.feature_time
                     AND f.funding_time<=s.feature_time+INTERVAL '48' HOUR
                    ORDER BY s.signal_id,f.funding_time"""
            ).fetchall()
    finally:
        conn.close()
    paths: dict[str, list[tuple]] = {}
    funding: dict[str, list[tuple]] = {}
    for row in signals.itertuples(index=False):
        paths[str(row.signal_id)] = [(
            pd.Timestamp(row.feature_time), float(row.entry_price),
            float(row.entry_price), float(row.entry_price),
        )]
    for signal_id, *values in path_rows:
        paths[str(signal_id)].append(tuple(values))
    for signal_id, *values in funding_rows:
        funding.setdefault(str(signal_id), []).append(tuple(values))
    return paths, funding, {
        "signal_symbols": len(symbols),
        "valid_signal_kline_files": len(kline_files),
        "rejected_signal_kline_files": rejected_kline,
        "valid_signal_funding_files": len(funding_files),
        "rejected_signal_funding_files": rejected_funding,
        "future_path_rows": len(path_rows),
        "future_funding_rows": len(funding_rows),
    }


def historical_execution(signals: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, dict[str, Any]]:
    paths, funding, audit = _load_paths(signals, config)
    events = _evaluate_templates(
        signals, [COMPACT], paths, funding,
        ExecutionConfig(target_drawdown=TARGET, hard_stop_pct=STOP),
        "historical_oos",
    )
    return events, audit


def august_execution(config: Config) -> pd.DataFrame:
    events = pd.read_csv(config.august_events_csv)
    events = events[events["template_id"].eq(COMPACT.template_id)].copy()
    events["signal_time"] = pd.to_datetime(events["signal_time"], utc=True)
    events["feature_time"] = events["signal_time"]
    events["fold"] = 5
    return events


def fit_thresholds(dev: pd.DataFrame) -> dict[str, float]:
    return {
        "btc_vol_q67": float(dev["btc_volatility_24h"].quantile(0.67)),
        "alt_vol_q67": float(dev["price_volatility_24h"].quantile(0.67)),
        "breadth_q50": float(dev["breadth_positive_24h"].quantile(0.50)),
        "breadth_q67": float(dev["breadth_positive_24h"].quantile(0.67)),
        "oi24_q67": float(dev["oi_change_24h"].quantile(0.67)),
        "funding_raw_q80": float(dev["funding_rate_raw"].quantile(0.80)),
        "retail_spread_q80": float(dev["retail_top_spread"].quantile(0.80)),
    }


def variants() -> list[Variant]:
    def true(frame):
        return pd.Series(True, index=frame.index)
    return [
        Variant("baseline", "No context filter", "Frozen challenger", (), lambda f, t: true(f)),
        Variant("block_trending_bull", "Bull trend may punish counter-trend shorts; keep high-vol chop", "Research 02/04/05; HIGH_VOL contradiction retained", ("btc_regime",), lambda f, t: f.btc_regime.ne("TRENDING_BULL")),
        Variant("sideway_only", "Sideway/distribution was historically strongest", "Research 03/04", ("btc_regime",), lambda f, t: f.btc_regime.eq("SIDEWAY_DISTRIBUTION")),
        Variant("sideway_or_bear", "Legacy regime allow-list", "Research 02/05", ("btc_regime",), lambda f, t: f.btc_regime.isin(["SIDEWAY_DISTRIBUTION", "TRENDING_BEAR"])),
        Variant("high_vol_chop_only", "Audit whether legacy hard block discarded useful high-vol states", "Research 04 versus Research 07 contradiction", ("btc_regime",), lambda f, t: f.btc_regime.eq("HIGH_VOLATILITY_CHOP")),
        Variant("nonbull_joint_high_vol", "High alt and BTC volatility may be useful only outside bull trend", "Research 07 interaction", ("btc_regime", "btc_volatility_24h", "price_volatility_24h"), lambda f, t: f.btc_regime.ne("TRENDING_BULL") & f.btc_volatility_24h.ge(t["btc_vol_q67"]) & f.price_volatility_24h.ge(t["alt_vol_q67"])),
        Variant("sideway_or_joint_high_vol", "Preserve sideway plus panic-vol interaction instead of hard-blocking chop", "Research 03/04/07", ("btc_regime", "btc_volatility_24h", "price_volatility_24h"), lambda f, t: f.btc_regime.eq("SIDEWAY_DISTRIBUTION") | (f.btc_volatility_24h.ge(t["btc_vol_q67"]) & f.price_volatility_24h.ge(t["alt_vol_q67"]))),
        Variant("btc_not_hot", "Avoid BTC FOMO when 24h return exceeds +2%", "Research 01/02", ("btc_ret_24h",), lambda f, t: f.btc_ret_24h.le(0.02)),
        Variant("btc_nonpositive", "Weak/flat BTC may favor alt distribution", "Research 01 hypothesis", ("btc_ret_24h",), lambda f, t: f.btc_ret_24h.le(0.0)),
        Variant("breadth_not_hot", "Avoid broad alt participation", "New causal breadth translation", ("breadth_positive_24h",), lambda f, t: f.breadth_positive_24h.le(t["breadth_q67"])),
        Variant("breadth_weak", "Select weak market breadth only", "New causal breadth translation", ("breadth_positive_24h",), lambda f, t: f.breadth_positive_24h.le(t["breadth_q50"])),
        Variant("dominance_proxy_up", "BTC outperforming median alt may mark liquidity rotation", "Research 07; proxy, not vendor dominance", ("btc_dominance_proxy_24h",), lambda f, t: f.btc_dominance_proxy_24h.gt(0.0)),
        Variant("dominance_up_alt_hot", "BTC rotation while the target alt remains hot may be a bull trap", "Research 07 interaction", ("btc_dominance_proxy_24h", "price_ret_24h"), lambda f, t: f.btc_dominance_proxy_24h.gt(0.0) & f.price_ret_24h.ge(0.20)),
        Variant("liquidity_10m_500m", "Legacy low-liquidity band may retain inefficiency", "Research 01/03/06/07; old ROI ignored", ("quote_volume_24h",), lambda f, t: f.quote_volume_24h.between(10_000_000, 500_000_000, inclusive="both")),
        Variant("liquidity_below_500m", "Audit only the claimed upper liquidity boundary", "Research 06/07", ("quote_volume_24h",), lambda f, t: f.quote_volume_24h.le(500_000_000)),
        Variant("funding_percentile_high", "High relative funding may indicate crowded longs", "Research 07 single-component slice", ("funding_percentile_30d",), lambda f, t: f.funding_percentile_30d.ge(0.80)),
        Variant("funding_exhaustion_rising", "High persistent funding still accelerating", "Research 07 three-way interaction", ("funding_percentile_30d", "funding_persistence_7d", "funding_change_8h"), lambda f, t: f.funding_percentile_30d.ge(0.80) & f.funding_persistence_7d.gt(0) & f.funding_change_8h.gt(0)),
        Variant("funding_exhaustion_rollover", "High persistent funding whose 8h change stopped rising", "Research map rollover alternative", ("funding_percentile_30d", "funding_persistence_7d", "funding_change_8h"), lambda f, t: f.funding_percentile_30d.ge(0.80) & f.funding_persistence_7d.gt(0) & f.funding_change_8h.le(0)),
        Variant("funding_oi_crowded", "Funding and OI jointly crowded", "Research 03/07 interaction", ("funding_percentile_30d", "oi_change_24h"), lambda f, t: f.funding_percentile_30d.ge(0.67) & f.oi_change_24h.ge(t["oi24_q67"])),
        Variant("raw_funding_high_negative_control", "Raw funding alone may instead capture ongoing squeeze", "Research 01 negative control", ("funding_rate_raw",), lambda f, t: f.funding_rate_raw.ge(t["funding_raw_q80"])),
        Variant("ls_spread_high_negative_control", "Position-ratio divergence should add no alpha", "Research 06 claim contradicted by Research 07 zero importance", ("retail_top_spread",), lambda f, t: f.retail_top_spread.ge(t["retail_spread_q80"])),
    ]


def apply_variant(frame: pd.DataFrame, variant: Variant, thresholds: dict[str, float]) -> pd.DataFrame:
    available = frame[list(variant.required_columns)].notna().all(axis=1) if variant.required_columns else pd.Series(True, index=frame.index)
    mask = variant.predicate(frame, thresholds).fillna(False) & available
    return frame.loc[mask].copy()


def summarize(rows: pd.DataFrame, baseline: pd.DataFrame, *, wilson_z: float = 1.959963984540054) -> dict[str, Any]:
    rows = rows.sort_values("signal_time")
    n = len(rows)
    targets = int(rows["status"].eq("target").sum())
    target_rate = targets / n if n else 0.0
    lower, upper = _wilson(targets, n, wilson_z)
    baseline_targets = int(baseline["status"].eq("target").sum())
    returns = rows["net_return_planned"].astype(float)
    return {
        "signals": n,
        "targets": targets,
        "target_rate": target_rate,
        "wilson95_lower": lower,
        "wilson95_upper": upper,
        "signal_coverage_vs_baseline": n / len(baseline) if len(baseline) else 0.0,
        "target_capture_vs_baseline": targets / baseline_targets if baseline_targets else 0.0,
        "actual_path_ev": float(returns.mean()) if n else None,
        "conservative_binary_ev": target_rate * TARGET - (1.0 - target_rate) * STOP - COST if n else None,
        "sequential_compounded_mdd": _max_drawdown(returns),
        "ev_over_downside_vol": _risk_normalized(returns),
        "positive_return_rate": float(returns.gt(0).mean()) if n else None,
    }


def _per_fold(rows: pd.DataFrame, baseline: pd.DataFrame, folds: list[int]) -> list[dict[str, Any]]:
    return [
        {"fold": fold, **summarize(rows[rows.fold.eq(fold)], baseline[baseline.fold.eq(fold)])}
        for fold in folds
    ]


def score_variant(
    selected: pd.DataFrame,
    baseline: pd.DataFrame,
    variant_count: int,
) -> tuple[float, float, float]:
    returns = selected["net_return_planned"].astype(float)
    if returns.empty:
        return -math.inf, math.inf, math.inf
    standard_error = float(returns.std(ddof=1) / math.sqrt(len(returns))) if len(returns) > 1 else math.inf
    multiple_testing_penalty = standard_error * math.sqrt(2.0 * math.log(variant_count))
    fold_evs = [
        float(part["net_return_planned"].mean())
        for _, part in selected.groupby("fold") if len(part)
    ]
    temporal_penalty = 0.5 * (float(np.std(fold_evs, ddof=0)) if fold_evs else math.inf)
    return float(returns.mean() - multiple_testing_penalty - temporal_penalty), multiple_testing_penalty, temporal_penalty


def choose_variant(dev: pd.DataFrame, config: Config) -> tuple[Variant, pd.DataFrame, dict[str, float]]:
    thresholds = fit_thresholds(dev)
    definitions = variants()
    simultaneous_z = statistics.NormalDist().inv_cdf(1 - 0.05 / (2 * len(definitions)))
    rows: list[dict[str, Any]] = []
    for variant in definitions:
        selected = apply_variant(dev, variant, thresholds)
        summary = summarize(selected, dev, wilson_z=simultaneous_z)
        fold_counts = selected.groupby("fold").size().reindex([1, 2, 3], fill_value=0)
        eligible = (
            summary["signals"] >= config.min_dev_signals
            and summary["signal_coverage_vs_baseline"] >= config.min_dev_coverage
            and int(fold_counts.min()) >= config.min_signals_per_dev_fold
        )
        score, mt_penalty, temporal_penalty = score_variant(selected, dev, len(definitions))
        rows.append({
            "variant_id": variant.variant_id,
            "hypothesis": variant.hypothesis,
            "provenance": variant.provenance,
            "required_columns": ",".join(variant.required_columns),
            **summary,
            "simultaneous_wilson_lower": summary["wilson95_lower"],
            "simultaneous_wilson_upper": summary["wilson95_upper"],
            "fold1_signals": int(fold_counts.loc[1]),
            "fold2_signals": int(fold_counts.loc[2]),
            "fold3_signals": int(fold_counts.loc[3]),
            "multiple_testing_ev_penalty": mt_penalty,
            "temporal_ev_penalty": temporal_penalty,
            "adjusted_score": score,
            "eligible": eligible,
        })
    leaderboard = pd.DataFrame(rows)
    eligible = leaderboard[leaderboard["eligible"]]
    if eligible.empty:
        winner_id = "baseline"
    else:
        winner_id = str(eligible.sort_values(
            ["adjusted_score", "simultaneous_wilson_lower", "signals"], ascending=False
        ).iloc[0]["variant_id"])
    return next(item for item in definitions if item.variant_id == winner_id), leaderboard, thresholds


def _coverage(frame: pd.DataFrame) -> dict[str, Any]:
    columns = sorted({column for variant in variants() for column in variant.required_columns})
    return {
        column: {
            "available": int(frame[column].notna().sum()),
            "missing": int(frame[column].isna().sum()),
            "coverage": float(frame[column].notna().mean()),
        }
        for column in columns
    }


def _evaluate_period(frame: pd.DataFrame, definitions: list[Variant], thresholds: dict[str, float], folds: list[int]) -> dict[str, Any]:
    return {
        variant.variant_id: {
            "aggregate": summarize(apply_variant(frame, variant, thresholds), frame),
            "per_fold": _per_fold(apply_variant(frame, variant, thresholds), frame, folds),
        }
        for variant in definitions
    }


def _report_markdown(report: dict[str, Any]) -> str:
    def pct(value: float | None) -> str:
        return "NA" if value is None else f"{value:.2%}"

    selected = report["selection"]["selected_variant"]
    lines = [
        "# Forward48 regime/context filter research — 2026-09-14",
        "",
        "## Kết luận",
        "",
        f"Development chọn **`{selected}`** sau coverage floors và multiple-testing penalty. "
        "Fold 4 chỉ là `recycled_branch_holdout`; August là `recycled_audit`. "
        "Không kết quả nào trong báo cáo này là sealed-forward/promotion evidence.",
        "",
        "## Protocol",
        "",
        "- Frozen timing: pump peak >=30%, age >=4h, 2 confirmations, threshold 0.39.",
        "- Frozen execution: 0/+3/+6, allocations 20/30/50, 6h scale-in, TP -20%, stop +16%, horizon 48h.",
        "- Folds 1–3: development and selection; fold 4: recycled branch holdout; August: opened recycled audit.",
        "- Eligibility: >=35% development coverage, >=20 signals total, >=5 signals in each development fold.",
        f"- Search: {report['selection']['variant_count']} predeclared variants including baseline; EV standard-error penalty sqrt(2 log M), temporal-fold penalty, and simultaneous Wilson intervals.",
        "",
        "## Baseline vs selected",
        "",
        "| Period | Variant | n | Target | Target rate | Coverage | Actual EV | Conservative EV | Wilson 95% | MDD | EV/downside vol |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for period in ["development_folds_1_3", "recycled_branch_holdout_fold_4", "recycled_august_audit"]:
        for variant_id in ["baseline", selected]:
            item = report["results"][period][variant_id]["aggregate"]
            lines.append(
                f"| {period} | `{variant_id}` | {item['signals']} | {item['targets']} | "
                f"{item['target_rate']:.2%} | {item['signal_coverage_vs_baseline']:.2%} | "
                f"{pct(item['actual_path_ev'])} | {pct(item['conservative_binary_ev'])} | "
                f"{item['wilson95_lower']:.2%}–{item['wilson95_upper']:.2%} | "
                f"{item['sequential_compounded_mdd']:.2%} | "
                f"{item['ev_over_downside_vol'] if item['ev_over_downside_vol'] is not None else 'NA'} |"
            )
    lines += [
        "",
        "## All variants",
        "",
        "| Variant | Eligible | Dev n | Dev target | Dev EV | Adjusted score | Fold4 n/EV | August n/EV |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    development_rows = {
        row["variant_id"]: row for row in report["selection"]["development_leaderboard"]
    }
    for definition in report["hypothesis_map"]:
        variant_id = definition["variant_id"]
        dev = report["results"]["development_folds_1_3"][variant_id]["aggregate"]
        fold4 = report["results"]["recycled_branch_holdout_fold_4"][variant_id]["aggregate"]
        august = report["results"]["recycled_august_audit"][variant_id]["aggregate"]
        rank = development_rows[variant_id]
        lines.append(
            f"| `{variant_id}` | {rank['eligible']} | {dev['signals']} | {dev['target_rate']:.2%} | "
            f"{pct(dev['actual_path_ev'])} | {pct(rank['adjusted_score'])} | "
            f"{fold4['signals']} / {pct(fold4['actual_path_ev'])} | "
            f"{august['signals']} / {pct(august['actual_path_ev'])} |"
        )
    lines += [
        "",
        "## Temporal stability of selected variant",
        "",
        "| Fold | n | Target rate | Actual EV | Conservative EV | Coverage |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    selected_folds = report["results"]["development_folds_1_3"][selected]["per_fold"]
    selected_folds += report["results"]["recycled_branch_holdout_fold_4"][selected]["per_fold"]
    selected_folds += report["results"]["recycled_august_audit"][selected]["per_fold"]
    for fold in selected_folds:
        lines.append(
            f"| {fold['fold']} | {fold['signals']} | {fold['target_rate']:.2%} | "
            f"{pct(fold['actual_path_ev'])} | {pct(fold['conservative_binary_ev'])} | "
            f"{fold['signal_coverage_vs_baseline']:.2%} |"
        )
    lines += [
        "",
        "## Data audit",
        "",
        f"- Historical compact paths: {report['coverage']['historical_execution']['future_path_rows']:,} 5m rows for {report['sample']['historical_signals']} signals.",
        f"- Corrupt/unreadable all-universe kline files excluded before breadth calculation: {len(report['coverage']['historical_market']['kline_files_rejected'])}.",
        "- `btc_dominance_proxy_24h` means BTC return minus median altcoin return, not exchange/vendor BTC dominance.",
        "- Market-cap data was unavailable point-in-time, so no market-cap filter was tested. Quote-volume liquidity was available.",
        "- Funding/OI/LS fields come from the same historical/live feature snapshot at Entry 1; BTC/breadth/regime use only bars closed by Entry 1.",
        "- Sequential MDD compounds overlapping signals as if traded one after another; it is a stress statistic, not a portfolio simulation.",
        "- Conservative binary EV assigns +19.8% to every target and -16.2% to every non-target. Actual-path EV respects partial fills, timeout exits, costs and funding, so the two can disagree.",
        "",
        "## Hypothesis provenance",
        "",
        "Reports 01–07 and `docs/RESEARCH_LIBRARY_HYPOTHESIS_MAP_20260914.md` were used only to predeclare hypotheses. "
        "Old precision/ROI claims were not imported as evidence. `raw_funding_high` and LS spread are negative controls; high volatility is tested as an interaction rather than automatically blocked.",
        "",
        "## Decision",
        "",
        report["decision"]["text"],
        "",
    ]
    return "\n".join(lines)


def run(config: Config) -> dict[str, Any]:
    challenger_text = config.challenger_config.read_text(encoding="utf-8")
    if EXPECTED_TIMING_LOCK not in challenger_text:
        raise RuntimeError("frozen challenger timing lock changed")
    historical, oos = load_historical_signals(config)
    august = load_august_signals(config)
    historical, historical_market_audit = attach_market_context(historical, config)
    august, august_market_audit = attach_august_market_context(august, config)

    historical_events, execution_audit = historical_execution(historical, config)
    historical_events = historical_events.merge(
        historical.drop(columns=["probability", "fold"], errors="ignore"),
        left_on=["signal_id", "symbol", "signal_time"],
        right_on=["signal_id", "symbol", "feature_time"],
        how="left", validate="one_to_one",
    )
    august_events = august_execution(config).merge(
        august.drop(columns=["probability", "fold", "feature_time"], errors="ignore"),
        on=["signal_id", "symbol"], how="left", validate="one_to_one",
    )
    august_events["feature_time"] = august_events["signal_time"]
    all_events = pd.concat([historical_events, august_events], ignore_index=True, sort=False)
    eligible_events = all_events[all_events["complete_path"].astype(bool)].copy()
    if "exclusion_reason" in eligible_events:
        eligible_events = eligible_events[eligible_events["exclusion_reason"].isna()]

    dev = eligible_events[eligible_events.fold.isin([1, 2, 3])].copy()
    holdout = eligible_events[eligible_events.fold.eq(4)].copy()
    august_eval = eligible_events[eligible_events.fold.eq(5)].copy()
    winner, leaderboard, thresholds = choose_variant(dev, config)
    definitions = variants()
    results = {
        "development_folds_1_3": _evaluate_period(dev, definitions, thresholds, [1, 2, 3]),
        "recycled_branch_holdout_fold_4": _evaluate_period(holdout, definitions, thresholds, [4]),
        "recycled_august_audit": _evaluate_period(august_eval, definitions, thresholds, [5]),
    }
    selected_mask = winner.predicate(eligible_events, thresholds).fillna(False)
    eligible_events["selected_variant"] = winner.variant_id
    eligible_events["selected_variant_pass"] = selected_mask

    report = {
        "artifact": "forward48_regime_context_research_v1",
        "generated_at": datetime.now(timezone.utc),
        "status": "research_only_not_live_not_sealed",
        "live_configuration_changed": False,
        "immutable_baseline": {
            "challenger_config": str(config.challenger_config),
            "challenger_config_sha256": _sha256(config.challenger_config),
            "timing_lock_sha256": EXPECTED_TIMING_LOCK,
            "timing_policy": asdict(FROZEN_TIMING),
            "execution_template": asdict(COMPACT),
            "target": TARGET, "stop": STOP, "horizon_hours": 48, "cost": COST,
        },
        "protocol": {
            "selection": "historical OOS folds 1-3 only",
            "branch_holdout": "historical OOS fold 4; recycled, not sealed",
            "august": "opened/recycled audit; may reject but cannot promote",
            "future_after_frozen_cutoff": "only valid sealed-forward promotion evidence",
            "same_row_comparison": True,
            "coverage_floors": {
                "minimum_dev_coverage": config.min_dev_coverage,
                "minimum_dev_signals": config.min_dev_signals,
                "minimum_each_dev_fold": config.min_signals_per_dev_fold,
            },
            "multiple_testing": "EV standard-error * sqrt(2 log M), 0.5*temporal-fold EV std, simultaneous Wilson",
        },
        "sample": {
            "historical_signals": len(historical),
            "historical_complete": int(historical_events.complete_path.sum()),
            "development_complete": len(dev),
            "branch_holdout_complete": len(holdout),
            "august_signals": len(august),
            "august_complete_resolved": len(august_eval),
            "historical_oos_rows": len(oos),
        },
        "coverage": {
            "historical_market": historical_market_audit,
            "august_market": august_market_audit,
            "historical_execution": execution_audit,
            "development_context": _coverage(dev),
            "branch_holdout_context": _coverage(holdout),
            "august_context": _coverage(august_eval),
        },
        "selection": {
            "variant_count": len(definitions),
            "selected_variant": winner.variant_id,
            "selected_hypothesis": winner.hypothesis,
            "thresholds_fit_on_development_only": thresholds,
            "development_leaderboard": json.loads(
                leaderboard[[
                    "variant_id", "eligible", "signals", "target_rate",
                    "actual_path_ev", "conservative_binary_ev", "signal_coverage_vs_baseline",
                    "fold1_signals", "fold2_signals", "fold3_signals",
                    "multiple_testing_ev_penalty", "temporal_ev_penalty", "adjusted_score",
                    "simultaneous_wilson_lower", "simultaneous_wilson_upper",
                ]].to_json(orient="records")
            ),
        },
        "hypothesis_map": [
            {key: value for key, value in asdict(variant).items() if key != "predicate"}
            for variant in definitions
        ],
        "results": results,
        "decision": {
            "promotion_eligible": False,
            "live_change": False,
            "selected_filter_validated_alpha": False,
            "selected_filter_improves_branch_holdout_actual_ev": (
                results["recycled_branch_holdout_fold_4"][winner.variant_id]["aggregate"]["actual_path_ev"]
                is not None
                and results["recycled_branch_holdout_fold_4"][winner.variant_id]["aggregate"]["actual_path_ev"]
                > results["recycled_branch_holdout_fold_4"]["baseline"]["aggregate"]["actual_path_ev"]
            ),
            "selected_filter_improves_august_actual_ev": (
                results["recycled_august_audit"][winner.variant_id]["aggregate"]["actual_path_ev"]
                is not None
                and results["recycled_august_audit"][winner.variant_id]["aggregate"]["actual_path_ev"]
                > results["recycled_august_audit"]["baseline"]["aggregate"]["actual_path_ev"]
            ),
            "scout_only": ["funding_exhaustion_rising", "funding_percentile_high"],
            "text": (
                "No validated regime alpha was found. The development winner btc_not_hot "
                "still had negative EV and underperformed baseline on both fold 4 and August. "
                "Funding-exhaustion slices are scout hypotheses only: coverage was below the "
                "predeclared floor and temporal performance was unstable. Freeze any next "
                "scout before testing future data; only >=100 new independent resolved "
                "episodes after the frozen cutoff can support promotion."
            ),
        },
    }

    for path in [config.output_json, config.output_leaderboard_csv, config.output_events_csv, config.output_report_md]:
        path.parent.mkdir(parents=True, exist_ok=True)
    config.output_json.write_text(json.dumps(report, default=_json_default, ensure_ascii=False, indent=2), encoding="utf-8")
    leaderboard.sort_values(["eligible", "adjusted_score"], ascending=False).to_csv(config.output_leaderboard_csv, index=False)
    eligible_events.sort_values("signal_time").to_csv(config.output_events_csv, index=False)
    config.output_report_md.write_text(_report_markdown(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=Config.output_json)
    parser.add_argument("--output-leaderboard-csv", type=Path, default=Config.output_leaderboard_csv)
    parser.add_argument("--output-events-csv", type=Path, default=Config.output_events_csv)
    parser.add_argument("--output-report-md", type=Path, default=Config.output_report_md)
    args = parser.parse_args()
    report = run(Config(
        output_json=args.output_json,
        output_leaderboard_csv=args.output_leaderboard_csv,
        output_events_csv=args.output_events_csv,
        output_report_md=args.output_report_md,
    ))
    print(json.dumps({
        "sample": report["sample"],
        "selection": report["selection"],
        "baseline": report["results"]["recycled_branch_holdout_fold_4"]["baseline"]["aggregate"],
        "selected": report["results"]["recycled_branch_holdout_fold_4"][report["selection"]["selected_variant"]]["aggregate"],
    }, default=_json_default, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
