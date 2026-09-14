"""Evaluate an already-locked 48h timing policy on August live snapshots.

Entry prices and the complete target/stop path come from ``live.kline``.
``quant_master`` is queried only as a coverage audit and never supplies labels.
The model and policy lock are immutable inputs created before this evaluator.
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import joblib
import numpy as np
import pandas as pd
from forward48_timing_backtest import (
    BREAK_EVEN_PRECISION,
    COST,
    HORIZON_HOURS,
    STOP,
    TARGET,
    TimingPolicy,
    _episode_ids,
    _predict_calibrated,
    _sha256_file,
    _sql_path,
    select_signals,
)

from dao_vang.experiments.train_distribution_v2 import SERVING_FEATURE_COLS


def _default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    raise TypeError(type(value).__name__)


def _wilson(successes: int, trials: int) -> tuple[float, float]:
    if trials <= 0:
        return 0.0, 0.0
    z = 1.959963984540054
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials)
    return (centre - radius) / denominator, (centre + radius) / denominator


def _load_features(
    live_db: Path, start: str, end: str
) -> tuple[pd.DataFrame, dict[str, Any]]:
    conn = duckdb.connect()
    conn.execute(f"ATTACH '{_sql_path(live_db)}' AS live (READ_ONLY)")
    feature_sql = ",\n                   ".join(
        f"f.{column}" for column in SERVING_FEATURE_COLS
    )
    try:
        candidates = conn.execute(
            """
            SELECT COUNT(*)
            FROM live.main.feature_results
            WHERE feature_time >= CAST(? AS TIMESTAMPTZ)
              AND feature_time < CAST(? AS TIMESTAMPTZ)
              AND price_ret_24h >= 0.15
              AND EXTRACT(MINUTE FROM feature_time)=4
            """,
            [start, end],
        ).fetchone()[0]
        frame = conn.execute(
            f"""
            SELECT f.feature_time, f.symbol, k.close AS entry_price,
                   {feature_sql}
            FROM live.main.feature_results f
            INNER JOIN live.main.kline k
              ON k.symbol=f.symbol AND k.close_time=f.feature_time
            WHERE f.feature_time >= CAST(? AS TIMESTAMPTZ)
              AND f.feature_time < CAST(? AS TIMESTAMPTZ)
              AND f.price_ret_24h >= 0.15
              AND EXTRACT(MINUTE FROM f.feature_time)=4
            ORDER BY f.feature_time, f.symbol
            """,
            [start, end],
        ).fetchdf()
        kline_max = conn.execute(
            "SELECT MAX(close_time), COUNT(DISTINCT symbol) FROM live.main.kline"
        ).fetchone()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    return frame, {
        "hourly_feature_candidates": int(candidates),
        "exact_live_kline_entry_matches": len(frame),
        "entry_match_ratio": len(frame) / candidates if candidates else 0.0,
        "live_kline_max_time": kline_max[0],
        "live_kline_symbols": int(kline_max[1]),
    }


def _master_audit(
    features: pd.DataFrame, market_db: Path, output_dir: Path
) -> dict[str, Any]:
    path = output_dir / "forward48_timing_master_audit_candidates.parquet"
    features[["symbol", "feature_time"]].to_parquet(path, index=False)
    conn = duckdb.connect()
    conn.execute(f"ATTACH '{_sql_path(market_db)}' AS market (READ_ONLY)")
    try:
        exact = conn.execute(
            f"""
            SELECT COUNT(*)
            FROM read_parquet('{_sql_path(path)}') c
            INNER JOIN market.main.klines_5m k
              ON k.symbol=c.symbol AND k.close_time=c.feature_time
            """
        ).fetchone()[0]
        max_time, symbols = conn.execute(
            "SELECT MAX(close_time), COUNT(DISTINCT symbol) FROM market.main.klines_5m"
        ).fetchone()
    finally:
        conn.close()
    return {
        "role": "coverage_audit_only_not_used_for_labels",
        "exact_matches": int(exact),
        "candidate_rows": len(features),
        "exact_match_ratio": exact / len(features) if len(features) else 0.0,
        "market_max_time": max_time,
        "market_symbols": int(symbols),
    }


def _load_outcomes(
    features: pd.DataFrame, live_db: Path, output_dir: Path, min_future_bars: int
) -> pd.DataFrame:
    path = output_dir / "forward48_timing_live_candidates_for_outcomes.parquet"
    features[["symbol", "feature_time", "entry_price"]].to_parquet(path, index=False)
    conn = duckdb.connect()
    conn.execute(f"ATTACH '{_sql_path(live_db)}' AS live (READ_ONLY)")
    try:
        frame = conn.execute(
            f"""
            WITH candidates AS (
              SELECT * FROM read_parquet('{_sql_path(path)}')
            ), outcomes AS (
              SELECT c.symbol, c.feature_time,
                     COUNT(f.close_time) AS future_bars,
                     MAX(f.close_time) AS last_future_time,
                     MIN(f.close_time) FILTER (
                       WHERE f.low <= c.entry_price * {1.0 - TARGET}
                     ) AS target_time,
                     MIN(f.close_time) FILTER (
                       WHERE f.high >= c.entry_price * {1.0 + STOP}
                     ) AS stop_time
              FROM candidates c
              LEFT JOIN live.main.kline f
                ON f.symbol=c.symbol
               AND f.close_time>c.feature_time
               AND f.close_time<=c.feature_time+INTERVAL '{HORIZON_HOURS}' HOUR
              GROUP BY c.symbol, c.feature_time
            )
            SELECT *,
                   CASE
                     WHEN future_bars < {min_future_bars}
                       OR last_future_time < feature_time+INTERVAL '{HORIZON_HOURS}' HOUR-INTERVAL '5' MINUTE
                       THEN 'incomplete_future'
                     WHEN target_time IS NOT NULL AND target_time=stop_time
                       THEN 'ambiguous_same_bar'
                     ELSE NULL
                   END exclusion_reason,
                   CASE
                     WHEN future_bars < {min_future_bars}
                       OR last_future_time < feature_time+INTERVAL '{HORIZON_HOURS}' HOUR-INTERVAL '5' MINUTE
                       THEN NULL
                     WHEN target_time IS NOT NULL AND target_time=stop_time THEN NULL
                     WHEN target_time IS NOT NULL AND (stop_time IS NULL OR target_time<stop_time) THEN 1
                     ELSE 0
                   END label_value
            FROM outcomes
            ORDER BY feature_time, symbol
            """
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    return frame


def _result(all_rows: pd.DataFrame, keys: pd.DataFrame) -> dict[str, Any]:
    signals = all_rows.merge(keys, on=["symbol", "feature_time"], how="inner")
    evaluable = signals[signals["label_value"].notna()]
    n = len(evaluable)
    tp = int(evaluable["label_value"].eq(1).sum())
    precision = tp / n if n else 0.0
    lower, upper = _wilson(tp, n)
    positive_episodes = set(
        all_rows.loc[all_rows["label_value"].eq(1), "episode_id"].astype(str)
    )
    signaled_episodes = set(signals["episode_id"].astype(str))
    caught = set(
        evaluable.loc[evaluable["label_value"].eq(1), "episode_id"].astype(str)
    )
    positive_signaled = positive_episodes & signaled_episodes
    return {
        "signals": len(signals),
        "evaluable_signals": n,
        "excluded_signals": len(signals) - n,
        "true_positives": tp,
        "false_positives": n - tp,
        "precision": precision,
        "precision_wilson95_lower": lower,
        "precision_wilson95_upper": upper,
        "positive_episodes": len(positive_episodes),
        "caught_positive_episodes": len(caught),
        "episode_recall": len(caught) / len(positive_episodes) if positive_episodes else 0.0,
        "conservative_ev": (
            precision * TARGET - (1.0 - precision) * STOP - COST if n else None
        ),
        "no_coverage": {
            "all_candidate_episodes": int(all_rows["episode_id"].nunique()),
            "episodes_with_entry1": len(signaled_episodes),
            "positive_episodes_without_entry1": len(positive_episodes - signaled_episodes),
            "positive_episodes_with_entry1_but_bad_timing": len(positive_signaled - caught),
        },
    }


def _promotion_gate(result: dict[str, Any]) -> dict[str, Any]:
    lower_pass = result["precision_wilson95_lower"] > BREAK_EVEN_PRECISION
    passed = (
        result["evaluable_signals"] >= 100
        and result["precision"] >= 0.50
        and lower_pass
    )
    gate = {
        "required_new_independent_signals": 100,
        "minimum_precision": 0.50,
        "wilson_lower_above_break_even": lower_pass,
        "passed": passed,
    }
    assert not gate["passed"] or gate["wilson_lower_above_break_even"]
    return gate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lock-dir", type=Path, default=Path("artifacts/forward48_timing_20260913")
    )
    parser.add_argument("--live-db", type=Path, default=Path("data_live/live.duckdb"))
    parser.add_argument(
        "--market-db",
        type=Path,
        default=Path(r"D:\Quant-trading\data_lake\quant_master.duckdb"),
    )
    parser.add_argument("--start", default="2026-08-01T00:00:00+07:00")
    parser.add_argument("--end", default="2026-08-27T00:00:00+07:00")
    parser.add_argument("--min-future-bars", type=int, default=552)
    args = parser.parse_args()

    lock_path = args.lock_dir / "forward48_timing_lock.json"
    model_path = args.lock_dir / "forward48_timing_research_model.joblib"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected_model_hash = lock["model_sha256"]
    actual_model_hash = _sha256_file(model_path)
    if actual_model_hash != expected_model_hash:
        raise RuntimeError("research model hash no longer matches immutable lock")
    bundle = joblib.load(model_path)
    policy = TimingPolicy(**lock["selected_policy"])
    baseline_policy = TimingPolicy()

    # Score and lock Entry-1 keys before any outcome query.
    features, live_coverage = _load_features(args.live_db, args.start, args.end)
    raw, probability = _predict_calibrated(
        bundle["model"], bundle["calibrator"], features, list(SERVING_FEATURE_COLS)
    )
    features["raw_probability"] = raw
    features["probability"] = probability
    features["threshold"] = float(bundle["threshold"])
    features["episode_id"] = _episode_ids(features)
    keys = select_signals(features, policy)[["symbol", "feature_time"]].copy()
    baseline_keys = select_signals(features, baseline_policy)[
        ["symbol", "feature_time"]
    ].copy()
    signal_key_path = args.lock_dir / "forward48_timing_august_locked_signal_keys.csv"
    keys.to_csv(signal_key_path, index=False)
    signal_key_hash = _sha256_file(signal_key_path)

    outcomes = _load_outcomes(
        features, args.live_db, args.lock_dir, args.min_future_bars
    )
    evaluated = features.merge(outcomes, on=["symbol", "feature_time"], how="left")
    result = _result(evaluated, keys)
    baseline_result = _result(evaluated, baseline_keys)
    selected_rows = evaluated.merge(keys, on=["symbol", "feature_time"], how="inner")
    selected_rows.to_csv(
        args.lock_dir / "forward48_timing_august_signals_live.csv", index=False
    )

    weekly: list[dict[str, Any]] = []
    week_series = evaluated["feature_time"].dt.strftime("%G-W%V")
    for week in sorted(week_series.unique()):
        part = evaluated.loc[week_series.eq(week)]
        part_keys = keys.merge(
            part[["symbol", "feature_time"]],
            on=["symbol", "feature_time"],
            how="inner",
        )
        weekly.append({"week": week, **_result(part, part_keys)})

    resolved = evaluated["label_value"].notna()
    report = {
        "artifact": "forward48_timing_locked_august_live_kline",
        "generated_at": datetime.now(timezone.utc),
        "status": "research_only_not_live",
        "immutable_inputs": {
            "policy_lock_sha256": lock["lock_sha256"],
            "model_sha256": actual_model_hash,
            "signal_keys_sha256_before_outcome_load": signal_key_hash,
            "selected_policy": lock["selected_policy"],
            "baseline_policy": baseline_policy.__dict__,
            "threshold": bundle["threshold"],
            "august_labels_used_for_model_or_policy_selection": False,
        },
        "contract": {
            "target_drawdown": TARGET,
            "max_adverse_excursion": STOP,
            "horizon_hours": HORIZON_HOURS,
            "round_trip_cost": COST,
            "break_even_precision": BREAK_EVEN_PRECISION,
            "same_bar": "exclude_ambiguous",
            "one_entry1_per_episode": True,
            "cooldown_hours": 24,
        },
        "coverage": {
            **live_coverage,
            "resolved_candidates": int(resolved.sum()),
            "resolved_ratio_of_exact_matches": float(resolved.mean()),
            "incomplete_future": int(
                evaluated["exclusion_reason"].eq("incomplete_future").sum()
            ),
            "ambiguous_same_bar": int(
                evaluated["exclusion_reason"].eq("ambiguous_same_bar").sum()
            ),
            "resolved_symbols": int(evaluated.loc[resolved, "symbol"].nunique()),
            "forward_start": evaluated["feature_time"].min(),
            "forward_end": evaluated["feature_time"].max(),
        },
        "quant_master_audit": _master_audit(features, args.market_db, args.lock_dir),
        "august": result,
        "august_pre_registered_baseline": baseline_result,
        "per_week": weekly,
        "promotion": _promotion_gate(result),
        "live_configuration_changed": False,
    }
    output = args.lock_dir / "forward48_timing_locked_forward_report.json"
    output.write_text(json.dumps(report, indent=2, default=_default), encoding="utf-8")
    print(json.dumps({"report": output, **report}, indent=2, default=_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
