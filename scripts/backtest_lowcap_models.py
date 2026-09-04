"""Walk-forward backtest of dao_vang models on the low-cap cohort.

The historical lake does not contain point-in-time market-cap snapshots.  The
repository's existing comprehensive backtest therefore uses average daily
quote volume as a market-cap/liquidity proxy.  This script makes that choice
explicit and records it in the output artifact.

The script is intentionally self-contained so that the JSON result can be
reproduced without mutating the production DuckDB database.  It uses the same
5m features, 12h distribution label, LightGBM + isotonic calibration and
LogisticRegression family used by the project backtest code.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score


LOGGER = logging.getLogger("dao_vang.lowcap_backtest")

FEATURE_COLS = [
    "return_5m",
    "volatility_5m",
    "volatility_24h",
    "return_1h",
    "return_4h",
    "return_24h",
    "funding_rate_raw",
    "taker_ratio",
    "vol_surge_24h",
    "oi_change_1h",
    "oi_change_4h",
    "top_acct_ratio",
    "global_ls_ratio",
    "taker_bs_ratio",
]


def _iso(value: Any) -> str:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """Uniform-bin expected calibration error."""

    if len(y_true) == 0:
        return 0.0
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.clip(np.asarray(y_prob, dtype=float), 0.0, 1.0)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for index in range(n_bins):
        if index == n_bins - 1:
            mask = (y_prob >= edges[index]) & (y_prob <= edges[index + 1])
        else:
            mask = (y_prob >= edges[index]) & (y_prob < edges[index + 1])
        if mask.any():
            total += float(mask.mean()) * abs(
                float(y_true[mask].mean()) - float(y_prob[mask].mean())
            )
    return total


def _binary_metrics(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    predicted: np.ndarray,
    threshold: float | None,
    trade_returns: np.ndarray,
    dates: pd.Series,
    *,
    ci_seed: int,
) -> dict[str, Any]:
    """Compute classification, calibration and signal-level trading metrics."""

    actual = np.asarray(y_true, dtype=int)
    probability = np.clip(np.asarray(y_prob, dtype=float), 0.0, 1.0)
    predicted = np.asarray(predicted, dtype=bool)
    returns = np.asarray(trade_returns, dtype=float)
    n = len(actual)
    tp = int(((actual == 1) & predicted).sum())
    fp = int(((actual == 0) & predicted).sum())
    fn = int(((actual == 1) & ~predicted).sum())
    n_pred = int(predicted.sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0

    selected_returns = returns[predicted]
    pnl = float(selected_returns.sum()) if len(selected_returns) else 0.0
    compound = float(np.prod(1.0 + selected_returns) - 1.0) if len(selected_returns) else 0.0
    wins = selected_returns[selected_returns > 0]
    losses = selected_returns[selected_returns < 0]
    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(-losses.sum()) if len(losses) else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (None if not len(wins) else None)

    date_values = pd.to_datetime(dates, utc=True).dt.floor("D")
    daily = pd.Series(selected_returns, index=date_values[predicted]).groupby(level=0).sum()
    if len(daily):
        full_days = pd.date_range(date_values.min(), date_values.max(), freq="D", tz="UTC")
        daily = daily.reindex(full_days, fill_value=0.0)
    daily_mean = float(daily.mean()) if len(daily) else 0.0
    daily_std = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    sharpe = float(math.sqrt(365.0) * daily_mean / daily_std) if daily_std > 0 else None
    equity = np.cumsum(daily.to_numpy(dtype=float)) if len(daily) else np.array([], dtype=float)
    if len(equity):
        drawdown = equity - np.maximum.accumulate(np.concatenate(([0.0], equity[:-1])))
        max_drawdown = float(drawdown.min())
    else:
        max_drawdown = 0.0

    # Bootstrap the mean of fold-level metrics in the caller.  This placeholder
    # keeps the schema stable for per-fold and aggregate rows.
    del ci_seed
    result: dict[str, Any] = {
        "n_rows": n,
        "n_positive": int(actual.sum()),
        "prevalence": float(actual.mean()) if n else 0.0,
        "n_predicted_positive": n_pred,
        "signal_rate": n_pred / n if n else 0.0,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "pr_auc": float(average_precision_score(actual, probability))
        if n and np.unique(actual).size > 1
        else 0.0,
        "brier_score": float(np.mean((probability - actual) ** 2)) if n else 0.0,
        "ece": _ece(actual, probability),
        "threshold": threshold,
        "pnl_sum": pnl,
        "compound_return": compound,
        "avg_trade_return": float(selected_returns.mean()) if len(selected_returns) else 0.0,
        "trade_win_rate": float((selected_returns > 0).mean()) if len(selected_returns) else 0.0,
        "profit_factor": profit_factor,
        "sharpe_daily_annualized": sharpe,
        "max_drawdown_daily": max_drawdown,
        "n_trade_days": int(len(daily)),
    }
    return result


def _bootstrap_mean(values: Iterable[float | None], seed: int, n_bootstrap: int = 2000) -> dict[str, Any]:
    arr = np.asarray([float(value) for value in values if value is not None and math.isfinite(float(value))], dtype=float)
    if len(arr) == 0:
        return {"mean": None, "ci_lower": None, "ci_upper": None, "n": 0}
    if len(arr) == 1:
        value = float(arr[0])
        return {"mean": value, "ci_lower": value, "ci_upper": value, "n": 1}
    rng = np.random.default_rng(seed)
    samples = rng.choice(arr, size=(n_bootstrap, len(arr)), replace=True).mean(axis=1)
    return {
        "mean": float(arr.mean()),
        "ci_lower": float(np.percentile(samples, 2.5)),
        "ci_upper": float(np.percentile(samples, 97.5)),
        "n": int(len(arr)),
    }


def _select_universe(
    conn: duckdb.DuckDBPyConnection,
    window_start: datetime,
    as_of: datetime,
    min_volume: float,
    max_volume: float,
    min_active_days: int,
) -> pd.DataFrame:
    query = """
        WITH daily AS (
            SELECT
                symbol,
                CAST(open_time AS DATE) AS trading_day,
                SUM(quote_volume) AS day_quote_volume
            FROM klines_5m
            WHERE close_time >= ? AND close_time <= ?
            GROUP BY symbol, CAST(open_time AS DATE)
        )
        SELECT
            symbol,
            AVG(day_quote_volume) AS avg_daily_quote_volume,
            COUNT(*) AS active_days,
            SUM(day_quote_volume) AS total_quote_volume
        FROM daily
        GROUP BY symbol
        HAVING COUNT(*) >= ?
           AND AVG(day_quote_volume) >= ?
           AND AVG(day_quote_volume) < ?
        ORDER BY avg_daily_quote_volume DESC, symbol
    """
    return conn.execute(
        query, [window_start, as_of, min_active_days, min_volume, max_volume]
    ).fetchdf()


def _load_feature_rows(
    conn: duckdb.DuckDBPyConnection,
    symbols: list[str],
    history_start: datetime,
    window_start: datetime,
    as_of: datetime,
    evaluation_end: datetime,
    horizon_bars: int,
    horizon_hours: int,
    target_drawdown: float,
    max_adverse_excursion: float,
    candidate_return: float,
    candidate_funding: float,
) -> pd.DataFrame:
    """Build point-in-time features and fully resolved labels in DuckDB."""

    conn.register("_lowcap_symbols", pd.DataFrame({"symbol": symbols}))
    interval = f"INTERVAL '{horizon_hours} hours'"
    horizon_plus = f"INTERVAL '{horizon_hours * 60 + 5} minutes'"
    query = f"""
        WITH base AS (
            SELECT
                k.symbol,
                k.close_time AS feature_time,
                k.open,
                k.high,
                k.low,
                k.close,
                k.volume,
                k.quote_volume,
                k.taker_buy_volume,
                (k.close - k.open) / NULLIF(k.open, 0) AS return_5m,
                (k.high - k.low) / NULLIF(k.open, 0) AS volatility_5m,
                m.open_interest AS oi_contracts,
                m.top_trader_account_ratio AS top_acct_ratio,
                m.global_account_ratio AS global_ls_ratio,
                m.taker_buy_sell_ratio AS taker_bs_ratio,
                f.funding_rate
            FROM klines_5m k
            INNER JOIN _lowcap_symbols u ON u.symbol = k.symbol
            LEFT JOIN metrics_5m m
              ON m.symbol = k.symbol
             AND time_bucket(INTERVAL '5 minutes', m.timestamp)
                 = time_bucket(INTERVAL '5 minutes', k.close_time)
            ASOF LEFT JOIN funding_history f
              ON f.symbol = k.symbol
             AND k.close_time >= f.funding_time
            WHERE k.close_time >= ? AND k.close_time <= ?
        ),
        feature_windows AS (
            SELECT
                base.*,
                STDDEV_SAMP(return_5m) OVER w24 AS volatility_24h,
                close / NULLIF(LAG(close, 12) OVER w, 0) - 1.0 AS return_1h,
                close / NULLIF(LAG(close, 48) OVER w, 0) - 1.0 AS return_4h,
                close / NULLIF(LAG(close, 288) OVER w, 0) - 1.0 AS return_24h,
                volume / NULLIF(AVG(volume) OVER w24, 0) AS vol_surge_24h,
                taker_buy_volume / NULLIF(volume, 0) AS taker_ratio,
                oi_contracts / NULLIF(LAG(oi_contracts, 12) OVER w, 0) - 1.0 AS oi_change_1h,
                oi_contracts / NULLIF(LAG(oi_contracts, 48) OVER w, 0) - 1.0 AS oi_change_4h,
                MIN(low) OVER wfuture AS future_min_low,
                MAX(high) OVER wfuture AS future_max_high,
                COUNT(*) OVER wfuture AS future_count,
                LEAD(close, {horizon_bars}) OVER w AS close_at_horizon,
                LEAD(feature_time, {horizon_bars}) OVER w AS time_at_horizon
            FROM base
            WINDOW
                w AS (PARTITION BY symbol ORDER BY feature_time),
                w24 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 287 PRECEDING AND CURRENT ROW),
                wfuture AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 1 FOLLOWING AND {horizon_bars} FOLLOWING)
        ),
        labeled AS (
            SELECT
                *,
                CASE
                    WHEN future_count = {horizon_bars}
                     AND time_at_horizon <= feature_time + {horizon_plus}
                    THEN CASE
                        WHEN future_min_low <= close * (1.0 - {target_drawdown})
                         AND future_max_high <= close * (1.0 + {max_adverse_excursion})
                        THEN 1 ELSE 0
                    END
                    ELSE NULL
                END AS label_value
            FROM feature_windows
        )
        SELECT
            symbol,
            feature_time,
            close,
            return_5m,
            volatility_5m,
            volatility_24h,
            return_1h,
            return_4h,
            return_24h,
            funding_rate AS funding_rate_raw,
            taker_ratio,
            vol_surge_24h,
            oi_change_1h,
            oi_change_4h,
            top_acct_ratio,
            global_ls_ratio,
            taker_bs_ratio,
            future_min_low,
            future_max_high,
            close_at_horizon,
            time_at_horizon,
            label_value
        FROM labeled
        WHERE feature_time >= ?
          AND feature_time <= ?
          AND future_count = {horizon_bars}
          AND time_at_horizon <= feature_time + {horizon_plus}
          AND (
                return_24h > {candidate_return}
                OR funding_rate > {candidate_funding}
          )
          AND return_1h IS NOT NULL
          AND return_4h IS NOT NULL
          AND return_24h IS NOT NULL
          AND label_value IS NOT NULL
        ORDER BY feature_time, symbol
    """
    try:
        return conn.execute(query, [history_start, as_of, window_start, evaluation_end]).fetchdf()
    finally:
        try:
            conn.unregister("_lowcap_symbols")
        except Exception:
            pass


def _fit_probabilities(
    train: pd.DataFrame,
    test: pd.DataFrame,
    *,
    seed: int,
    top_quantile: float,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Fit LR and LGBM on fit-only rows; calibrate/threshold on train tail."""

    n_fit = max(1, int(len(train) * 0.8))
    fit = train.iloc[:n_fit]
    calibration = train.iloc[n_fit:]
    y_fit = fit["label_value"].astype(int).to_numpy()
    y_cal = calibration["label_value"].astype(int).to_numpy()
    y_test = test["label_value"].astype(int).to_numpy()
    if len(np.unique(y_fit)) < 2:
        raise ValueError("training fit split has only one class")

    imputer = SimpleImputer(strategy="median", add_indicator=True)
    x_fit = imputer.fit_transform(fit[FEATURE_COLS])
    x_cal = imputer.transform(calibration[FEATURE_COLS]) if len(calibration) else np.empty((0, x_fit.shape[1]))
    x_test = imputer.transform(test[FEATURE_COLS])

    lr = LogisticRegression(max_iter=1000, random_state=seed)
    lr.fit(x_fit, y_fit)
    lr_cal = lr.predict_proba(x_cal)[:, 1] if len(x_cal) else np.array([], dtype=float)
    lr_test = lr.predict_proba(x_test)[:, 1]
    lr_threshold = float(np.quantile(lr_cal, top_quantile)) if len(lr_cal) else 0.5

    lgb_model = lgb.LGBMClassifier(
        random_state=seed,
        n_estimators=200,
        learning_rate=0.05,
        max_depth=5,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
        n_jobs=1,
    )
    lgb_model.fit(x_fit, y_fit)
    lgb_cal_raw = lgb_model.predict_proba(x_cal)[:, 1] if len(x_cal) else np.array([], dtype=float)
    lgb_test_raw = lgb_model.predict_proba(x_test)[:, 1]
    if len(lgb_cal_raw) >= 50 and len(np.unique(y_cal)) >= 2:
        calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        calibrator.fit(lgb_cal_raw, y_cal)
        lgb_cal = np.asarray(calibrator.predict(lgb_cal_raw), dtype=float)
        lgb_test = np.asarray(calibrator.predict(lgb_test_raw), dtype=float)
        calibration_method = "isotonic"
    else:
        lgb_cal = lgb_cal_raw
        lgb_test = lgb_test_raw
        calibration_method = "none"
    lgb_threshold = float(np.quantile(lgb_cal, top_quantile)) if len(lgb_cal) else 0.5

    def top_k(values: np.ndarray) -> np.ndarray:
        """Select a fixed score-ranked budget, with deterministic tie breaks."""

        count = max(1, int(round(len(values) * (1.0 - top_quantile))))
        count = min(count, len(values))
        order = np.argsort(-np.asarray(values, dtype=float), kind="mergesort")
        mask = np.zeros(len(values), dtype=bool)
        mask[order[:count]] = True
        return mask

    # No-skill baseline: a train-only prevalence probability plus a random
    # top-2%-style signal policy.  The random policy has a fixed budget and
    # does not inspect test labels or model scores.
    train_prevalence = float(train["label_value"].mean())
    rng = np.random.default_rng(seed + 10_000)
    n_baseline = max(1, int(round(len(test) * (1.0 - top_quantile))))
    n_baseline = min(n_baseline, len(test))
    baseline_signal = np.zeros(len(test), dtype=bool)
    if n_baseline:
        baseline_signal[rng.choice(len(test), size=n_baseline, replace=False)] = True

    probs = {
        "LogisticRegression": lr_test,
        "LightGBM": lgb_test,
        "Baseline": np.full(len(test), train_prevalence, dtype=float),
    }
    signals = {
        # The threshold is learned from calibration; the final signal policy
        # is score-ranked top-k so LightGBM's isotonic ties cannot silently
        # create a much larger trade count than LogisticRegression.
        "LogisticRegression": top_k(lr_test),
        "LightGBM": top_k(lgb_test),
        "Baseline": baseline_signal,
    }
    metadata = {
        "thresholds": {
            "LogisticRegression": lr_threshold,
            "LightGBM": lgb_threshold,
            "Baseline": None,
        },
        "baseline_probability": train_prevalence,
        "baseline_signal_count": int(n_baseline),
        "lightgbm_calibration_method": calibration_method,
        "fit_rows": int(len(fit)),
        "calibration_rows": int(len(calibration)),
        "fit_positive_rows": int(y_fit.sum()),
        "calibration_positive_rows": int(y_cal.sum()),
        "test_positive_rows": int(y_test.sum()),
    }
    return {**probs, **{f"{name}__signal": value for name, value in signals.items()}}, metadata


def _fold_boundaries(
    window_start: datetime,
    evaluation_end: datetime,
    n_folds: int,
    warmup_days: int,
) -> list[dict[str, datetime]]:
    """Create equal-duration chronological test windows through the last row."""

    boundaries: list[dict[str, datetime]] = []
    first_test = window_start + timedelta(days=warmup_days)
    step = (evaluation_end - first_test) / n_folds
    for index in range(n_folds):
        test_start = first_test + step * index
        test_end = min(first_test + step * (index + 1), evaluation_end)
        if test_start >= test_end:
            break
        boundaries.append({"test_start": test_start, "test_end": test_end})
    return boundaries


def _trade_returns(
    frame: pd.DataFrame,
    *,
    target_drawdown: float,
    max_adverse_excursion: float,
    target_profit: float,
    round_trip_cost_bps: float,
) -> np.ndarray:
    """Approximate short-trade return with TP/SL and horizon close fallback."""

    entry = frame["close"].to_numpy(dtype=float)
    future_low = frame["future_min_low"].to_numpy(dtype=float)
    future_high = frame["future_max_high"].to_numpy(dtype=float)
    close_horizon = frame["close_at_horizon"].to_numpy(dtype=float)
    labels = frame["label_value"].to_numpy(dtype=int)
    stop_loss = -max_adverse_excursion
    gross = np.where(
        labels == 1,
        target_profit,
        np.where(
            future_high >= entry * (1.0 + max_adverse_excursion),
            stop_loss,
            entry / np.maximum(close_horizon, 1e-12) - 1.0,
        ),
    )
    # A label=1 already guarantees the target was reached before the adverse
    # excursion according to the project definition.  Keep the named argument
    # in the calculation contract to make the assumptions explicit.
    del target_drawdown, future_low
    cost = round_trip_cost_bps / 10_000.0
    return np.asarray(gross - cost, dtype=float)


def _aggregate_model_metrics(
    oos: pd.DataFrame,
    folds: list[dict[str, Any]],
    model: str,
    *,
    seed: int,
) -> dict[str, Any]:
    prob_col = f"{model}__prob"
    signal_col = f"{model}__signal"
    y = oos["label_value"].to_numpy(dtype=int)
    p = oos[prob_col].to_numpy(dtype=float)
    signal = oos[signal_col].to_numpy(dtype=bool)
    metrics = _binary_metrics(
        y,
        p,
        signal,
        None,
        oos["trade_return"].to_numpy(dtype=float),
        oos["feature_time"],
        ci_seed=seed,
    )
    per_fold = [fold["models"][model] for fold in folds]
    stable_model_seed = sum(ord(char) for char in model)
    for key in ["precision", "recall", "brier_score", "ece", "pnl_sum", "sharpe_daily_annualized"]:
        metrics[f"{key}_fold_bootstrap_95"] = _bootstrap_mean(
            [item.get(key) for item in per_fold],
            seed + stable_model_seed + sum(ord(char) for char in key),
        )
    metrics["threshold_summary"] = {
        "min": float(oos[f"{model}__threshold"].min()) if model != "Baseline" else None,
        "median": float(oos[f"{model}__threshold"].median()) if model != "Baseline" else None,
        "max": float(oos[f"{model}__threshold"].max()) if model != "Baseline" else None,
    }
    metrics["n_folds"] = len(per_fold)
    return metrics


def _round_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _round_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_round_for_json(item) for item in value]
    if isinstance(value, float):
        return round(value, 8) if math.isfinite(value) else None
    return value


def run_backtest(
    *,
    db_path: Path,
    output_path: Path,
    lookback_days: int = 365,
    min_volume: float = 10_000_000.0,
    max_volume: float = 500_000_000.0,
    min_active_days: int = 180,
    n_folds: int = 10,
    test_days: int = 30,
    embargo_hours: int = 48,
    horizon_hours: int = 12,
    top_quantile: float = 0.98,
    seed: int = 42,
    round_trip_cost_bps: float = 20.0,
) -> dict[str, Any]:
    start_wall = datetime.now(timezone.utc)
    horizon_bars = horizon_hours * 12
    target_drawdown = 0.08
    max_adverse_excursion = 0.04
    target_profit = 0.08
    candidate_return = 0.08
    candidate_funding = 0.0002

    conn = duckdb.connect(str(db_path), read_only=True)
    try:
        as_of = conn.execute("SELECT MAX(close_time) FROM klines_5m").fetchone()[0]
        if not isinstance(as_of, datetime):
            as_of = pd.Timestamp(as_of).to_pydatetime()
        as_of = as_of.replace(tzinfo=as_of.tzinfo or timezone.utc)
        window_start = as_of - timedelta(days=lookback_days)
        evaluation_end = as_of - timedelta(hours=horizon_hours)
        history_start = window_start - timedelta(days=2)

        LOGGER.info("Selecting low-cap universe from %s to %s", window_start, as_of)
        universe = _select_universe(
            conn,
            window_start,
            as_of,
            min_volume,
            max_volume,
            min_active_days,
        )
        if universe.empty:
            raise RuntimeError("No symbols match the low-cap volume filter")
        symbols = universe["symbol"].astype(str).tolist()
        LOGGER.info("Selected %d symbols", len(symbols))

        LOGGER.info("Building point-in-time features and labels")
        frame = _load_feature_rows(
            conn,
            symbols,
            history_start,
            window_start,
            as_of,
            evaluation_end,
            horizon_bars,
            horizon_hours,
            target_drawdown,
            max_adverse_excursion,
            candidate_return,
            candidate_funding,
        )
    finally:
        conn.close()

    if frame.empty:
        raise RuntimeError("Feature/label query returned no candidate rows")
    frame[FEATURE_COLS] = frame[FEATURE_COLS].replace([np.inf, -np.inf], np.nan)
    frame["label_value"] = frame["label_value"].astype(int)
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame = frame.sort_values(["feature_time", "symbol"]).reset_index(drop=True)
    frame["trade_return"] = _trade_returns(
        frame,
        target_drawdown=target_drawdown,
        max_adverse_excursion=max_adverse_excursion,
        target_profit=target_profit,
        round_trip_cost_bps=round_trip_cost_bps,
    )

    boundaries = _fold_boundaries(
        pd.Timestamp(window_start), pd.Timestamp(evaluation_end), n_folds, test_days * 2
    )
    folds: list[dict[str, Any]] = []
    oos_parts: list[pd.DataFrame] = []
    embargo = timedelta(hours=embargo_hours)

    for fold_index, boundary in enumerate(boundaries, start=1):
        test_start = boundary["test_start"]
        test_end = boundary["test_end"]
        train_end = test_start - embargo
        train = frame[(frame["feature_time"] >= window_start) & (frame["feature_time"] < train_end)].copy()
        test = frame[(frame["feature_time"] >= test_start) & (frame["feature_time"] < test_end)].copy()
        if len(train) < 100 or len(test) == 0 or train["label_value"].nunique() < 2:
            LOGGER.warning("Skipping fold %d: train=%d test=%d classes=%s", fold_index, len(train), len(test), train["label_value"].nunique())
            continue
        LOGGER.info("Fold %d: train=%d test=%d", fold_index, len(train), len(test))
        predictions, metadata = _fit_probabilities(
            train,
            test,
            seed=seed,
            top_quantile=top_quantile,
        )
        oos_fold = test[["symbol", "feature_time", "label_value", "trade_return"]].copy()
        for model in ("LogisticRegression", "LightGBM", "Baseline"):
            oos_fold[f"{model}__prob"] = predictions[model]
            oos_fold[f"{model}__signal"] = predictions[f"{model}__signal"]
            oos_fold[f"{model}__threshold"] = metadata["thresholds"][model]
        fold_models: dict[str, Any] = {}
        for model in ("LogisticRegression", "LightGBM", "Baseline"):
            fold_models[model] = _binary_metrics(
                test["label_value"].to_numpy(dtype=int),
                predictions[model],
                predictions[f"{model}__signal"],
                metadata["thresholds"][model],
                test["trade_return"].to_numpy(dtype=float),
                test["feature_time"],
                ci_seed=seed + fold_index,
            )
        folds.append({
            "fold": fold_index,
            "boundary_test_start": _iso(test_start),
            "boundary_test_end": _iso(test_end),
            "train_start": _iso(train["feature_time"].min()),
            "train_end": _iso(train["feature_time"].max()),
            "test_start": _iso(test["feature_time"].min()),
            "test_end": _iso(test["feature_time"].max()),
            "train_rows": int(len(train)),
            "train_positive_rows": int(train["label_value"].sum()),
            "test_rows": int(len(test)),
            "test_positive_rows": int(test["label_value"].sum()),
            "embargo_hours": embargo_hours,
            "model_metadata": metadata,
            "models": fold_models,
        })
        oos_parts.append(oos_fold)

    if not oos_parts:
        raise RuntimeError("No valid walk-forward folds were produced")
    oos = pd.concat(oos_parts, ignore_index=True)
    models = {name: _aggregate_model_metrics(oos, folds, name, seed=seed) for name in ("LogisticRegression", "LightGBM", "Baseline")}

    # Add rule-based baselines on the same OOS rows for context.  They are not
    # used in the primary model ranking because the requested baseline is B0.
    rule_baselines: dict[str, Any] = {}
    for name in ("PriceReturn_gt_8pct", "Funding_gt_0.02pct"):
        # The index alignment above is by timestamp only; use the exact OOS
        # keys below to avoid cross-symbol collisions.
        key = oos[["symbol", "feature_time"]].merge(
            frame[["symbol", "feature_time", "return_24h", "funding_rate_raw"]],
            on=["symbol", "feature_time"],
            how="left",
            validate="one_to_one",
        )
        if name.startswith("Price"):
            signal = key["return_24h"].to_numpy(dtype=float) > candidate_return
        else:
            signal = key["funding_rate_raw"].fillna(-np.inf).to_numpy(dtype=float) > candidate_funding
        rule_baselines[name] = _binary_metrics(
            oos["label_value"].to_numpy(dtype=int),
            oos["Baseline__prob"].to_numpy(dtype=float),
            signal,
            None,
            oos["trade_return"].to_numpy(dtype=float),
            oos["feature_time"],
            ci_seed=seed,
        )

    # Rank by the requested KPIs.  Precision/calibration are the primary
    # detector objectives; PnL/Sharpe are secondary because this is a signal-
    # level simulation with overlapping 5m observations.
    primary_metrics = {
        "precision": ("precision", True),
        "recall": ("recall", True),
        "ece": ("ece", False),
        "brier_score": ("brier_score", False),
        "pnl_sum": ("pnl_sum", True),
        "sharpe_daily_annualized": ("sharpe_daily_annualized", True),
    }
    best_by_metric: dict[str, str | None] = {}
    for label, (key, higher_is_better) in primary_metrics.items():
        usable = {name: value.get(key) for name, value in models.items() if value.get(key) is not None}
        best_by_metric[label] = (max if higher_is_better else min)(usable, key=usable.get) if usable else None
    # Equal-weight rank score across available metrics.  This prevents a
    # single noisy PnL statistic from hiding materially worse calibration.
    rank_scores: dict[str, float] = {name: 0.0 for name in models}
    for key, (_, higher_is_better) in primary_metrics.items():
        usable = [(name, value[key]) for name, value in models.items() if value.get(key) is not None]
        ordered = sorted(usable, key=lambda item: item[1], reverse=higher_is_better)
        for rank, (name, _) in enumerate(ordered, start=1):
            rank_scores[name] += rank
    recommended = min(rank_scores, key=rank_scores.get)

    feature_nulls = {
        col: int(frame[col].isna().sum()) for col in FEATURE_COLS if int(frame[col].isna().sum()) > 0
    }
    summary = {
        "recommended_model_by_equal_metric_rank": recommended,
        "rank_score_lower_is_better": rank_scores,
        "best_by_metric": best_by_metric,
        "interpretation": "Primary detector choice prioritizes precision/calibration; PnL/Sharpe are secondary signal-level diagnostics.",
    }
    report: dict[str, Any] = {
        "artifact": "codex_backtest_lowcap",
        "generated_at": start_wall.isoformat(),
        "source": {
            "database": str(db_path),
            "table": "klines_5m + metrics_5m + funding_history",
            "as_of_last_kline": _iso(as_of),
        },
        "window": {
            "lookback_days": lookback_days,
            "observation_start": _iso(window_start),
            "observation_end": _iso(as_of),
            "signal_evaluation_end": _iso(evaluation_end),
            "history_start_for_features": _iso(history_start),
            "note": "The final 12h of the observation window is reserved for label resolution.",
        },
        "universe": {
            "definition": "Average daily Binance Futures quote volume proxy; no point-in-time market-cap snapshot is present in the source lake.",
            "market_cap_available": False,
            "selection_is_fixed_over_full_window": True,
            "selection_lookahead_caveat": "The cohort is selected ex-post over the 365-day window for research comparability; this is not a point-in-time universe simulation.",
            "min_avg_daily_quote_volume_usd": min_volume,
            "max_avg_daily_quote_volume_usd_exclusive": max_volume,
            "min_active_days": min_active_days,
            "n_symbols": len(symbols),
            "symbols": symbols,
            "symbol_stats": [
                {
                    "symbol": str(row.symbol),
                    "avg_daily_quote_volume_usd": float(row.avg_daily_quote_volume),
                    "active_days": int(row.active_days),
                    "total_quote_volume_usd": float(row.total_quote_volume),
                }
                for row in universe.itertuples(index=False)
            ],
        },
        "label": {
            "version": "distribution_short_v1-compatible",
            "horizon_hours": horizon_hours,
            "target_drawdown": target_drawdown,
            "max_adverse_excursion": max_adverse_excursion,
            "definition": "label=1 when future low reaches -8% before/without future high exceeding +4% within 12h; complete 5m horizon required.",
            "candidate_filter": f"return_24h > {candidate_return} OR funding_rate > {candidate_funding}",
        },
        "features": {
            "timeframe": "5m",
            "columns": FEATURE_COLS,
            "count": len(FEATURE_COLS),
            "imputer": "median + missing indicators fit on fit split only",
            "null_counts_in_evaluated_rows": feature_nulls,
        },
        "validation": {
            "method": "chronological walk-forward",
            "n_requested_folds": n_folds,
            "n_valid_folds": len(folds),
            "warmup_days": test_days * 2,
            "target_test_days": test_days,
            "actual_test_duration_days": (evaluation_end - (window_start + timedelta(days=test_days * 2))).total_seconds() / 86400 / n_folds,
            "training": "expanding from observation_start",
            "calibration": "last 20% of each train window; LightGBM isotonic when both classes and >=50 rows",
            "embargo_hours": embargo_hours,
            "threshold_policy": f"calibration quantile at {(top_quantile * 100):.2f}th percentile; test signals use fixed top {(1.0 - top_quantile) * 100:.2f}% score-ranked budget with stable tie breaks",
            "seed": seed,
            "leakage_checks": {
                "feature_columns_exclude_label_and_future_fields": True,
                "imputer_fit_on_train_fit_split_only": True,
                "threshold_fit_on_calibration_split_only": True,
                "test_labels_used_for_training_or_threshold": False,
                "train_test_embargo_hours": embargo_hours,
                "universe_point_in_time": False,
            },
        },
        "data_quality": {
            "evaluated_rows": int(len(frame)),
            "evaluated_symbols": int(frame["symbol"].nunique()),
            "positive_rows": int(frame["label_value"].sum()),
            "negative_rows": int((frame["label_value"] == 0).sum()),
            "prevalence": float(frame["label_value"].mean()),
            "duplicate_symbol_time_rows": int(frame.duplicated(["symbol", "feature_time"]).sum()),
            "nonfinite_feature_values_after_cleaning": int(np.isinf(frame[FEATURE_COLS].to_numpy(dtype=float)).sum()),
            "label_min_time": _iso(frame["feature_time"].min()),
            "label_max_time": _iso(frame["feature_time"].max()),
            "funding_non_null_rate": float(frame["funding_rate_raw"].notna().mean()),
        },
        "trading_simulation": {
            "direction": "short",
            "entry": "close of feature bar",
            "take_profit_gross": target_profit,
            "stop_loss_gross": -max_adverse_excursion,
            "no_hit_exit": "short return from entry close to close_at_horizon",
            "round_trip_cost_bps": round_trip_cost_bps,
            "position_sizing": "one equal-notional trade per predicted signal",
            "overlap_policy": "overlapping 5m signals are allowed; PnL/Sharpe are signal-level diagnostics, not a capacity-aware portfolio backtest",
        },
        "folds": folds,
        "models": models,
        "additional_rule_baselines": rule_baselines,
        "conclusion": summary,
        "runtime_seconds": (datetime.now(timezone.utc) - start_wall).total_seconds(),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_round_for_json(report), indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(r"D:\Quant-trading\data_lake\quant_master.duckdb"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/codex_backtest_lowcap.json"))
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--min-volume", type=float, default=10_000_000.0)
    parser.add_argument("--max-volume", type=float, default=500_000_000.0)
    parser.add_argument("--min-active-days", type=int, default=180)
    parser.add_argument("--n-folds", type=int, default=10)
    parser.add_argument("--test-days", type=int, default=30)
    parser.add_argument("--embargo-hours", type=int, default=48)
    parser.add_argument("--horizon-hours", type=int, default=12)
    parser.add_argument("--top-quantile", type=float, default=0.98)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--round-trip-cost-bps", type=float, default=20.0)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    run_backtest(
        db_path=args.db,
        output_path=args.output,
        lookback_days=args.lookback_days,
        min_volume=args.min_volume,
        max_volume=args.max_volume,
        min_active_days=args.min_active_days,
        n_folds=args.n_folds,
        test_days=args.test_days,
        embargo_hours=args.embargo_hours,
        horizon_hours=args.horizon_hours,
        top_quantile=args.top_quantile,
        seed=args.seed,
        round_trip_cost_bps=args.round_trip_cost_bps,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
