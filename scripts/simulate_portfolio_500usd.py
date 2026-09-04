"""Realistic $500 Account Portfolio Simulation for dao_vang models.

Parameters:
- Capital: $500.00
- Leverage: 5x
- Margin per order: $5.00 (Position Notional: $25.00)
- Trading fee: 20 bps round-trip ($0.05 per trade)
- Max concurrent positions: 15
- Max orders per day: 15
- Max positions per coin: 1 (with 120-minute cooldown)

Evaluates:
- Setup 1: TP 8% / SL 4%
- Setup 2: TP 20% / SL 10%
Across:
- LogisticRegression
- LightGBM (Top-ranked)
- LightGBM (High-Confidence Filter: Calibrated Top 2%)
- Baseline (Random top signals)
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

LOGGER = logging.getLogger("dao_vang.portfolio_sim")

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


def generate_oos_predictions(
    df: pd.DataFrame,
    label_col: str,
    n_folds: int = 10,
    embargo_hours: int = 48,
    seed: int = 42,
) -> pd.DataFrame:
    """Run walk-forward CV to generate out-of-sample predictions for all test rows."""
    window_start = pd.Timestamp(df["feature_time"].min()).to_pydatetime()
    evaluation_end = pd.Timestamp(df["feature_time"].max()).to_pydatetime()
    boundaries = _fold_boundaries(window_start, evaluation_end, n_folds=n_folds, warmup_days=60)
    embargo = timedelta(hours=embargo_hours)

    oos_parts = []
    for fold_idx, b in enumerate(boundaries, start=1):
        t0 = time.time()
        t_start = b["test_start"]
        t_end = b["test_end"]
        train_end = t_start - embargo

        train = df[(df["feature_time"] >= window_start) & (df["feature_time"] < train_end)].copy()
        test = df[(df["feature_time"] >= t_start) & (df["feature_time"] < t_end)].copy()

        if len(train) < 100 or len(test) == 0 or len(np.unique(train[label_col])) < 2:
            continue

        n_fit = max(1, int(len(train) * 0.8))
        fit = train.iloc[:n_fit]
        cal = train.iloc[n_fit:]
        y_fit = fit[label_col].astype(int).to_numpy()
        y_cal = cal[label_col].astype(int).to_numpy()

        imputer = SimpleImputer(strategy="median", add_indicator=True)
        x_fit = imputer.fit_transform(fit[FEATURE_COLS])
        x_cal = imputer.transform(cal[FEATURE_COLS]) if len(cal) else np.empty((0, x_fit.shape[1]))
        x_test = imputer.transform(test[FEATURE_COLS])

        # 1. Logistic Regression
        lr = LogisticRegression(max_iter=500, random_state=seed + fold_idx)
        lr.fit(x_fit, y_fit)
        lr_preds = lr.predict_proba(x_test)[:, 1]

        # 2. LightGBM + Isotonic
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
            n_jobs=8,
        )
        lgb_model.fit(x_fit, y_fit)
        lgb_cal_raw = lgb_model.predict_proba(x_cal)[:, 1] if len(cal) else np.array([], dtype=float)
        lgb_test_raw = lgb_model.predict_proba(x_test)[:, 1]

        if len(lgb_cal_raw) >= 50 and len(np.unique(y_cal)) >= 2:
            calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            calibrator.fit(lgb_cal_raw, y_cal)
            lgb_cal = np.asarray(calibrator.predict(lgb_cal_raw), dtype=float)
            lgb_preds = np.asarray(calibrator.predict(lgb_test_raw), dtype=float)
        else:
            lgb_cal = lgb_cal_raw
            lgb_preds = lgb_test_raw

        lgb_p98_thresh = float(np.quantile(lgb_cal, 0.98)) if len(lgb_cal) else 0.5
        lgb_p99_thresh = float(np.quantile(lgb_cal, 0.99)) if len(lgb_cal) else 0.6
        lr_p98_thresh = float(np.quantile(lr.predict_proba(x_cal)[:, 1], 0.98)) if len(cal) else 0.5
        # Baseline: uniform random
        rng = np.random.default_rng(seed + fold_idx * 100)
        base_preds = rng.uniform(0.0, 1.0, size=len(test))

        test_out = test.copy()
        test_out["prob_lr"] = lr_preds
        test_out["prob_lgb"] = lgb_preds
        test_out["prob_base"] = base_preds
        test_out["lgb_p98_thresh"] = lgb_p98_thresh
        test_out["lgb_p99_thresh"] = lgb_p99_thresh
        test_out["lr_p98_thresh"] = lr_p98_thresh
        oos_parts.append(test_out)
        LOGGER.info("Fold %d/%d OOS predictions generated in %.1fs (%d test rows)", fold_idx, len(boundaries), time.time() - t0, len(test))

    return pd.concat(oos_parts, ignore_index=True)


def simulate_account(
    df: pd.DataFrame,
    prob_col: str,
    target_profit: float,
    max_loss: float,
    label_col: str,
    threshold_filter: float | None = None,
    use_quantile_col: str | None = None,
    initial_equity: float = 500.0,
    margin_per_order: float = 5.0,
    leverage: float = 5.0,
    fee_bps: float = 20.0,
    max_concurrent_positions: int = 15,
    max_orders_per_day: int = 15,
    cooldown_minutes: int = 120,
) -> dict[str, Any]:
    """Chronological bar-by-bar portfolio execution simulation."""
    position_notional = margin_per_order * leverage  # $25.00
    fee_per_trade = position_notional * (fee_bps / 10_000.0)  # $0.05 round-trip

    # Sort strictly chronologically
    df_sorted = df.sort_values("feature_time").reset_index(drop=True)

    equity = initial_equity
    peak_equity = initial_equity
    max_drawdown_dollar = 0.0
    max_drawdown_pct = 0.0

    daily_history = []
    trade_log = []

    # State trackers
    open_positions: dict[str, datetime] = {}  # symbol -> exit_time
    last_symbol_entry: dict[str, datetime] = {}  # symbol -> entry_time
    current_day: datetime | None = None
    orders_today = 0

    # Group candidate signals by feature_time (each 5m bar)
    grouped = df_sorted.groupby("feature_time", sort=False)

    for timestamp, bar_df in grouped:
        t_stamp = pd.Timestamp(timestamp)
        day_date = t_stamp.floor("D")

        if current_day is None or day_date != current_day:
            if current_day is not None:
                daily_history.append({"date": current_day.isoformat(), "equity": equity})
            current_day = day_date
            orders_today = 0

        # 1. Close matured positions
        expired_symbols = [sym for sym, exit_t in open_positions.items() if t_stamp >= exit_t]
        for sym in expired_symbols:
            del open_positions[sym]

        # 2. Check available capacity
        if orders_today >= max_orders_per_day or len(open_positions) >= max_concurrent_positions:
            continue

        # 3. Filter candidates at this timestamp
        candidates = bar_df.copy()
        if threshold_filter is not None:
            candidates = candidates[candidates[prob_col] >= threshold_filter]
        elif use_quantile_col is not None:
            candidates = candidates[candidates[prob_col] >= candidates[use_quantile_col]]

        # Exclude coins currently in position or on cooldown
        valid_indices = []
        for idx, row in candidates.iterrows():
            sym = row["symbol"]
            if sym in open_positions:
                continue
            if sym in last_symbol_entry:
                if (t_stamp - last_symbol_entry[sym]).total_seconds() < cooldown_minutes * 60:
                    continue
            valid_indices.append(idx)

        if not valid_indices:
            continue

        valid_candidates = candidates.loc[valid_indices].sort_values(prob_col, ascending=False)

        # 4. Open positions up to daily & concurrent limits
        slots_available = min(
            max_orders_per_day - orders_today,
            max_concurrent_positions - len(open_positions),
        )
        to_open = valid_candidates.head(slots_available)

        for _, order in to_open.iterrows():
            sym = order["symbol"]
            entry_price = float(order["close"])
            future_high = float(order["future_max_high"])
            close_horizon = float(order["close_at_horizon"])
            label_hit = int(order[label_col])

            # Position duration = 12 hours (144 bars of 5m)
            exit_time = t_stamp + timedelta(hours=12)
            open_positions[sym] = exit_time
            last_symbol_entry[sym] = t_stamp
            orders_today += 1

            # Determine PnL outcome
            if label_hit == 1:
                # Reached TP without touching SL
                gross_return_pct = target_profit
                hit_type = "TP"
            elif future_high >= entry_price * (1.0 + max_loss):
                # Hit SL
                gross_return_pct = -max_loss
                hit_type = "SL"
            else:
                # Exit at horizon close
                gross_return_pct = entry_price / max(close_horizon, 1e-12) - 1.0
                hit_type = "CLOSE"

            dollar_pnl = position_notional * gross_return_pct - fee_per_trade
            equity += dollar_pnl

            if equity > peak_equity:
                peak_equity = equity
            dd_dollar = peak_equity - equity
            dd_pct = dd_dollar / peak_equity if peak_equity > 0 else 0.0

            if dd_dollar > max_drawdown_dollar:
                max_drawdown_dollar = dd_dollar
            if dd_pct > max_drawdown_pct:
                max_drawdown_pct = dd_pct

            trade_log.append({
                "symbol": sym,
                "entry_time": t_stamp.isoformat(),
                "exit_time": exit_time.isoformat(),
                "hit_type": hit_type,
                "gross_return_pct": gross_return_pct,
                "dollar_pnl": dollar_pnl,
                "equity_after": equity,
            })

    if current_day is not None:
        daily_history.append({"date": current_day.isoformat(), "equity": equity})

    # Summary statistics
    total_trades = len(trade_log)
    if total_trades == 0:
        return {
            "initial_equity": initial_equity,
            "final_equity": initial_equity,
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
        }

    pnls = [t["dollar_pnl"] for t in trade_log]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    win_rate = len(wins) / total_trades if total_trades else 0.0

    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if len(wins) else 0.0)

    # Daily Sharpe
    df_daily = pd.DataFrame(daily_history)
    if len(df_daily) > 1:
        df_daily["daily_return"] = df_daily["equity"].pct_change().fillna(0.0)
        daily_mean = df_daily["daily_return"].mean()
        daily_std = df_daily["daily_return"].std(ddof=1)
        sharpe = math.sqrt(365.0) * daily_mean / daily_std if daily_std > 0 else 0.0
    else:
        sharpe = 0.0

    tp_hits = sum(1 for t in trade_log if t["hit_type"] == "TP")
    sl_hits = sum(1 for t in trade_log if t["hit_type"] == "SL")
    close_exits = sum(1 for t in trade_log if t["hit_type"] == "CLOSE")

    return {
        "initial_equity": initial_equity,
        "final_equity": round(equity, 2),
        "total_pnl_dollar": round(equity - initial_equity, 2),
        "total_return_pct": round((equity - initial_equity) / initial_equity * 100, 2),
        "total_trades": total_trades,
        "trades_per_day_avg": round(total_trades / max(len(daily_history), 1), 2),
        "win_rate_pct": round(win_rate * 100, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "sharpe_annualized": round(sharpe, 2),
        "peak_equity": round(peak_equity, 2),
        "max_drawdown_dollar": round(max_drawdown_dollar, 2),
        "max_drawdown_pct": round(max_drawdown_pct * 100, 2),
        "breakdown": {
            "tp_hits": tp_hits,
            "tp_hit_rate_pct": round(tp_hits / total_trades * 100, 2),
            "sl_hits": sl_hits,
            "sl_hit_rate_pct": round(sl_hits / total_trades * 100, 2),
            "close_exits": close_exits,
            "close_exit_rate_pct": round(close_exits / total_trades * 100, 2),
        },
    }


def run_all_simulations(cache_path: Path, output_path: Path) -> dict[str, Any]:
    t0 = time.time()
    LOGGER.info("Loading cached feature data from %s...", cache_path)
    df = pd.read_parquet(cache_path)
    df["feature_time"] = pd.to_datetime(df["feature_time"], utc=True)
    df["funding_rate_raw"] = df["funding_rate_raw"].fillna(0.0)
    df[FEATURE_COLS] = df[FEATURE_COLS].replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["label_8_4", "label_20_10"]).copy()
    df["label_8_4"] = df["label_8_4"].astype(int)
    df["label_20_10"] = df["label_20_10"].astype(int)
    df = df.sort_values(["feature_time", "symbol"]).reset_index(drop=True)
    LOGGER.info("Loaded %d clean rows across %d coins", len(df), df["symbol"].nunique())

    LOGGER.info("Generating OOS predictions for Setup 1 (TP 8% / SL 4%)...")
    oos_8_4 = generate_oos_predictions(df, label_col="label_8_4", n_folds=10, embargo_hours=48)

    LOGGER.info("Generating OOS predictions for Setup 2 (TP 20% / SL 10%)...")
    oos_20_10 = generate_oos_predictions(df, label_col="label_20_10", n_folds=10, embargo_hours=48)

    results: dict[str, Any] = {
        "simulation_parameters": {
            "account_size_usd": 500.0,
            "leverage": 5.0,
            "margin_per_order_usd": 5.0,
            "position_notional_usd": 25.0,
            "trading_fee_bps": 20.0,
            "max_concurrent_positions": 15,
            "max_orders_per_day": 15,
            "cooldown_minutes": 120,
            "tested_period": f"{oos_8_4['feature_time'].min().isoformat()[:10]} -> {oos_8_4['feature_time'].max().isoformat()[:10]}",
        },
        "setup_8_4": {},
        "setup_20_10": {},
    }

    # Setup 1: TP 8% / SL 4%
    LOGGER.info("Simulating Setup 1 (TP 8% / SL 4%)...")
    results["setup_8_4"]["LogisticRegression_p98"] = simulate_account(
        oos_8_4, prob_col="prob_lr", target_profit=0.08, max_loss=0.04, label_col="label_8_4",
        use_quantile_col="lr_p98_thresh"
    )
    results["setup_8_4"]["LightGBM_p98"] = simulate_account(
        oos_8_4, prob_col="prob_lgb", target_profit=0.08, max_loss=0.04, label_col="label_8_4",
        use_quantile_col="lgb_p98_thresh"
    )
    results["setup_8_4"]["LightGBM_p99_HighConfidence"] = simulate_account(
        oos_8_4, prob_col="prob_lgb", target_profit=0.08, max_loss=0.04, label_col="label_8_4",
        use_quantile_col="lgb_p99_thresh"
    )
    results["setup_8_4"]["Baseline_Random_p98"] = simulate_account(
        oos_8_4, prob_col="prob_base", target_profit=0.08, max_loss=0.04, label_col="label_8_4",
        threshold_filter=0.98
    )

    # Setup 2: TP 20% / SL 10%
    LOGGER.info("Simulating Setup 2 (TP 20% / SL 10%)...")
    results["setup_20_10"]["LogisticRegression_p98"] = simulate_account(
        oos_20_10, prob_col="prob_lr", target_profit=0.20, max_loss=0.10, label_col="label_20_10",
        use_quantile_col="lr_p98_thresh"
    )
    results["setup_20_10"]["LightGBM_p98"] = simulate_account(
        oos_20_10, prob_col="prob_lgb", target_profit=0.20, max_loss=0.10, label_col="label_20_10",
        use_quantile_col="lgb_p98_thresh"
    )
    results["setup_20_10"]["LightGBM_p99_HighConfidence"] = simulate_account(
        oos_20_10, prob_col="prob_lgb", target_profit=0.20, max_loss=0.10, label_col="label_20_10",
        use_quantile_col="lgb_p99_thresh"
    )
    results["setup_20_10"]["Baseline_Random_p98"] = simulate_account(
        oos_20_10, prob_col="prob_base", target_profit=0.20, max_loss=0.10, label_col="label_20_10",
        threshold_filter=0.98
    )

    results["runtime_seconds"] = round(time.time() - t0, 1)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("Simulation report written to %s in %.1fs", output_path, results["runtime_seconds"])
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, default=Path("artifacts/lowcap_dual_features_cache.parquet"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/portfolio_sim_500usd.json"))
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    run_all_simulations(cache_path=args.cache, output_path=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
