"""10-Fold Walk-Forward Backtest: 3-Day Holding Without Stop Loss.

Evaluates V1 (LogisticRegression / Champion) vs V2 (LightGBM / Challenger)
when NO STOP LOSS is applied, measuring:
1. Probability of hitting TP (-20% drop) within 24h, 48h, and 72h (3 days).
2. Rate of signals that breached +10% adverse move but subsequently hit TP 20% within 3 days ("false stop-outs").
3. Max Adverse Excursion (MAE) risk profile (unrealized drawdown without SL).
4. Trade returns & Profit Factor when closing at TP 20% or at the end of Day 3.
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

LOGGER = logging.getLogger("dao_vang.no_sl_backtest")

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


def _bootstrap_mean(values: list[float], seed: int, n_bootstrap: int = 2000) -> dict[str, Any]:
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


def _fold_boundaries(
    window_start: datetime,
    evaluation_end: datetime,
    n_folds: int = 10,
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


def load_dataset_with_forward_72h(
    parquet_path: Path,
    db_path: Path,
) -> pd.DataFrame:
    LOGGER.info("Reading feature cache from %s...", parquet_path)
    t0 = time.time()
    conn = duckdb.connect(str(db_path), read_only=True)
    conn.execute("PRAGMA disable_progress_bar")
    conn.execute("SET threads=4")

    # Compute 72h forward rolling window on klines_5m and join with candidate features
    query = f"""
    WITH target_klines AS (
        SELECT k.symbol, k.close_time, k.close, k.high, k.low
        FROM klines_5m k
        WHERE k.close_time >= '2025-08-25' AND k.close_time <= '2026-09-01'
    ),
    fwd AS (
        SELECT symbol, close_time, close,
            MIN(low) OVER (PARTITION BY symbol ORDER BY close_time ROWS BETWEEN 1 FOLLOWING AND 288 FOLLOWING) as min_low_24h,
            MIN(low) OVER (PARTITION BY symbol ORDER BY close_time ROWS BETWEEN 1 FOLLOWING AND 576 FOLLOWING) as min_low_48h,
            MIN(low) OVER (PARTITION BY symbol ORDER BY close_time ROWS BETWEEN 1 FOLLOWING AND 864 FOLLOWING) as min_low_72h,
            MAX(high) OVER (PARTITION BY symbol ORDER BY close_time ROWS BETWEEN 1 FOLLOWING AND 864 FOLLOWING) as max_high_72h,
            LEAD(close, 864) OVER (PARTITION BY symbol ORDER BY close_time) as close_72h,
            COUNT(*) OVER (PARTITION BY symbol ORDER BY close_time ROWS BETWEEN 1 FOLLOWING AND 864 FOLLOWING) as fwd_count
        FROM target_klines
    )
    SELECT 
        c.symbol,
        c.feature_time,
        c.close as entry_price,
        c.return_5m,
        c.volatility_5m,
        c.volatility_24h,
        c.return_1h,
        c.return_4h,
        c.return_24h,
        COALESCE(c.funding_rate_raw, 0.0) as funding_rate_raw,
        c.taker_ratio,
        c.vol_surge_24h,
        c.oi_change_1h,
        c.oi_change_4h,
        c.top_acct_ratio,
        c.global_ls_ratio,
        c.taker_bs_ratio,
        c.label_20_10,
        c.future_min_low as future_min_low_12h,
        c.future_max_high as future_max_high_12h,
        f.min_low_24h,
        f.min_low_48h,
        f.min_low_72h,
        f.max_high_72h,
        f.close_72h
    FROM read_parquet('{parquet_path.as_posix()}') c
    INNER JOIN fwd f 
        ON c.symbol = f.symbol 
       AND c.feature_time = f.close_time
    WHERE f.fwd_count = 864
      AND c.return_5m IS NOT NULL
      AND c.volatility_5m IS NOT NULL
      AND c.return_1h IS NOT NULL
      AND c.return_4h IS NOT NULL
      AND c.return_24h IS NOT NULL
    ORDER BY c.feature_time, c.symbol
    """
    LOGGER.info("Executing DuckDB window join for 72h forward outcomes...")
    df = conn.execute(query).fetchdf()
    conn.close()
    LOGGER.info("Loaded %d rows with 72h forward outcomes in %.2fs", len(df), time.time() - t0)
    return df


def run_backtest_3day_no_sl(
    df: pd.DataFrame,
    n_folds: int = 10,
    top_quantile: float = 0.98,
    seed: int = 42,
    target_drop: float = 0.20,
    round_trip_cost_bps: float = 20.0,
) -> dict[str, Any]:
    t0 = time.time()
    fee = round_trip_cost_bps / 10_000.0

    as_of = df["feature_time"].max()
    window_start = df["feature_time"].min()
    evaluation_end = as_of
    embargo = timedelta(hours=48)
    boundaries = _fold_boundaries(window_start, evaluation_end, n_folds=n_folds, warmup_days=60)

    LOGGER.info("Starting 10-fold Walk-Forward Backtest (3-day evaluation without SL)...")
    folds_results = []
    oos_records = []

    for fold_idx, b in enumerate(boundaries, start=1):
        t_start = b["test_start"]
        t_end = b["test_end"]
        train_end = t_start - embargo

        train = df[(df["feature_time"] >= window_start) & (df["feature_time"] < train_end)].copy()
        test = df[(df["feature_time"] >= t_start) & (df["feature_time"] < t_end)].copy()

        if len(train) < 200 or len(test) == 0:
            LOGGER.warning("Fold %d skipped: insufficient samples", fold_idx)
            continue

        # Fit models on label_20_10 (same training target as production V1/V2 dual backtest)
        n_fit = max(1, int(len(train) * 0.8))
        fit = train.iloc[:n_fit]
        calibration = train.iloc[n_fit:]
        y_fit = fit["label_20_10"].astype(int).to_numpy()
        y_cal = calibration["label_20_10"].astype(int).to_numpy()

        imputer = SimpleImputer(strategy="median", add_indicator=True)
        x_fit = imputer.fit_transform(fit[FEATURE_COLS])
        x_cal = imputer.transform(calibration[FEATURE_COLS]) if len(calibration) else np.empty((0, x_fit.shape[1]))
        x_test = imputer.transform(test[FEATURE_COLS])

        # 1. Logistic Regression (V1 / Champion)
        lr = LogisticRegression(max_iter=1000, random_state=seed + fold_idx)
        lr.fit(x_fit, y_fit)
        lr_test_prob = lr.predict_proba(x_test)[:, 1]

        # 2. LightGBM + Isotonic Calibration (V2 / Challenger)
        lgb_model = lgb.LGBMClassifier(
            random_state=seed + fold_idx,
            n_estimators=200,
            learning_rate=0.05,
            max_depth=5,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            deterministic=True,
            force_col_wise=True,
            verbosity=-1,
            n_jobs=2,
        )
        lgb_model.fit(x_fit, y_fit)
        lgb_cal_raw = lgb_model.predict_proba(x_cal)[:, 1] if len(x_cal) else np.array([], dtype=float)
        lgb_test_raw = lgb_model.predict_proba(x_test)[:, 1]

        if len(lgb_cal_raw) >= 50 and len(np.unique(y_cal)) >= 2:
            calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            calibrator.fit(lgb_cal_raw, y_cal)
            lgb_test_prob = np.asarray(calibrator.predict(lgb_test_raw), dtype=float)
        else:
            lgb_test_prob = lgb_test_raw

        # Top 2% selection
        def top_k_mask(probs: np.ndarray) -> np.ndarray:
            k = max(1, int(round(len(probs) * (1.0 - top_quantile))))
            k = min(k, len(probs))
            order = np.argsort(-probs, kind="mergesort")
            mask = np.zeros(len(probs), dtype=bool)
            mask[order[:k]] = True
            return mask

        lr_signal = top_k_mask(lr_test_prob)
        lgb_signal = top_k_mask(lgb_test_prob)

        # Baseline random signal
        rng = np.random.default_rng(seed + fold_idx + 500)
        base_signal = np.zeros(len(test), dtype=bool)
        k_base = max(1, int(round(len(test) * (1.0 - top_quantile))))
        base_signal[rng.choice(len(test), size=k_base, replace=False)] = True

        test_copy = test.copy()
        test_copy["fold"] = fold_idx
        test_copy["V1__signal"] = lr_signal
        test_copy["V2__signal"] = lgb_signal
        test_copy["Baseline__signal"] = base_signal
        oos_records.append(test_copy)

        LOGGER.info(
            "Fold %d/%d [%s -> %s]: Train=%d, Test=%d, V1 signals=%d, V2 signals=%d",
            fold_idx,
            len(boundaries),
            t_start.strftime("%Y-%m-%d"),
            t_end.strftime("%Y-%m-%d"),
            len(train),
            len(test),
            int(lr_signal.sum()),
            int(lgb_signal.sum()),
        )

    oos = pd.concat(oos_records, ignore_index=True)

    # Compute outcomes on OOS
    entry = oos["entry_price"].to_numpy(dtype=float)
    min_24h = oos["min_low_24h"].to_numpy(dtype=float)
    min_48h = oos["min_low_48h"].to_numpy(dtype=float)
    min_72h = oos["min_low_72h"].to_numpy(dtype=float)
    max_72h = oos["max_high_72h"].to_numpy(dtype=float)
    close_72h = oos["close_72h"].to_numpy(dtype=float)
    fwd_high_12h = oos["future_max_high_12h"].to_numpy(dtype=float)

    # Hit target drop (>= 20%) within timeframes
    hit_tp_24h = (entry - min_24h) / entry >= target_drop
    hit_tp_48h = (entry - min_48h) / entry >= target_drop
    hit_tp_72h = (entry - min_72h) / entry >= target_drop

    # MAE within 72h
    mae_72h = np.maximum(0.0, (max_72h - entry) / entry)
    # Did trade breach 10% SL during 72h?
    breached_sl_10 = (max_72h - entry) / entry >= 0.10

    # False stop-outs: Breached 10% SL earlier, but still reached TP 20% within 3 days!
    recovered_after_sl = breached_sl_10 & hit_tp_72h

    # Trade return WITHOUT SL:
    # If hit TP 20% anytime within 72h -> exit at +20%
    # Else -> exit at close of 72h: (entry - close_72h) / entry
    gross_return_no_sl = np.where(hit_tp_72h, target_drop, (entry - close_72h) / entry)
    net_return_no_sl = gross_return_no_sl - fee

    oos["hit_tp_24h"] = hit_tp_24h
    oos["hit_tp_48h"] = hit_tp_48h
    oos["hit_tp_72h"] = hit_tp_72h
    oos["mae_72h"] = mae_72h
    oos["breached_sl_10"] = breached_sl_10
    oos["recovered_after_sl"] = recovered_after_sl
    oos["net_return_no_sl"] = net_return_no_sl

    def analyze_model(signal_col: str, model_name: str) -> dict[str, Any]:
        mask = oos[signal_col].to_numpy(dtype=bool)
        n_signals = int(mask.sum())
        if n_signals == 0:
            return {"name": model_name, "signals": 0}

        ret = net_return_no_sl[mask]
        mae = mae_72h[mask]
        hit_24 = hit_tp_24h[mask]
        hit_48 = hit_tp_48h[mask]
        hit_72 = hit_tp_72h[mask]
        sl_breach = breached_sl_10[mask]
        recovered = recovered_after_sl[mask]

        wins = ret[ret > 0]
        losses = ret[ret < 0]
        gross_profit = float(wins.sum()) if len(wins) else 0.0
        gross_loss = float(-losses.sum()) if len(losses) else 0.0001
        pf = gross_profit / gross_loss if gross_loss > 0 else 999.0

        # Per fold metrics for bootstrap CI
        fold_hits = []
        fold_evs = []
        for f in sorted(oos["fold"].unique()):
            f_mask = mask & (oos["fold"].to_numpy() == f)
            if f_mask.sum() > 0:
                fold_hits.append(float(hit_tp_72h[f_mask].mean()))
                fold_evs.append(float(net_return_no_sl[f_mask].mean()))

        # Daily Sharpe
        dates = pd.to_datetime(oos["feature_time"][mask], utc=True).dt.floor("D")
        daily = pd.Series(ret, index=dates).groupby(level=0).sum()
        daily_mean = float(daily.mean()) if len(daily) else 0.0
        daily_std = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
        sharpe = float(math.sqrt(365.0) * daily_mean / daily_std) if daily_std > 0 else None

        return {
            "name": model_name,
            "total_signals": n_signals,
            "tp_hit_rate_24h_pct": round(float(hit_24.mean()) * 100, 2),
            "tp_hit_rate_48h_pct": round(float(hit_48.mean()) * 100, 2),
            "tp_hit_rate_72h_pct": round(float(hit_72.mean()) * 100, 2),
            "bootstrap_tp_hit_rate_72h": _bootstrap_mean(fold_hits, seed),
            "mae_mean_pct": round(float(mae.mean()) * 100, 2),
            "mae_p50_pct": round(float(np.percentile(mae, 50)) * 100, 2),
            "mae_p75_pct": round(float(np.percentile(mae, 75)) * 100, 2),
            "mae_p90_pct": round(float(np.percentile(mae, 90)) * 100, 2),
            "mae_max_pct": round(float(mae.max()) * 100, 2),
            "mae_exceed_10pct_rate": round(float((mae >= 0.10).mean()) * 100, 2),
            "mae_exceed_20pct_rate": round(float((mae >= 0.20).mean()) * 100, 2),
            "mae_exceed_50pct_rate": round(float((mae >= 0.50).mean()) * 100, 2),
            "breached_sl10_rate_pct": round(float(sl_breach.mean()) * 100, 2),
            "recovered_after_sl_rate_pct": round(float(recovered.mean()) * 100, 2),
            "recovered_of_breached_sl_pct": round(float(recovered.sum()) / max(1, float(sl_breach.sum())) * 100, 2),
            "expected_pnl_per_trade_pct": round(float(ret.mean()) * 100, 2),
            "bootstrap_expected_pnl": _bootstrap_mean(fold_evs, seed),
            "profit_factor": round(pf, 2),
            "trade_win_rate_pct": round(float((ret > 0).mean()) * 100, 2),
            "total_pnl_pct": round(float(ret.sum()) * 100, 2),
            "sharpe_annualized": round(sharpe, 2) if sharpe is not None else None,
        }

    v1_metrics = analyze_model("V1__signal", "V1 (LogisticRegression / Champion)")
    v2_metrics = analyze_model("V2__signal", "V2 (LightGBM / Challenger)")
    base_metrics = analyze_model("Baseline__signal", "Baseline (Random Top 2%)")

    runtime = time.time() - t0
    report = {
        "artifact": "backtest_3day_no_sl_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runtime_seconds": round(runtime, 2),
        "parameters": {
            "target_drop_pct": 20.0,
            "stop_loss": None,
            "holding_period": "3 days (72 hours / 864 bars)",
            "top_quantile": top_quantile,
            "round_trip_fee_bps": round_trip_cost_bps,
            "total_oos_candidates": len(oos),
        },
        "v1": v1_metrics,
        "v2": v2_metrics,
        "baseline": base_metrics,
    }

    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parquet_path = Path("artifacts/lowcap_dual_features_cache.parquet")
    db_path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    output_path = Path("artifacts/backtest_3day_no_sl_report.json")

    df = load_dataset_with_forward_72h(parquet_path, db_path)
    report = run_backtest_3day_no_sl(df)

    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("Report saved to %s", output_path)

    v1 = report["v1"]
    v2 = report["v2"]
    b = report["baseline"]

    print("\n" + "=" * 85)
    print("      KẾT QUẢ BACKTEST 3 NGÀY KHÔNG STOP LOSS (TP = -20%, THỜI GIAN = 72H)")
    print("=" * 85)
    print(f"{'Chỉ số':<42} | {'V1 (Champion)':<18} | {'V2 (Challenger)':<18}")
    print("-" * 85)
    print(f"{'Tổng số tín hiệu OOS (Top 2% confident)':<42} | {v1['total_signals']:<18} | {v2['total_signals']:<18}")
    print(f"{'Tỷ lệ chạm TP 20% sau 24h (1 ngày)':<42} | {v1['tp_hit_rate_24h_pct']:>16}% | {v2['tp_hit_rate_24h_pct']:>16}%")
    print(f"{'Tỷ lệ chạm TP 20% sau 48h (2 ngày)':<42} | {v1['tp_hit_rate_48h_pct']:>16}% | {v2['tp_hit_rate_48h_pct']:>16}%")
    print(f"{'Tỷ lệ chạm TP 20% sau 72h (3 ngày)':<42} | {v1['tp_hit_rate_72h_pct']:>16}% | {v2['tp_hit_rate_72h_pct']:>16}%")
    print(f"{'-> CI 95% tỷ lệ chạm TP 72h':<42} | {v1['bootstrap_tp_hit_rate_72h']['ci_lower']*100:.1f}% - {v1['bootstrap_tp_hit_rate_72h']['ci_upper']*100:.1f}% | {v2['bootstrap_tp_hit_rate_72h']['ci_lower']*100:.1f}% - {v2['bootstrap_tp_hit_rate_72h']['ci_upper']*100:.1f}%")
    print("-" * 85)
    print(f"{'Bị vượt mốc 10% nhưng vẫn chạm TP 20% (Cứu thua)':<42} | {v1['recovered_after_sl_rate_pct']:>16}% | {v2['recovered_after_sl_rate_pct']:>16}%")
    print(f"{'Tỷ lệ lệnh dính SL 10% thực ra quay lại TP':<42} | {v1['recovered_of_breached_sl_pct']:>16}% | {v2['recovered_of_breached_sl_pct']:>16}%")
    print("-" * 85)
    print(f"{'RỦI RO ĐI NGƯỢC (MAE - Max Drawdown vị thế)':<42} | {'':<18} | {'':<18}")
    print(f"{'  - MAE trung vị (P50)':<42} | {v1['mae_p50_pct']:>16}% | {v2['mae_p50_pct']:>16}%")
    print(f"{'  - MAE trung bình (Mean)':<42} | {v1['mae_mean_pct']:>16}% | {v2['mae_mean_pct']:>16}%")
    print(f"{'  - MAE P90 (10% xấu nhất)':<42} | {v1['mae_p90_pct']:>16}% | {v2['mae_p90_pct']:>16}%")
    print(f"{'  - MAE Max (Xấu nhất)':<42} | {v1['mae_max_pct']:>16}% | {v2['mae_max_pct']:>16}%")
    print(f"{'  - Tỷ lệ lệnh âm ngược > 20%':<42} | {v1['mae_exceed_20pct_rate']:>16}% | {v2['mae_exceed_20pct_rate']:>16}%")
    print(f"{'  - Tỷ lệ lệnh âm ngược > 50%':<42} | {v1['mae_exceed_50pct_rate']:>16}% | {v2['mae_exceed_50pct_rate']:>16}%")
    print("-" * 85)
    print(f"{'KẾT QUẢ PNL THOÁT LỆNH NGÀY THỨ 3 (TRỪ PHÍ)':<42} | {'':<18} | {'':<18}")
    print(f"{'Hệ số lợi nhuận (Profit Factor)':<42} | {v1['profit_factor']:>18} | {v2['profit_factor']:>18}")
    print(f"{'Lợi nhuận kỳ vọng mỗi tín hiệu (EV)':<42} | {v1['expected_pnl_per_trade_pct']:>16}% | {v2['expected_pnl_per_trade_pct']:>16}%")
    print(f"{'Tỷ lệ lệnh có lãi tổng thể (Win Rate)':<42} | {v1['trade_win_rate_pct']:>16}% | {v2['trade_win_rate_pct']:>16}%")
    print(f"{'Sharpe Ratio năm hóa':<42} | {str(v1['sharpe_annualized']):>18} | {str(v2['sharpe_annualized']):>18}")
    print("=" * 85)


if __name__ == "__main__":
    main()
