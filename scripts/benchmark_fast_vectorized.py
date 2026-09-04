"""Fast Vectorized Historical Benchmark: V1 (Heuristic) vs V2 (2-Tier Climax).

Performs batch evaluation across historical snapshots with complete 24h forward outcomes.
The target and stop-loss levels are configurable so risk profiles can be compared
without changing the production scanner.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from typing import Any

from dao_vang.config.settings import AppSettings
from dao_vang.data.storage.duckdb import open_read_only_connection
from dao_vang.scoring.btc_context import classify_btc
from dao_vang.scoring.distribution_scorer import compute_distribution_score
from dao_vang.scoring.two_tier_scorer import compute_two_tier_distribution_score


def run_fast_benchmark(
    db_path: str,
    limit: int = 1500,
    target_drop: float = 0.08,
    stop_loss: float = 0.04,
) -> dict[str, Any]:
    if target_drop <= 0 or stop_loss <= 0:
        raise ValueError("target_drop and stop_loss must be positive")

    conn = open_read_only_connection(db_path, prefer_snapshot=True)
    settings = AppSettings()
    btc_dummy = classify_btc(0.0, 0.0, 0.0, settings.scoring)

    print(f"1. Loading top {limit} volatile snapshots with mature 24h forward history...")
    query = """
    WITH max_k AS (
        SELECT MAX(close_time) as max_time FROM kline
    )
    SELECT f.*, k.close as entry_price
    FROM feature_results f
    JOIN kline k ON k.symbol = f.symbol AND k.close_time = f.feature_time AND k.interval = '5m'
    CROSS JOIN max_k
    WHERE f.price_ret_24h >= 0.10
      AND f.feature_time <= max_k.max_time - INTERVAL 24 HOUR
    ORDER BY f.feature_time DESC
    LIMIT ?
    """
    df_snaps = conn.execute(query, [limit]).df()
    print(f"Loaded {len(df_snaps)} candidate snapshots.")

    if len(df_snaps) == 0:
        return {"error": "No mature snapshots found."}

    symbols = df_snaps["symbol"].unique().tolist()
    min_time = df_snaps["feature_time"].min()
    max_time = df_snaps["feature_time"].max()

    print(f"2. Batch loading forward klines for {len(symbols)} symbols ({min_time} to {max_time})...")
    klines_df = conn.execute(
        """
        SELECT symbol, close_time, open, high, low, close
        FROM kline
        WHERE interval = '5m' 
          AND close_time >= ?
        ORDER BY symbol, close_time ASC
        """,
        [min_time],
    ).df()
    print(f"Loaded {len(klines_df)} klines into memory.")

    # Index klines by symbol as sorted lists
    klines_by_sym: dict[str, list[dict[str, Any]]] = {}
    for sym, group in klines_df.groupby("symbol"):
        klines_by_sym[str(sym)] = group.sort_values("close_time").to_dict("records")

    v1_trades: list[dict[str, Any]] = []
    v2_trades: list[dict[str, Any]] = []
    evaluated = 0

    print("3. Scoring & evaluating forward path trajectories...")
    for _, row in df_snaps.iterrows():
        sym = str(row["symbol"])
        feat_time = row["feature_time"]
        entry_p = float(row.get("entry_price") or 0.0)
        pump_pct = float(row.get("price_ret_24h") or 0.0)

        if entry_p <= 0 or sym not in klines_by_sym:
            continue

        feat_dict = {col: row[col] for col in df_snaps.columns if row[col] is not None}

        # Calculate scores
        v1_score = compute_distribution_score(
            symbol=sym,
            features=feat_dict,
            btc=btc_dummy,
            config=settings.scoring,
            pump_pct=pump_pct,
        )

        v2_score = compute_two_tier_distribution_score(
            symbol=sym,
            features=feat_dict,
            btc=btc_dummy,
            config=settings.scoring,
            pump_pct=pump_pct,
        )

        # Filter forward 24h klines
        sym_klines = klines_by_sym[sym]
        forward: list[dict[str, Any]] = []
        for k in sym_klines:
            ct = k["close_time"]
            if ct > feat_time:
                diff_sec = (ct - feat_time).total_seconds()
                if diff_sec <= 86400:
                    forward.append(k)
                elif diff_sec > 86400:
                    break

        if len(forward) < 24:  # At least 2h of forward data
            continue

        evaluated += 1

        # Evaluate path
        max_high = max(float(k["high"]) for k in forward)
        min_low = min(float(k["low"]) for k in forward)

        mae = max(0.0, (max_high - entry_p) / entry_p)
        mfe = max(0.0, (entry_p - min_low) / entry_p)

        hit_stop_loss = False
        hit_target = False
        hit_tp3 = False
        hit_tp4 = False
        hit_tp6 = False
        hit_tp8 = False
        hit_tp12 = False

        lead_min = 20.0
        peak_found = False

        for k_idx, k in enumerate(forward):
            k_high = float(k["high"])
            k_low = float(k["low"])

            if not peak_found and abs(k_high - max_high) / entry_p < 0.002:
                lead_min = (k_idx + 1) * 5.0
                peak_found = True

            if (k_high - entry_p) / entry_p >= stop_loss:
                hit_stop_loss = True
                break

            drop = (entry_p - k_low) / entry_p
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
            if drop >= target_drop:
                hit_target = True
                break

        if hit_stop_loss:
            net_pnl = -stop_loss
        elif hit_target:
            net_pnl = target_drop
        else:
            final_c = float(forward[-1]["close"])
            net_pnl = (entry_p - final_c) / entry_p

        trade_data = {
            "symbol": sym,
            "pump_pct": pump_pct,
            "mae": mae,
            "mfe": mfe,
            "hit_stop_loss": hit_stop_loss,
            "hit_target": hit_target,
            "hit_sl_4pct": hit_stop_loss,
            "hit_tp_3pct": hit_tp3,
            "hit_tp_4pct": hit_tp4,
            "hit_tp_6pct": hit_tp6,
            "hit_tp_8pct": hit_tp8,
            "hit_tp_12pct": hit_tp12,
            "lead_time_min": lead_min,
            "net_pnl_pct": net_pnl,
        }

        # V1 signals when recommendation == 'SHORT_CANDIDATE' (or score >= 60)
        if v1_score.recommendation == "SHORT_CANDIDATE" or v1_score.total_score >= 55.0:
            v1_trades.append(trade_data)

        # V2 signals strictly when BOTH Tier 1 is ARMED and Tier 2 is FIRED (recommendation == 'SHORT_CANDIDATE')
        if v2_score.recommendation == "SHORT_CANDIDATE":
            v2_trades.append(trade_data)

    conn.close()

    def aggregate(trades: list[dict[str, Any]], name: str) -> dict[str, Any]:
        n = len(trades)
        if n == 0:
            return {"engine_name": name, "total_signals": 0}

        tp3 = sum(1 for t in trades if t["hit_tp_3pct"])
        tp4 = sum(1 for t in trades if t["hit_tp_4pct"])
        tp6 = sum(1 for t in trades if t["hit_tp_6pct"])
        tp8 = sum(1 for t in trades if t["hit_tp_8pct"])
        tp12 = sum(1 for t in trades if t["hit_tp_12pct"])
        target_hits = sum(1 for t in trades if t["hit_target"])
        stop_losses = sum(1 for t in trades if t["hit_stop_loss"])

        maes = sorted([t["mae"] for t in trades])
        mfes = sorted([t["mfe"] for t in trades])
        leads = [t["lead_time_min"] for t in trades]
        pnls = [t["net_pnl_pct"] for t in trades]

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
        avg_pnl = sum(pnls) / n

        pump_extreme = [t for t in trades if t["pump_pct"] >= 0.40]
        pump_moderate = [t for t in trades if 0.20 <= t["pump_pct"] < 0.40]
        pump_mild = [t for t in trades if t["pump_pct"] < 0.20]

        def r_wr(group: list[dict[str, Any]]) -> float:
            if not group:
                return 0.0
            return sum(1 for t in group if t["hit_target"]) / len(group) * 100.0

        return {
            "engine_name": name,
            "total_signals": n,
            "target_drop_pct": round(target_drop * 100, 1),
            "stop_loss_pct": round(stop_loss * 100, 1),
            "target_hit_rate_pct": round(target_hits / n * 100, 1),
            "stop_loss_rate_pct": round(stop_losses / n * 100, 1),
            "hit_rate_tp1_4pct": round(tp4 / n * 100, 1),
            "hit_rate_tp_3pct": round(tp3 / n * 100, 1),
            "hit_rate_tp_6pct": round(tp6 / n * 100, 1),
            "hit_rate_tp2_8pct": round(tp8 / n * 100, 1),
            "hit_rate_tp3_12pct": round(tp12 / n * 100, 1),
            "sl_breach_rate": round(stop_losses / n * 100, 1),
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
            "regime_extreme_win_rate": round(r_wr(pump_extreme), 1),
            "regime_extreme_count": len(pump_extreme),
            "regime_moderate_win_rate": round(r_wr(pump_moderate), 1),
            "regime_moderate_count": len(pump_moderate),
            "regime_mild_win_rate": round(r_wr(pump_mild), 1),
            "regime_mild_count": len(pump_mild),
        }

    return {
        "sample_evaluated": evaluated,
        "target_drop_pct": round(target_drop * 100, 1),
        "stop_loss_pct": round(stop_loss * 100, 1),
        "v1_metrics": aggregate(v1_trades, "V1 Heuristic Composite (Classic)"),
        "v2_metrics": aggregate(v2_trades, "V2 2-Tier Climax Engine (Pro)"),
    }


if __name__ == "__main__":
    db_file = sys.argv[1] if len(sys.argv) > 1 else "data_live/live.duckdb"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
    target_drop = float(sys.argv[3]) if len(sys.argv) > 3 else 0.08
    stop_loss = float(sys.argv[4]) if len(sys.argv) > 4 else 0.04
    res = run_fast_benchmark(db_file, limit, target_drop, stop_loss)
    print("\n" + "=" * 75)
    print("      DETAILED STATISTICAL BENCHMARK REPORT: V1 vs V2 (REAL DATA)")
    print("=" * 75)
    print(json.dumps(res, indent=2))
