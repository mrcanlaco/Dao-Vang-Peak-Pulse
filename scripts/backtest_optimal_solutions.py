"""Comprehensive Backtest of Proposed Optimization Solutions.

Evaluates 5 strategic solution frameworks on V1 (LogisticRegression) and V2 (LightGBM):
1. Widened Stop Loss (SL = 15%, 18%, 20%, 25% vs TP = 20%, holding up to 72h)
2. Breakeven Trailing Stop (Initial SL 18%, move SL to 0% after price drops 10%, TP 20%)
3. Partial Take Profit (50% exit at -10% & move to BE, 50% exit at -20%, initial SL 18%)
4. Scale-in / DCA Limit Order (50% market, 50% limit at +10% pump, SL at +20%, TP at -20%)
5. Time-stop Invalidation (Exit at 24h if price has not dropped at least 5%, SL 18%, TP 20%)

Uses exact 10-fold Walk-Forward cross validation on 189 low-cap coins across 365 days.
"""

from __future__ import annotations

import json
import logging
import math
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

LOGGER = logging.getLogger("dao_vang.optimal_backtest")

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


def simulate_trade_strategy(
    strategy_name: str,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    entry_price: float,
    fee: float = 0.0020,
    **kwargs: Any,
) -> dict[str, Any]:
    """Simulate candle-by-candle path outcome for a single trade.
    
    highs, lows, closes: 1D arrays of forward 5m candle prices (up to 864 bars = 72h).
    """
    n_bars = len(highs)
    if n_bars == 0 or entry_price <= 0:
        return {"pnl": -fee, "status": "no_data", "hit_tp": False, "hit_sl": False, "bars_held": 0}

    # Normalize relative price trajectory: return for short = (entry - price) / entry
    # Adverse move (pump against short) = (price - entry) / entry
    pump_pct = (highs - entry_price) / entry_price
    drop_pct = (entry_price - lows) / entry_price

    if strategy_name == "baseline_sl10":
        # 12h max horizon (144 bars), TP 20%, SL 10%
        limit_bars = min(144, n_bars)
        for b in range(limit_bars):
            if pump_pct[b] >= 0.10:
                return {"pnl": -0.10 - fee, "status": "sl_hit", "hit_tp": False, "hit_sl": True, "bars_held": b + 1}
            if drop_pct[b] >= 0.20:
                return {"pnl": 0.20 - fee, "status": "tp_hit", "hit_tp": True, "hit_sl": False, "bars_held": b + 1}
        exit_pnl = (entry_price - closes[limit_bars - 1]) / entry_price
        return {"pnl": exit_pnl - fee, "status": "timeout", "hit_tp": False, "hit_sl": False, "bars_held": limit_bars}

    elif strategy_name == "fixed_sl":
        sl_pct = kwargs.get("sl_pct", 0.18)
        tp_pct = kwargs.get("tp_pct", 0.20)
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        for b in range(max_bars):
            if pump_pct[b] >= sl_pct:
                return {"pnl": -sl_pct - fee, "status": "sl_hit", "hit_tp": False, "hit_sl": True, "bars_held": b + 1}
            if drop_pct[b] >= tp_pct:
                return {"pnl": tp_pct - fee, "status": "tp_hit", "hit_tp": True, "hit_sl": False, "bars_held": b + 1}
        exit_pnl = (entry_price - closes[max_bars - 1]) / entry_price
        return {"pnl": exit_pnl - fee, "status": "timeout", "hit_tp": False, "hit_sl": False, "bars_held": max_bars}

    elif strategy_name == "breakeven_trail":
        # Initial SL e.g. 18%, when drop reaches 10% (1R), move SL to 0% (breakeven)
        sl_pct = kwargs.get("sl_pct", 0.18)
        tp_pct = kwargs.get("tp_pct", 0.20)
        be_trigger = kwargs.get("be_trigger", 0.10)
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        sl_active = sl_pct
        be_activated = False

        for b in range(max_bars):
            # Check SL breach
            if pump_pct[b] >= sl_active:
                pnl_exit = 0.0 if be_activated else -sl_pct
                return {"pnl": pnl_exit - fee, "status": "be_exit" if be_activated else "sl_hit", "hit_tp": False, "hit_sl": not be_activated, "bars_held": b + 1}
            # Check TP hit
            if drop_pct[b] >= tp_pct:
                return {"pnl": tp_pct - fee, "status": "tp_hit", "hit_tp": True, "hit_sl": False, "bars_held": b + 1}
            # Check BE trigger
            if drop_pct[b] >= be_trigger and not be_activated:
                be_activated = True
                sl_active = 0.00  # Stop loss moved to entry price

        exit_pnl = (entry_price - closes[max_bars - 1]) / entry_price
        return {"pnl": exit_pnl - fee, "status": "timeout", "hit_tp": False, "hit_sl": False, "bars_held": max_bars}

    elif strategy_name == "partial_tp":
        # Exit 50% at TP1 (10%) and move remaining SL to BE. Exit remaining 50% at TP2 (20%).
        sl_pct = kwargs.get("sl_pct", 0.18)
        tp1_pct = kwargs.get("tp1_pct", 0.10)
        tp2_pct = kwargs.get("tp2_pct", 0.20)
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        tp1_hit = False
        tp2_hit = False
        sl_active = sl_pct
        accumulated_pnl = 0.0

        for b in range(max_bars):
            if not tp1_hit:
                if pump_pct[b] >= sl_active:
                    return {"pnl": -sl_pct - fee, "status": "sl_hit", "hit_tp": False, "hit_sl": True, "bars_held": b + 1}
                if drop_pct[b] >= tp1_pct:
                    tp1_hit = True
                    accumulated_pnl += 0.5 * tp1_pct
                    sl_active = 0.0  # move SL to entry for the remaining 50%
            else:
                # Remaining 50% in play
                if pump_pct[b] >= sl_active:
                    # Half was stopped at BE (0%)
                    total_pnl = accumulated_pnl + 0.5 * 0.0 - fee
                    return {"pnl": total_pnl, "status": "partial_tp1_then_be", "hit_tp": True, "hit_sl": False, "bars_held": b + 1}
                if drop_pct[b] >= tp2_pct:
                    total_pnl = accumulated_pnl + 0.5 * tp2_pct - fee
                    return {"pnl": total_pnl, "status": "full_tp_hit", "hit_tp": True, "hit_sl": False, "bars_held": b + 1}

        # Timeout exit
        if tp1_hit:
            exit_pnl_remaining = 0.5 * ((entry_price - closes[max_bars - 1]) / entry_price)
            total_pnl = accumulated_pnl + exit_pnl_remaining - fee
            return {"pnl": total_pnl, "status": "partial_tp1_timeout", "hit_tp": True, "hit_sl": False, "bars_held": max_bars}
        else:
            exit_pnl = (entry_price - closes[max_bars - 1]) / entry_price - fee
            return {"pnl": exit_pnl, "status": "timeout", "hit_tp": False, "hit_sl": False, "bars_held": max_bars}

    elif strategy_name == "scale_in_dca":
        # Enter 50% at market (entry_price). Place 50% limit order at entry_price * (1 + dca_pump_pct).
        # SL is placed at entry_price * (1 + sl_pct). Target is avg_entry * (1 - tp_pct).
        dca_pump_pct = kwargs.get("dca_pump_pct", 0.10)
        sl_pct = kwargs.get("sl_pct", 0.22)  # 22% from initial entry
        tp_pct = kwargs.get("tp_pct", 0.20)
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        dca_filled = False
        dca_fill_bar = -1
        p_dca = entry_price * (1.0 + dca_pump_pct)

        for b in range(max_bars):
            curr_high = highs[b]
            curr_low = lows[b]

            if not dca_filled:
                # Check if SL hit on 50% position
                if curr_high >= entry_price * (1.0 + sl_pct):
                    return {"pnl": 0.5 * (-sl_pct) - fee, "status": "sl_hit_half", "hit_tp": False, "hit_sl": True, "bars_held": b + 1}
                # Check if TP hit on 50% position
                if curr_low <= entry_price * (1.0 - tp_pct):
                    return {"pnl": 0.5 * tp_pct - fee, "status": "tp_hit_half", "hit_tp": True, "hit_sl": False, "bars_held": b + 1}
                # Check if DCA limit order filled
                if curr_high >= p_dca:
                    dca_filled = True
                    dca_fill_bar = b
                    avg_entry = (entry_price + p_dca) / 2.0
                    target_price_full = avg_entry * (1.0 - tp_pct)
                    sl_price_full = entry_price * (1.0 + sl_pct)
            else:
                # Full 100% position active
                if curr_high >= sl_price_full:
                    loss_pct = (sl_price_full - avg_entry) / avg_entry
                    return {"pnl": -loss_pct - fee, "status": "sl_hit_full", "hit_tp": False, "hit_sl": True, "bars_held": b + 1}
                if curr_low <= target_price_full:
                    return {"pnl": tp_pct - fee, "status": "tp_hit_full", "hit_tp": True, "hit_sl": False, "bars_held": b + 1}

        # Timeout exit at 72h
        if dca_filled:
            final_pnl = (avg_entry - closes[max_bars - 1]) / avg_entry - fee
            return {"pnl": final_pnl, "status": "timeout_full", "hit_tp": False, "hit_sl": False, "bars_held": max_bars}
        else:
            final_pnl = 0.5 * ((entry_price - closes[max_bars - 1]) / entry_price) - fee
            return {"pnl": final_pnl, "status": "timeout_half", "hit_tp": False, "hit_sl": False, "bars_held": max_bars}

    elif strategy_name == "time_stop_24h":
        # SL = 18%, TP = 20%. If after 288 bars (24h) price hasn't dropped >= 5%, close trade immediately!
        sl_pct = kwargs.get("sl_pct", 0.18)
        tp_pct = kwargs.get("tp_pct", 0.20)
        time_limit_bars = min(288, n_bars)  # 24 hours
        max_bars = min(kwargs.get("max_bars", 864), n_bars)

        for b in range(max_bars):
            if pump_pct[b] >= sl_pct:
                return {"pnl": -sl_pct - fee, "status": "sl_hit", "hit_tp": False, "hit_sl": True, "bars_held": b + 1}
            if drop_pct[b] >= tp_pct:
                return {"pnl": tp_pct - fee, "status": "tp_hit", "hit_tp": True, "hit_sl": False, "bars_held": b + 1}

            # Check 24h milestone
            if b == time_limit_bars - 1:
                # If price hasn't dropped by at least 5% (i.e. drop_pct < 0.05)
                max_drop_so_far = drop_pct[:time_limit_bars].max()
                if max_drop_so_far < 0.05:
                    exit_pnl = (entry_price - closes[b]) / entry_price - fee
                    return {"pnl": exit_pnl, "status": "time_stop_closed", "hit_tp": False, "hit_sl": False, "bars_held": b + 1}

        exit_pnl = (entry_price - closes[max_bars - 1]) / entry_price - fee
        return {"pnl": exit_pnl, "status": "timeout_72h", "hit_tp": False, "hit_sl": False, "bars_held": max_bars}

    raise ValueError(f"Unknown strategy: {strategy_name}")


def run_full_optimization_backtest():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parquet_path = Path("artifacts/lowcap_dual_features_cache.parquet")
    db_path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    output_path = Path("artifacts/backtest_optimal_solutions_report.json")

    LOGGER.info("Loading parquet features cache...")
    df = pd.read_parquet(parquet_path)
    symbols = df["symbol"].unique().tolist()
    LOGGER.info("Loaded %d candidate feature rows across %d symbols", len(df), len(symbols))

    LOGGER.info("Loading 5m klines from duckdb into RAM for instant slicing...")
    t0 = time.time()
    conn = duckdb.connect(str(db_path), read_only=True)
    conn.register("sym_df", pd.DataFrame({"symbol": symbols}))
    klines_df = conn.execute("""
        SELECT k.symbol, k.close_time, k.open, k.high, k.low, k.close
        FROM klines_5m k
        INNER JOIN sym_df s ON k.symbol = s.symbol
        WHERE k.close_time >= '2025-08-25' AND k.close_time <= '2026-09-01'
        ORDER BY k.symbol, k.close_time ASC
    """).fetchdf()
    conn.close()
    LOGGER.info("Loaded %d klines in %.2fs. Building symbol numpy indices...", len(klines_df), time.time() - t0)

    sym_klines = {}
    for sym, g in klines_df.groupby("symbol"):
        sym_klines[sym] = {
            "times": g["close_time"].dt.tz_convert("UTC").values,
            "high": g["high"].values.astype(np.float32),
            "low": g["low"].values.astype(np.float32),
            "close": g["close"].values.astype(np.float32),
        }
    del klines_df

    # 10-fold Walk-Forward
    oos_cache_path = Path("artifacts/oos_optimal_signals.parquet")
    if oos_cache_path.exists():
        LOGGER.info("Loading cached OOS signals from %s...", oos_cache_path)
        oos = pd.read_parquet(oos_cache_path)
    else:
        as_of = df["feature_time"].max()
        window_start = df["feature_time"].min()
        evaluation_end = as_of - pd.Timedelta(hours=72)
        embargo = timedelta(hours=48)
        boundaries = _fold_boundaries(window_start, evaluation_end, n_folds=10, warmup_days=60)
        top_quantile = 0.98
        seed = 42

        LOGGER.info("Starting 10-fold Walk-Forward modeling & signal generation...")
        oos_records = []

    for fold_idx, b in enumerate(boundaries, start=1):
        t_start = b["test_start"]
        t_end = b["test_end"]
        train_end = t_start - embargo

        train = df[(df["feature_time"] >= window_start) & (df["feature_time"] < train_end)].copy()
        test = df[(df["feature_time"] >= t_start) & (df["feature_time"] < t_end)].copy()

        if len(train) < 200 or len(test) == 0:
            continue

        n_fit = max(1, int(len(train) * 0.8))
        fit = train.iloc[:n_fit]
        cal = train.iloc[n_fit:]
        y_fit = fit["label_20_10"].astype(int).to_numpy()
        y_cal = cal["label_20_10"].astype(int).to_numpy()

        imputer = SimpleImputer(strategy="median", add_indicator=True)
        x_fit = imputer.fit_transform(fit[FEATURE_COLS])
        x_cal = imputer.transform(cal[FEATURE_COLS]) if len(cal) else np.empty((0, x_fit.shape[1]))
        x_test = imputer.transform(test[FEATURE_COLS])

        # V1: LogisticRegression
        lr = LogisticRegression(max_iter=1000, random_state=seed + fold_idx)
        lr.fit(x_fit, y_fit)
        lr_test_prob = lr.predict_proba(x_test)[:, 1]

        # V2: LightGBM + Calibration
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

        def top_k(probs: np.ndarray) -> np.ndarray:
            k = max(1, int(round(len(probs) * (1.0 - top_quantile))))
            k = min(k, len(probs))
            order = np.argsort(-probs, kind="mergesort")
            mask = np.zeros(len(probs), dtype=bool)
            mask[order[:k]] = True
            return mask

        v1_sig = top_k(lr_test_prob)
        v2_sig = top_k(lgb_test_prob)

        test_out = test[["symbol", "feature_time", "close"]].copy()
        test_out["fold"] = fold_idx
        test_out["V1_sig"] = v1_sig
        test_out["V2_sig"] = v2_sig
        oos_records.append(test_out)

    oos = pd.concat(oos_records, ignore_index=True)
    oos.to_parquet(oos_cache_path)
    LOGGER.info("Saved OOS signals to %s", oos_cache_path)

    LOGGER.info("OOS test records: %d rows. V1 signals: %d, V2 signals: %d", len(oos), oos["V1_sig"].sum(), oos["V2_sig"].sum())

    # Strategy suite to benchmark
    strategies = {
        "0. Baseline cũ (TP 20%, SL 10%, 12h)": {
            "name": "baseline_sl10",
            "kwargs": {},
        },
        "1. Nới SL 15% (TP 20%, 72h)": {
            "name": "fixed_sl",
            "kwargs": {"sl_pct": 0.15, "tp_pct": 0.20, "max_bars": 864},
        },
        "2. Nới SL 18% (TP 20%, 72h)": {
            "name": "fixed_sl",
            "kwargs": {"sl_pct": 0.18, "tp_pct": 0.20, "max_bars": 864},
        },
        "3. Nới SL 20% (R:R 1:1, 72h)": {
            "name": "fixed_sl",
            "kwargs": {"sl_pct": 0.20, "tp_pct": 0.20, "max_bars": 864},
        },
        "4. Nới SL 25% (R:R 0.8:1, 72h)": {
            "name": "fixed_sl",
            "kwargs": {"sl_pct": 0.25, "tp_pct": 0.20, "max_bars": 864},
        },
        "5. Dời SL về Breakeven (SL 18% ban đầu, dời BE khi -10%, TP 20%)": {
            "name": "breakeven_trail",
            "kwargs": {"sl_pct": 0.18, "tp_pct": 0.20, "be_trigger": 0.10, "max_bars": 864},
        },
        "6. Chốt lời từng phần (TP1 -10% chốt 50% & dời BE, TP2 -20%, SL 18%)": {
            "name": "partial_tp",
            "kwargs": {"sl_pct": 0.18, "tp1_pct": 0.10, "tp2_pct": 0.20, "max_bars": 864},
        },
        "7. Vào lệnh 2 bước / DCA đón râu (50% market, 50% limit +10%, SL +20%, TP -20%)": {
            "name": "scale_in_dca",
            "kwargs": {"dca_pump_pct": 0.10, "sl_pct": 0.20, "tp_pct": 0.20, "max_bars": 864},
        },
        "8. Time-Stop Invalidation (SL 18%, TP 20%, thoát ở 24h nếu không giảm >= 5%)": {
            "name": "time_stop_24h",
            "kwargs": {"sl_pct": 0.18, "tp_pct": 0.20, "max_bars": 864},
        },
    }

    results = {}

    for strat_label, strat_cfg in strategies.items():
        LOGGER.info("Evaluating: %s...", strat_label)
        strat_results = {}

        for model_key, sig_col in [("V1", "V1_sig"), ("V2", "V2_sig")]:
            sig_df = oos[oos[sig_col] == True].copy()
            pnls = []
            tp_hits = 0
            sl_hits = 0
            be_exits = 0
            bars_held_list = []

            for _, row in sig_df.iterrows():
                sym = row["symbol"]
                f_time = row["feature_time"]
                entry_p = float(row["close"])

                if sym not in sym_klines:
                    continue
                kdata = sym_klines[sym]
                times = kdata["times"]
                f_time_val = pd.to_datetime(f_time).tz_convert("UTC").to_datetime64()
                idx = np.searchsorted(times, f_time_val)
                # Next 864 bars
                fwd_high = kdata["high"][idx + 1 : idx + 865]
                fwd_low = kdata["low"][idx + 1 : idx + 865]
                fwd_close = kdata["close"][idx + 1 : idx + 865]

                sim = simulate_trade_strategy(
                    strat_cfg["name"],
                    fwd_high,
                    fwd_low,
                    fwd_close,
                    entry_p,
                    fee=0.0020,
                    **strat_cfg["kwargs"],
                )
                pnls.append(sim["pnl"])
                if sim["hit_tp"]:
                    tp_hits += 1
                if sim["hit_sl"]:
                    sl_hits += 1
                if sim.get("status") in ("be_exit", "partial_tp1_then_be"):
                    be_exits += 1
                bars_held_list.append(sim["bars_held"])

            pnls_arr = np.array(pnls, dtype=float)
            n_trades = len(pnls_arr)
            wins = pnls_arr[pnls_arr > 0]
            losses = pnls_arr[pnls_arr < 0]
            gross_win = float(wins.sum()) if len(wins) else 0.0
            gross_loss = float(-losses.sum()) if len(losses) else 0.0001
            pf = gross_win / gross_loss if gross_loss > 0 else 999.0
            ev = float(pnls_arr.mean()) if n_trades else 0.0
            wr = float((pnls_arr > 0).mean()) if n_trades else 0.0

            strat_results[model_key] = {
                "n_signals": n_trades,
                "win_rate_pct": round(wr * 100, 2),
                "tp_hit_rate_pct": round(tp_hits / n_trades * 100, 2) if n_trades else 0.0,
                "sl_hit_rate_pct": round(sl_hits / n_trades * 100, 2) if n_trades else 0.0,
                "be_exit_rate_pct": round(be_exits / n_trades * 100, 2) if n_trades else 0.0,
                "profit_factor": round(pf, 2),
                "expected_return_pct": round(ev * 100, 2),
                "total_pnl_pct": round(float(pnls_arr.sum()) * 100, 2),
                "avg_hours_held": round(float(np.mean(bars_held_list)) * 5.0 / 60.0, 1) if bars_held_list else 0.0,
            }

        results[strat_label] = strat_results

    # Save to json
    report = {
        "artifact": "optimal_solutions_backtest_report",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_evaluated_signals": len(oos[oos["V2_sig"] == True]),
        "strategies": results,
    }
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("Report saved to %s", output_path)

    # Print summary table
    print("\n" + "=" * 100)
    print("        BẢNG TỔNG HỢP BACKTEST CÁC HƯỚNG GIẢI PHÁP TỐI ƯU (V1 vs V2)")
    print("=" * 100)
    print(f"{'Chiến lược thử nghiệm':<42} | {'Model':<4} | {'Win Rate':<9} | {'TP Hit%':<8} | {'SL Hit%':<8} | {'Profit Factor':<14} | {'Lợi nhuận EV':<12}")
    print("-" * 100)
    for strat_label, s_res in results.items():
        v1 = s_res["V1"]
        v2 = s_res["V2"]
        print(f"{strat_label:<42} | V1   | {v1['win_rate_pct']:>7}% | {v1['tp_hit_rate_pct']:>6}% | {v1['sl_hit_rate_pct']:>6}% | {v1['profit_factor']:>13} | {v1['expected_return_pct']:>10}%")
        print(f"{'':<42} | V2   | {v2['win_rate_pct']:>7}% | {v2['tp_hit_rate_pct']:>6}% | {v2['sl_hit_rate_pct']:>6}% | {v2['profit_factor']:>13} | {v2['expected_return_pct']:>10}%")
        print("-" * 100)


if __name__ == "__main__":
    run_full_optimization_backtest()
