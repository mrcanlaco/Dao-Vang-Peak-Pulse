"""Detailed Statistical Benchmark: Engine V1 (Heuristic) vs Engine V2 (2-Tier Climax).

Performs a rigorous historical path evaluation across DuckDB klines and feature snapshots.
Calculates TP hit rates (-3%, -4%, -6%, -8%, -12%), SL breach rate (+4%),
MAE/MFE distributions, lead time to peak, and regime breakdown.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import duckdb
from dao_vang.config.settings import AppSettings
from dao_vang.data.storage.duckdb import open_read_only_connection
from dao_vang.scoring.btc_context import BtcContext, classify_btc
from dao_vang.scoring.distribution_scorer import compute_distribution_score
from dao_vang.scoring.two_tier_scorer import compute_two_tier_distribution_score


@dataclass
class TradeOutcome:
    symbol: str
    feature_time: datetime
    entry_price: float
    score_v1: float
    score_v2: float
    v2_htf_state: str
    v2_ltf_state: str
    pump_pct: float
    mae: float  # Max upward move before major drop
    mfe: float  # Max downward drop
    hit_sl_4pct: bool
    hit_tp_3pct: bool
    hit_tp_4pct: bool
    hit_tp_6pct: bool
    hit_tp_8pct: bool
    hit_tp_12pct: bool
    lead_time_min: float
    net_pnl_pct: float  # PnL with SL +4% & TP2 -8% rule


def run_benchmark(db_path: str, sample_limit: int = 1500) -> dict[str, Any]:
    print(f"Connecting to DuckDB: {db_path} via open_read_only_connection...")
    conn = open_read_only_connection(db_path, prefer_snapshot=True)
    settings = AppSettings()

    # Query volatile snapshots with significant 24h price action
    print(f"Querying top {sample_limit} volatile snapshots with feature results...")
    query = """
    SELECT f.*, k.close as current_price
    FROM feature_results f
    JOIN kline k ON k.symbol = f.symbol AND k.close_time = f.feature_time AND k.interval = '5m'
    WHERE f.price_ret_24h >= 0.12
    ORDER BY f.feature_time DESC
    LIMIT ?
    """
    df = conn.execute(query, [sample_limit]).df()
    print(f"Loaded {len(df)} candidate snapshots.")

    btc_dummy = classify_btc(0.0, 0.0, 0.0, settings.scoring)

    v1_trades: list[TradeOutcome] = []
    v2_trades: list[TradeOutcome] = []
    all_evaluated = 0

    for idx, row in df.iterrows():
        symbol = str(row["symbol"])
        feature_time = row["feature_time"]
        entry_price = float(row.get("current_price") or row.get("close") or 0.0)
        pump_pct = float(row.get("price_ret_24h") or 0.0)

        if entry_price <= 0:
            continue

        feat_dict = {col: row[col] for col in df.columns if row[col] is not None}

        # Calculate scores
        v1_score = compute_distribution_score(
            symbol=symbol,
            features=feat_dict,
            btc=btc_dummy,
            config=settings.scoring,
            pump_pct=pump_pct,
        )

        v2_score = compute_two_tier_distribution_score(
            symbol=symbol,
            features=feat_dict,
            btc=btc_dummy,
            config=settings.scoring,
            pump_pct=pump_pct,
        )

        # Get forward 24h klines (up to 288 5m candles)
        try:
            klines = conn.execute(
                """
                SELECT open_time, open, high, low, close
                FROM kline
                WHERE symbol = ? AND close_time > ? AND close_time <= ? + INTERVAL 24 HOUR
                ORDER BY close_time ASC
                """,
                [symbol, feature_time, feature_time],
            ).fetchall()
        except Exception:
            klines = []

        if len(klines) < 12:  # Need at least 1 hour of forward data
            continue

        all_evaluated += 1

        # Track path trajectory
        max_high = max(float(k[2]) for k in klines)
        min_low = min(float(k[3]) for k in klines)

        mae = max(0.0, (max_high - entry_price) / entry_price)
        mfe = max(0.0, (entry_price - min_low) / entry_price)

        # Path sequence evaluation
        hit_sl = False
        hit_tp3 = False
        hit_tp4 = False
        hit_tp6 = False
        hit_tp8 = False
        hit_tp12 = False

        lead_min = 0.0
        peak_found = False

        for k_idx, k in enumerate(klines):
            k_high = float(k[2])
            k_low = float(k[3])

            # Check if this candle was the highest point (peak)
            if not peak_found and abs(k_high - max_high) / entry_price < 0.002:
                lead_min = (k_idx + 1) * 5.0
                peak_found = True

            # Check SL breach (+4%)
            if (k_high - entry_price) / entry_price >= 0.04:
                hit_sl = True
                break

            # Check TP milestones before SL
            drop = (entry_price - k_low) / entry_price
            if drop >= 0.03:
                hit_tp3 = True
            if drop >= 0.04:
                hit_tp4 = True
            if drop >= 0.06:
                hit_tp6 = True
            if drop >= 0.08:
                hit_tp8 = True
            if drop >= 0.12:
                hit_tp12 = True

        # PnL Calculation (SL = -4.0%, TP2 = +8.0%, TP1 = +4.0%, or exit at 24h close)
        if hit_sl:
            net_pnl = -0.04
        elif hit_tp8:
            net_pnl = +0.08
        elif hit_tp4:
            net_pnl = +0.04
        else:
            final_close = float(klines[-1][4])
            net_pnl = (entry_price - final_close) / entry_price

        outcome = TradeOutcome(
            symbol=symbol,
            feature_time=feature_time,
            entry_price=entry_price,
            score_v1=v1_score.total_score,
            score_v2=v2_score.total_score,
            v2_htf_state=v2_score.htf_state,
            v2_ltf_state=v2_score.ltf_state,
            pump_pct=pump_pct,
            mae=mae,
            mfe=mfe,
            hit_sl_4pct=hit_sl,
            hit_tp_3pct=hit_tp3,
            hit_tp_4pct=hit_tp4,
            hit_tp_6pct=hit_tp6,
            hit_tp_8pct=hit_tp8,
            hit_tp_12pct=hit_tp12,
            lead_time_min=lead_min if peak_found else 20.0,
            net_pnl_pct=net_pnl,
        )

        if v1_score.total_score >= 50.0:
            v1_trades.append(outcome)

        if v2_score.total_score >= 50.0:
            v2_trades.append(outcome)

    conn.close()

    return {
        "sample_evaluated": all_evaluated,
        "v1_metrics": _compute_detailed_metrics(v1_trades, "V1 Heuristic Composite"),
        "v2_metrics": _compute_detailed_metrics(v2_trades, "V2 2-Tier Climax Engine"),
        "v1_trades": v1_trades,
        "v2_trades": v2_trades,
    }


def _compute_detailed_metrics(trades: list[TradeOutcome], name: str) -> dict[str, Any]:
    n = len(trades)
    if n == 0:
        return {"name": name, "count": 0}

    tp3 = sum(1 for t in trades if t.hit_tp_3pct)
    tp4 = sum(1 for t in trades if t.hit_tp_4pct)
    tp6 = sum(1 for t in trades if t.hit_tp_6pct)
    tp8 = sum(1 for t in trades if t.hit_tp_8pct)
    tp12 = sum(1 for t in trades if t.hit_tp_12pct)
    sl = sum(1 for t in trades if t.hit_sl_4pct)

    maes = sorted([t.mae for t in trades])
    mfes = sorted([t.mfe for t in trades])
    leads = [t.lead_time_min for t in trades]
    pnls = [t.net_pnl_pct for t in trades]

    avg_mae = sum(maes) / n
    avg_mfe = sum(mfes) / n
    p50_mae = maes[n // 2]
    p90_mae = maes[int(n * 0.9)]
    p50_mfe = mfes[n // 2]
    p90_mfe = mfes[int(n * 0.9)]

    wins = [p for p in pnls if p > 0]
    losses = [abs(p) for p in pnls if p < 0]
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = sum(losses) if losses else 0.0001
    profit_factor = gross_profit / gross_loss
    win_rate = len(wins) / n
    avg_pnl = sum(pnls) / n

    # Regime breakdown
    pump_extreme = [t for t in trades if t.pump_pct >= 0.40]
    pump_moderate = [t for t in trades if 0.20 <= t.pump_pct < 0.40]
    pump_mild = [t for t in trades if t.pump_pct < 0.20]

    def regime_win_rate(group: list[TradeOutcome]) -> float:
        if not group:
            return 0.0
        return sum(1 for t in group if t.hit_tp_4pct) / len(group) * 100.0

    return {
        "engine_name": name,
        "total_signals": n,
        "win_rate_tp1_4pct": round(tp4 / n * 100, 1),
        "hit_rate_tp_3pct": round(tp3 / n * 100, 1),
        "hit_rate_tp_6pct": round(tp6 / n * 100, 1),
        "hit_rate_tp_8pct": round(tp8 / n * 100, 1),
        "hit_rate_tp_12pct": round(tp12 / n * 100, 1),
        "sl_breach_rate": round(sl / n * 100, 1),
        "avg_mae_pct": round(avg_mae * 100, 2),
        "p50_mae_pct": round(p50_mae * 100, 2),
        "p90_mae_pct": round(p90_mae * 100, 2),
        "avg_mfe_pct": round(avg_mfe * 100, 2),
        "p50_mfe_pct": round(p50_mfe * 100, 2),
        "p90_mfe_pct": round(p90_mfe * 100, 2),
        "avg_rr_ratio": round(avg_mfe / (avg_mae if avg_mae > 0.005 else 0.005), 2),
        "profit_factor": round(profit_factor, 2),
        "expected_pnl_per_trade_pct": round(avg_pnl * 100, 2),
        "mean_lead_time_min": round(sum(leads) / n, 1),
        "regime_extreme_win_rate": round(regime_win_rate(pump_extreme), 1),
        "regime_extreme_count": len(pump_extreme),
        "regime_moderate_win_rate": round(regime_win_rate(pump_moderate), 1),
        "regime_moderate_count": len(pump_moderate),
        "regime_mild_win_rate": round(regime_win_rate(pump_mild), 1),
        "regime_mild_count": len(pump_mild),
    }


if __name__ == "__main__":
    db_file = sys.argv[1] if len(sys.argv) > 1 else "data_live/live.duckdb"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    res = run_benchmark(db_file, limit)
    print("\n" + "=" * 70)
    print("           DETAILED HISTORICAL BENCHMARK REPORT: V1 vs V2")
    print("=" * 70)
    print(json.dumps({
        "sample_evaluated": res["sample_evaluated"],
        "v1_metrics": res["v1_metrics"],
        "v2_metrics": res["v2_metrics"],
    }, indent=2))
