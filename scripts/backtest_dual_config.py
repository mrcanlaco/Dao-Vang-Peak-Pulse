"""Walk-forward backtest of dao_vang models under two TP:StopLoss configurations:
Config 1: TP:SL = (8% : 4%)
Config 2: TP:SL = (20% : 10%)

Compares Champion (LogisticRegression) vs Challenger (LightGBM + Isotonic Calibration)
across 10 chronological walk-forward folds on 365 days of low-cap coins from quant_master.duckdb.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
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

LOGGER = logging.getLogger("dao_vang.dual_backtest")

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
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    return str(value)


def _json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        val = float(value)
        return val if math.isfinite(val) else None
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [_json_value(item) for item in value.tolist()]
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _round_for_json(data: Any, decimals: int = 6) -> Any:
    if isinstance(data, dict):
        return {k: _round_for_json(v, decimals) for k, v in data.items()}
    if isinstance(data, list):
        return [_round_for_json(v, decimals) for v in data]
    if isinstance(data, float):
        if not math.isfinite(data):
            return None
        return round(data, decimals)
    return _json_value(data)


def _ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    if len(y_true) == 0:
        return 0.0
    y_true = np.asarray(y_true, dtype=float)
    y_prob = np.clip(np.asarray(y_prob, dtype=float), 0.0, 1.0)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    total = 0.0
    for idx in range(n_bins):
        if idx == n_bins - 1:
            mask = (y_prob >= edges[idx]) & (y_prob <= edges[idx + 1])
        else:
            mask = (y_prob >= edges[idx]) & (y_prob < edges[idx + 1])
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
) -> dict[str, Any]:
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
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if len(wins) else None)

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

    return {
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


def _bootstrap_mean(values: Iterable[float | None], seed: int, n_bootstrap: int = 2000) -> dict[str, Any]:
    arr = np.asarray([float(v) for v in values if v is not None and math.isfinite(float(v))], dtype=float)
    if len(arr) == 0:
        return {"mean": None, "ci_lower": None, "ci_upper": None, "n": 0}
    if len(arr) == 1:
        val = float(arr[0])
        return {"mean": val, "ci_lower": val, "ci_upper": val, "n": 1}
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
        HAVING AVG(day_quote_volume) >= ?
           AND AVG(day_quote_volume) < ?
           AND COUNT(*) >= ?
        ORDER BY avg_daily_quote_volume DESC
    """
    return conn.execute(
        query,
        [window_start, as_of, min_volume, max_volume, min_active_days],
    ).fetchdf()


def _load_data_chunked(
    conn: duckdb.DuckDBPyConnection,
    symbols: list[str],
    history_start: datetime,
    window_start: datetime,
    as_of: datetime,
    evaluation_end: datetime,
    horizon_bars: int,
    horizon_hours: int,
    candidate_return: float = 0.08,
    candidate_funding: float = 0.0002,
    chunk_size: int = 25,
) -> pd.DataFrame:
    chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]
    horizon_plus = f"INTERVAL '{horizon_hours * 60 + 5} minutes'"
    dfs = []
    for idx, chunk in enumerate(chunks, 1):
        t_c = time.time()
        conn.register("_target_symbols", pd.DataFrame({"symbol": chunk}))
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
                INNER JOIN _target_symbols u ON u.symbol = k.symbol
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
                COALESCE(funding_rate, 0.0) AS funding_rate_raw,
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
                CASE
                    WHEN future_count = {horizon_bars} AND time_at_horizon <= feature_time + {horizon_plus}
                    THEN CASE
                        WHEN future_min_low <= close * (1.0 - 0.08) AND future_max_high <= close * (1.0 + 0.04)
                        THEN 1 ELSE 0
                    END
                    ELSE NULL
                END AS label_8_4,
                CASE
                    WHEN future_count = {horizon_bars} AND time_at_horizon <= feature_time + {horizon_plus}
                    THEN CASE
                        WHEN future_min_low <= close * (1.0 - 0.20) AND future_max_high <= close * (1.0 + 0.10)
                        THEN 1 ELSE 0
                    END
                    ELSE NULL
                END AS label_20_10
            FROM feature_windows
            WHERE feature_time >= ?
              AND feature_time <= ?
              AND (return_24h > {candidate_return} OR funding_rate > {candidate_funding})
              AND future_count = {horizon_bars}
              AND return_5m IS NOT NULL
              AND volatility_5m IS NOT NULL
              AND return_1h IS NOT NULL
              AND return_4h IS NOT NULL
              AND return_24h IS NOT NULL
            ORDER BY feature_time, symbol
        """
        try:
            df_chunk = conn.execute(query, [history_start, as_of, window_start, evaluation_end]).fetchdf()
        finally:
            try:
                conn.unregister("_target_symbols")
            except Exception:
                pass
        dfs.append(df_chunk)
        LOGGER.info("Extracted chunk %d/%d (%d coins): %d rows in %.2fs", idx, len(chunks), len(chunk), len(df_chunk), time.time() - t_c)
    return pd.concat(dfs, ignore_index=True)

def _trade_returns(
    frame: pd.DataFrame,
    label_col: str,
    target_profit: float,
    max_adverse_excursion: float,
    round_trip_cost_bps: float = 20.0,
) -> np.ndarray:
    entry = frame["close"].to_numpy(dtype=float)
    future_high = frame["future_max_high"].to_numpy(dtype=float)
    close_horizon = frame["close_at_horizon"].to_numpy(dtype=float)
    labels = frame[label_col].fillna(0).to_numpy(dtype=int)
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
    cost = round_trip_cost_bps / 10_000.0
    return np.asarray(gross - cost, dtype=float)


def _fit_models_for_label(
    train: pd.DataFrame,
    test: pd.DataFrame,
    label_col: str,
    seed: int,
    top_quantile: float = 0.98,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    n_fit = max(1, int(len(train) * 0.8))
    fit = train.iloc[:n_fit]
    calibration = train.iloc[n_fit:]
    y_fit = fit[label_col].astype(int).to_numpy()
    y_cal = calibration[label_col].astype(int).to_numpy()
    if len(np.unique(y_fit)) < 2:
        raise ValueError("Fit split has only one class")

    imputer = SimpleImputer(strategy="median", add_indicator=True)
    x_fit = imputer.fit_transform(fit[FEATURE_COLS])
    x_cal = imputer.transform(calibration[FEATURE_COLS]) if len(calibration) else np.empty((0, x_fit.shape[1]))
    x_test = imputer.transform(test[FEATURE_COLS])

    # 1. Logistic Regression (Champion baseline)
    lr = LogisticRegression(max_iter=500, random_state=seed)
    lr.fit(x_fit, y_fit)
    lr_cal = lr.predict_proba(x_cal)[:, 1] if len(x_cal) else np.array([], dtype=float)
    lr_test = lr.predict_proba(x_test)[:, 1]
    lr_threshold = float(np.quantile(lr_cal, top_quantile)) if len(lr_cal) else 0.5

    # 2. LightGBM (Challenger with Isotonic Calibration)
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
        n_jobs=8,
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

    # Signal selection: top_k budget
    def top_k(values: np.ndarray) -> np.ndarray:
        count = max(1, int(round(len(values) * (1.0 - top_quantile))))
        count = min(count, len(values))
        order = np.argsort(-np.asarray(values, dtype=float), kind="mergesort")
        mask = np.zeros(len(values), dtype=bool)
        mask[order[:count]] = True
        return mask

    train_prevalence = float(train[label_col].mean())
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
        "lightgbm_calibration_method": calibration_method,
    }
    return {**probs, **{f"{name}__signal": s for name, s in signals.items()}}, metadata


def _fold_boundaries(
    window_start: datetime,
    evaluation_end: datetime,
    n_folds: int,
    warmup_days: int = 60,
) -> list[dict[str, datetime]]:
    boundaries = []
    first_test = window_start + timedelta(days=warmup_days)
    step = (evaluation_end - first_test) / n_folds
    for i in range(n_folds):
        t_start = first_test + step * i
        t_end = min(first_test + step * (i + 1), evaluation_end)
        if t_start >= t_end:
            break
        boundaries.append({"test_start": t_start, "test_end": t_end})
    return boundaries


def _evaluate_config(
    frame: pd.DataFrame,
    label_col: str,
    target_profit: float,
    max_adverse_excursion: float,
    boundaries: list[dict[str, datetime]],
    window_start: datetime,
    embargo: timedelta,
    seed: int,
    top_quantile: float = 0.98,
    round_trip_cost_bps: float = 20.0,
) -> dict[str, Any]:
    trade_ret = _trade_returns(
        frame,
        label_col=label_col,
        target_profit=target_profit,
        max_adverse_excursion=max_adverse_excursion,
        round_trip_cost_bps=round_trip_cost_bps,
    )
    df_eval = frame.copy()
    df_eval["trade_return"] = trade_ret

    folds_data = []
    oos_parts = []

    for fold_idx, b in enumerate(boundaries, start=1):
        t_fold = time.time()
        t_start = b["test_start"]
        t_end = b["test_end"]
        train_end = t_start - embargo
        train = df_eval[(df_eval["feature_time"] >= window_start) & (df_eval["feature_time"] < train_end)].copy()
        test = df_eval[(df_eval["feature_time"] >= t_start) & (df_eval["feature_time"] < t_end)].copy()

        if len(train) < 100 or len(test) == 0 or train[label_col].nunique() < 2:
            LOGGER.warning("Skipping fold %d", fold_idx)
            continue

        preds, meta = _fit_models_for_label(
            train, test, label_col=label_col, seed=seed + fold_idx, top_quantile=top_quantile
        )

        fold_record: dict[str, Any] = {
            "fold": fold_idx,
            "test_start": _iso(t_start),
            "test_end": _iso(t_end),
            "n_train": len(train),
            "n_test": len(test),
            "models": {},
        }
        oos_fold = test[["symbol", "feature_time", label_col, "trade_return"]].copy()
        for m in ("LogisticRegression", "LightGBM", "Baseline"):
            oos_fold[f"{m}__prob"] = preds[m]
            oos_fold[f"{m}__signal"] = preds[f"{m}__signal"]
            oos_fold[f"{m}__threshold"] = meta["thresholds"][m]
            fold_record["models"][m] = _binary_metrics(
                test[label_col].to_numpy(dtype=int),
                preds[m],
                preds[f"{m}__signal"],
                threshold=meta["thresholds"][m],
                trade_returns=test["trade_return"].to_numpy(),
                dates=test["feature_time"],
            )
        folds_data.append(fold_record)
        oos_parts.append(oos_fold)
        LOGGER.info("Fold %d/%d completed in %.1fs", fold_idx, len(boundaries), time.time() - t_fold)

    oos = pd.concat(oos_parts, ignore_index=True)
    models_summary = {}
    for m in ("LogisticRegression", "LightGBM", "Baseline"):
        full_metrics = _binary_metrics(
            oos[label_col].to_numpy(dtype=int),
            oos[f"{m}__prob"].to_numpy(dtype=float),
            oos[f"{m}__signal"].to_numpy(dtype=bool),
            threshold=None,
            trade_returns=oos["trade_return"].to_numpy(dtype=float),
            dates=oos["feature_time"],
        )
        fold_precisions = [f["models"][m]["precision"] for f in folds_data]
        fold_recalls = [f["models"][m]["recall"] for f in folds_data]
        fold_eces = [f["models"][m]["ece"] for f in folds_data]
        fold_briers = [f["models"][m]["brier_score"] for f in folds_data]
        fold_pnls = [f["models"][m]["pnl_sum"] for f in folds_data]
        fold_sharpes = [f["models"][m]["sharpe_daily_annualized"] for f in folds_data]
        fold_win_rates = [f["models"][m]["trade_win_rate"] for f in folds_data]

        full_metrics["bootstrap_95"] = {
            "precision": _bootstrap_mean(fold_precisions, seed),
            "recall": _bootstrap_mean(fold_recalls, seed),
            "ece": _bootstrap_mean(fold_eces, seed),
            "brier_score": _bootstrap_mean(fold_briers, seed),
            "pnl_sum": _bootstrap_mean(fold_pnls, seed),
            "sharpe": _bootstrap_mean(fold_sharpes, seed),
            "win_rate": _bootstrap_mean(fold_win_rates, seed),
        }
        models_summary[m] = full_metrics

    # Determine Champion for this config
    # Criteria: Precision is primary detector capability, Sharpe & Win rate as trade performance
    lr_prec = models_summary["LogisticRegression"]["precision"]
    lgb_prec = models_summary["LightGBM"]["precision"]
    lr_sharpe = models_summary["LogisticRegression"]["sharpe_daily_annualized"] or -99.0
    lgb_sharpe = models_summary["LightGBM"]["sharpe_daily_annualized"] or -99.0
    lr_pnl = models_summary["LogisticRegression"]["pnl_sum"]
    lgb_pnl = models_summary["LightGBM"]["pnl_sum"]
    lr_wr = models_summary["LogisticRegression"]["trade_win_rate"]
    lgb_wr = models_summary["LightGBM"]["trade_win_rate"]

    lgb_score = 0
    lr_score = 0
    if lgb_prec > lr_prec:
        lgb_score += 2
    else:
        lr_score += 2

    if lgb_sharpe > lr_sharpe:
        lgb_score += 1
    else:
        lr_score += 1

    if lgb_pnl > lr_pnl:
        lgb_score += 1
    else:
        lr_score += 1

    if lgb_wr > lr_wr:
        lgb_score += 1
    else:
        lr_score += 1

    champion = "LightGBM" if lgb_score > lr_score else "LogisticRegression"

    return {
        "target_profit": target_profit,
        "stop_loss": max_adverse_excursion,
        "prevalence": float(frame[label_col].mean()),
        "total_positive_rows": int(frame[label_col].sum()),
        "champion": champion,
        "champion_reason": f"Precision: LGBM {lgb_prec*100:.2f}% vs LR {lr_prec*100:.2f}%; WinRate: LGBM {lgb_wr*100:.1f}% vs LR {lr_wr*100:.1f}%; Sharpe: LGBM {lgb_sharpe:.2f} vs LR {lr_sharpe:.2f}",
        "models": models_summary,
        "folds": folds_data,
    }


def run_dual_backtest(
    db_path: Path,
    output_path: Path,
    lookback_days: int = 365,
    min_volume: float = 10_000_000.0,
    max_volume: float = 500_000_000.0,
    min_active_days: int = 180,
    n_folds: int = 10,
    embargo_hours: int = 48,
    horizon_hours: int = 12,
    top_quantile: float = 0.98,
    seed: int = 42,
    round_trip_cost_bps: float = 20.0,
) -> dict[str, Any]:
    t0 = time.time()
    LOGGER.info("Connecting to DuckDB: %s", db_path)
    conn = duckdb.connect(str(db_path), read_only=True)
    conn.execute("PRAGMA disable_progress_bar")

    as_of = conn.execute("SELECT MAX(close_time) FROM klines_5m").fetchone()[0]
    if not isinstance(as_of, datetime):
        as_of = pd.Timestamp(as_of).to_pydatetime()
    as_of = as_of.replace(tzinfo=as_of.tzinfo or timezone.utc)
    window_start = as_of - timedelta(days=lookback_days)
    evaluation_end = as_of - timedelta(hours=horizon_hours)
    history_start = window_start - timedelta(days=2)

    LOGGER.info("Selecting low-cap universe from %s to %s", window_start, as_of)
    universe = _select_universe(conn, window_start, as_of, min_volume, max_volume, min_active_days)
    symbols = universe["symbol"].astype(str).tolist()
    LOGGER.info("Selected %d symbols", len(symbols))

    LOGGER.info("Extracting candidate features and dual labels (single-pass)...")
    cache_path = Path("artifacts/lowcap_dual_features_cache.parquet")
    if cache_path.exists():
        LOGGER.info("Loading cached candidate features from %s...", cache_path)
        frame = pd.read_parquet(cache_path)
    else:
        LOGGER.info("Extracting candidate features and dual labels (chunked)...")
        frame = _load_data_chunked(
            conn,
            symbols=symbols,
            history_start=history_start,
            window_start=window_start,
            as_of=as_of,
            evaluation_end=evaluation_end,
            horizon_bars=horizon_hours * 12,
            horizon_hours=horizon_hours,
            candidate_return=0.08,
            candidate_funding=0.0002,
            chunk_size=25,
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(cache_path, index=False)
        LOGGER.info("Cached %d feature rows to %s", len(frame), cache_path)
    conn.close()

    LOGGER.info("Data loaded: %d rows across %d symbols in %.1fs", len(frame), frame["symbol"].nunique(), time.time() - t0)
    frame = frame.dropna(subset=["label_8_4", "label_20_10"]).copy()
    frame["label_8_4"] = frame["label_8_4"].astype(int)
    frame["label_20_10"] = frame["label_20_10"].astype(int)
    frame["funding_rate_raw"] = frame["funding_rate_raw"].fillna(0.0)
    frame[FEATURE_COLS] = frame[FEATURE_COLS].replace([np.inf, -np.inf], np.nan)
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame = frame.sort_values(["feature_time", "symbol"]).reset_index(drop=True)

    boundaries = _fold_boundaries(
        pd.Timestamp(window_start), pd.Timestamp(evaluation_end), n_folds=n_folds, warmup_days=60
    )
    embargo = timedelta(hours=embargo_hours)

    LOGGER.info("Evaluating Configuration 1: TP:SL = (8% : 4%)...")
    res_8_4 = _evaluate_config(
        frame=frame,
        label_col="label_8_4",
        target_profit=0.08,
        max_adverse_excursion=0.04,
        boundaries=boundaries,
        window_start=window_start,
        embargo=embargo,
        seed=seed,
        top_quantile=top_quantile,
        round_trip_cost_bps=round_trip_cost_bps,
    )

    LOGGER.info("Evaluating Configuration 2: TP:SL = (20% : 10%)...")
    res_20_10 = _evaluate_config(
        frame=frame,
        label_col="label_20_10",
        target_profit=0.20,
        max_adverse_excursion=0.10,
        boundaries=boundaries,
        window_start=window_start,
        embargo=embargo,
        seed=seed + 100,
        top_quantile=top_quantile,
        round_trip_cost_bps=round_trip_cost_bps,
    )

    elapsed = time.time() - t0
    report = {
        "artifact": "dual_config_backtest_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": elapsed,
        "dataset": {
            "source_db": str(db_path),
            "lookback_days": lookback_days,
            "evaluated_coins": len(symbols),
            "total_candidate_rows": len(frame),
            "time_range": f"{_iso(window_start)} -> {_iso(as_of)}",
            "validation": f"{n_folds}-Fold Walk-Forward with {embargo_hours}h Embargo",
            "signal_selection": f"Top {(1.0-top_quantile)*100:.1f}% (p{int(top_quantile*100)}) Quantile",
        },
        "config_8_4": res_8_4,
        "config_20_10": res_20_10,
        "overall_conclusion": {
            "config_8_4_champion": res_8_4["champion"],
            "config_20_10_champion": res_20_10["champion"],
            "summary": (
                f"Config (8%:4%): Champion is {res_8_4['champion']}. "
                f"Config (20%:10%): Champion is {res_20_10['champion']}."
            ),
        },
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(_round_for_json(report), indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf-8",
    )
    LOGGER.info("Report saved to %s in %.1fs", output_path, elapsed)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path(r"D:\Quant-trading\data_lake\quant_master.duckdb"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/dual_config_backtest_report.json"))
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--n-folds", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    report = run_dual_backtest(
        db_path=args.db,
        output_path=args.output,
        lookback_days=args.lookback_days,
        n_folds=args.n_folds,
        seed=args.seed,
    )
    print("\n" + "=" * 80)
    print("BACKTEST DUAL CONFIG COMPLETED SUCCESSFULLY!")
    print(f"Runtime: {report['runtime_seconds']:.1f}s")
    print(f"Config (8% : 4%) Champion: {report['config_8_4']['champion']}")
    print(f"Config (20% : 10%) Champion: {report['config_20_10']['champion']}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
