"""3-Day No-Stop-Loss Backtest: LogisticRegression vs LightGBM.

Evaluates the ability of models to hit Take Profit (TP = 8% and TP = 20%)
within a 3-day horizon (72 hours = 864 bars of 5m candles) without ANY Stop Loss.
Also calculates Maximum Adverse Excursion (MAE) to measure the floating drawdown
traders must endure when not applying a Stop Loss.
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

LOGGER = logging.getLogger("dao_vang.tp_only_3d")

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
    maes: np.ndarray,
    dates: pd.Series,
) -> dict[str, Any]:
    actual = np.asarray(y_true, dtype=int)
    probability = np.clip(np.asarray(y_prob, dtype=float), 0.0, 1.0)
    predicted = np.asarray(predicted, dtype=bool)
    returns = np.asarray(trade_returns, dtype=float)
    mae_arr = np.asarray(maes, dtype=float)
    n = len(actual)
    tp = int(((actual == 1) & predicted).sum())
    fp = int(((actual == 0) & predicted).sum())
    fn = int(((actual == 1) & ~predicted).sum())
    n_pred = int(predicted.sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2.0 * precision * recall / (precision + recall) if precision + recall else 0.0

    selected_returns = returns[predicted]
    selected_maes = mae_arr[predicted]
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

    # Adverse excursion stats for trades without SL
    avg_mae = float(selected_maes.mean()) if len(selected_maes) else 0.0
    max_mae = float(selected_maes.max()) if len(selected_maes) else 0.0
    pct_mae_gt_10 = float((selected_maes > 0.10).mean()) if len(selected_maes) else 0.0
    pct_mae_gt_20 = float((selected_maes > 0.20).mean()) if len(selected_maes) else 0.0
    pct_mae_gt_50 = float((selected_maes > 0.50).mean()) if len(selected_maes) else 0.0

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
        "risk_without_sl": {
            "avg_floating_loss_mae": avg_mae,
            "max_floating_loss_mae": max_mae,
            "rate_floating_loss_gt_10pct": pct_mae_gt_10,
            "rate_floating_loss_gt_20pct": pct_mae_gt_20,
            "rate_floating_loss_gt_50pct": pct_mae_gt_50,
        },
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


def _load_data_3d_chunked(
    conn: duckdb.DuckDBPyConnection,
    symbols: list[str],
    history_start: datetime,
    window_start: datetime,
    as_of: datetime,
    evaluation_end: datetime,
    horizon_bars: int = 864,  # 3 days = 72h = 864 bars of 5m
    candidate_return: float = 0.08,
    candidate_funding: float = 0.0002,
    chunk_size: int = 25,
) -> pd.DataFrame:
    chunks = [symbols[i:i + chunk_size] for i in range(0, len(symbols), chunk_size)]
    horizon_plus = "INTERVAL '4335 minutes'"  # 72h 15m
    dfs = []
    for idx, chunk in enumerate(chunks, 1):
        t_c = time.time()
        conn.register("_target_symbols_3d", pd.DataFrame({"symbol": chunk}))
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
                INNER JOIN _target_symbols_3d u ON u.symbol = k.symbol
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
                -- NO STOP LOSS: Label=1 if price reaches TP at ANY POINT within 3 days
                CASE
                    WHEN future_count = {horizon_bars} AND time_at_horizon <= feature_time + {horizon_plus}
                    THEN CASE
                        WHEN future_min_low <= close * 0.92 THEN 1 ELSE 0
                    END
                    ELSE NULL
                END AS hit_tp8_3d,
                CASE
                    WHEN future_count = {horizon_bars} AND time_at_horizon <= feature_time + {horizon_plus}
                    THEN CASE
                        WHEN future_min_low <= close * 0.80 THEN 1 ELSE 0
                    END
                    ELSE NULL
                END AS hit_tp20_3d,
                -- Maximum adverse excursion (floating drawdown) during 3 days
                (future_max_high - close) / close AS max_ae_3d
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
                conn.unregister("_target_symbols_3d")
            except Exception:
                pass
        dfs.append(df_chunk)
        LOGGER.info("Extracted 3d chunk %d/%d (%d coins): %d rows in %.2fs", idx, len(chunks), len(chunk), len(df_chunk), time.time() - t_c)
    return pd.concat(dfs, ignore_index=True)


def _trade_returns_no_sl(
    frame: pd.DataFrame,
    hit_label_col: str,
    target_profit: float,
    round_trip_cost_bps: float = 20.0,
) -> np.ndarray:
    """If hit TP at any point within 3d, take profit (+target_profit).

    If not hit, close at 3-day horizon close: short return = (entry - close_3d) / entry.
    """
    entry = frame["close"].to_numpy(dtype=float)
    close_3d = frame["close_at_horizon"].to_numpy(dtype=float)
    hits = frame[hit_label_col].fillna(0).to_numpy(dtype=int)

    # If hit TP, return target_profit. If not hit, exit at horizon close.
    gross = np.where(
        hits == 1,
        target_profit,
        entry / np.maximum(close_3d, 1e-12) - 1.0,
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

    # 1. Logistic Regression
    lr = LogisticRegression(max_iter=500, random_state=seed)
    lr.fit(x_fit, y_fit)
    lr_cal = lr.predict_proba(x_cal)[:, 1] if len(x_cal) else np.array([], dtype=float)
    lr_test = lr.predict_proba(x_test)[:, 1]
    lr_threshold = float(np.quantile(lr_cal, top_quantile)) if len(lr_cal) else 0.5

    # 2. LightGBM + Isotonic Calibration
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
    boundaries: list[dict[str, datetime]],
    window_start: datetime,
    embargo: timedelta,
    seed: int,
    top_quantile: float = 0.98,
    round_trip_cost_bps: float = 20.0,
) -> dict[str, Any]:
    trade_ret = _trade_returns_no_sl(
        frame,
        hit_label_col=label_col,
        target_profit=target_profit,
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
        oos_fold = test[["symbol", "feature_time", label_col, "trade_return", "max_ae_3d"]].copy()
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
                maes=test["max_ae_3d"].to_numpy(),
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
            maes=oos["max_ae_3d"].to_numpy(dtype=float),
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
        "stop_loss": "NONE (No Stop Loss, 3-day hold)",
        "prevalence": float(frame[label_col].mean()),
        "total_positive_rows": int(frame[label_col].sum()),
        "champion": champion,
        "champion_reason": f"Precision: LGBM {lgb_prec*100:.2f}% vs LR {lr_prec*100:.2f}%; WinRate: LGBM {lgb_wr*100:.1f}% vs LR {lr_wr*100:.1f}%; Sharpe: LGBM {lgb_sharpe:.2f} vs LR {lr_sharpe:.2f}",
        "models": models_summary,
        "folds": folds_data,
    }


def run_tp_only_backtest(
    db_path: Path,
    output_path: Path,
    lookback_days: int = 365,
    min_volume: float = 10_000_000.0,
    max_volume: float = 500_000_000.0,
    min_active_days: int = 180,
    n_folds: int = 10,
    embargo_hours: int = 48,
    horizon_hours: int = 72,  # 3 days = 72h
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

    cache_path = Path("artifacts/lowcap_tp_only_3d_cache.parquet")
    if cache_path.exists():
        LOGGER.info("Loading cached 3-day candidate features from %s...", cache_path)
        frame = pd.read_parquet(cache_path)
    else:
        LOGGER.info("Extracting candidate features and 3-day labels (chunked)...")
        frame = _load_data_3d_chunked(
            conn,
            symbols=symbols,
            history_start=history_start,
            window_start=window_start,
            as_of=as_of,
            evaluation_end=evaluation_end,
            horizon_bars=horizon_hours * 12,
            candidate_return=0.08,
            candidate_funding=0.0002,
            chunk_size=25,
        )
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(cache_path, index=False)
        LOGGER.info("Cached %d feature rows to %s", len(frame), cache_path)
    conn.close()

    LOGGER.info("Data loaded: %d rows across %d symbols in %.1fs", len(frame), frame["symbol"].nunique(), time.time() - t0)
    frame = frame.dropna(subset=["hit_tp8_3d", "hit_tp20_3d"]).copy()
    frame["hit_tp8_3d"] = frame["hit_tp8_3d"].astype(int)
    frame["hit_tp20_3d"] = frame["hit_tp20_3d"].astype(int)
    frame["funding_rate_raw"] = frame["funding_rate_raw"].fillna(0.0)
    frame[FEATURE_COLS] = frame[FEATURE_COLS].replace([np.inf, -np.inf], np.nan)
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame = frame.sort_values(["feature_time", "symbol"]).reset_index(drop=True)

    boundaries = _fold_boundaries(
        pd.Timestamp(window_start), pd.Timestamp(evaluation_end), n_folds=n_folds, warmup_days=60
    )
    embargo = timedelta(hours=embargo_hours)

    LOGGER.info("Evaluating Config A: TP = 8% in 3 days (NO STOP LOSS)...")
    res_tp8 = _evaluate_config(
        frame=frame,
        label_col="hit_tp8_3d",
        target_profit=0.08,
        boundaries=boundaries,
        window_start=window_start,
        embargo=embargo,
        seed=seed,
        top_quantile=top_quantile,
        round_trip_cost_bps=round_trip_cost_bps,
    )

    LOGGER.info("Evaluating Config B: TP = 20% in 3 days (NO STOP LOSS)...")
    res_tp20 = _evaluate_config(
        frame=frame,
        label_col="hit_tp20_3d",
        target_profit=0.20,
        boundaries=boundaries,
        window_start=window_start,
        embargo=embargo,
        seed=seed + 100,
        top_quantile=top_quantile,
        round_trip_cost_bps=round_trip_cost_bps,
    )

    elapsed = time.time() - t0
    report = {
        "artifact": "tp_only_3d_backtest_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": elapsed,
        "dataset": {
            "source_db": str(db_path),
            "lookback_days": lookback_days,
            "evaluated_coins": len(symbols),
            "total_candidate_rows": len(frame),
            "time_range": f"{_iso(window_start)} -> {_iso(as_of)}",
            "horizon": "3 Days (72 Hours = 864 bars 5m)",
            "stop_loss_policy": "NONE (Positions held up to 3 days until TP hit or 72h close)",
            "validation": f"{n_folds}-Fold Walk-Forward with {embargo_hours}h Embargo",
            "signal_selection": f"Top {(1.0-top_quantile)*100:.1f}% (p{int(top_quantile*100)}) Quantile",
        },
        "config_tp8_3d": res_tp8,
        "config_tp20_3d": res_tp20,
        "overall_conclusion": {
            "tp8_champion": res_tp8["champion"],
            "tp20_champion": res_tp20["champion"],
            "summary": (
                f"3-Day TP 8% (No SL): Champion is {res_tp8['champion']}. "
                f"3-Day TP 20% (No SL): Champion is {res_tp20['champion']}."
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
    parser.add_argument("--output", type=Path, default=Path("artifacts/tp_only_3d_backtest_report.json"))
    parser.add_argument("--lookback-days", type=int, default=365)
    parser.add_argument("--n-folds", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    report = run_tp_only_backtest(
        db_path=args.db,
        output_path=args.output,
        lookback_days=args.lookback_days,
        n_folds=args.n_folds,
        seed=args.seed,
    )
    print("\n" + "=" * 80)
    print("3-DAY NO STOP LOSS BACKTEST COMPLETED SUCCESSFULLY!")
    print(f"Runtime: {report['runtime_seconds']:.1f}s")
    print(f"TP 8% (3 Days, No SL) Champion: {report['config_tp8_3d']['champion']}")
    print(f"TP 20% (3 Days, No SL) Champion: {report['config_tp20_3d']['champion']}")
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
