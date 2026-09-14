"""Strict pre-August reconstruction for the 48h distribution timing policy.

The runner uses only labels whose 48-hour outcome was knowable before
2026-08-01 to fit/calibrate the model and select a causal Entry-1 state
machine.  It writes a policy/model hash before loading any August rows or
outcomes, then scores August snapshots and evaluates target-before-stop.

This is research-only.  It never updates serving configuration or a frozen
model directory.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb
import joblib
import numpy as np
import pandas as pd

from dao_vang.experiments.train_distribution_v2 import (
    SERVING_FEATURE_COLS,
    _build_estimator,
    _calibrator,
    _partition_history,
    _predict_calibrated,
)

TARGET = 0.20
STOP = 0.16
COST = 0.002
HORIZON_HOURS = 48
EMBARGO_HOURS = 48
EPISODE_GAP_HOURS = 6
COOLDOWN_HOURS = 24
BREAK_EVEN_PRECISION = (STOP + COST) / (TARGET + STOP)


@dataclass(frozen=True)
class TimingPolicy:
    min_peak_pump_24h: float = 0.15
    confirmations: int = 1
    min_episode_age_hours: int = 0
    min_probability_peak_drop: float = 0.0
    min_drawdown_from_high: float = 0.0
    require_ret5_nonpositive: bool = False
    probability_tolerance: float = 0.10


@dataclass(frozen=True)
class Config:
    historical_db: Path = Path("artifacts/universe_policy_v2_48h.duckdb")
    live_db: Path = Path("data_live/live.duckdb")
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    historical_table: str = "universe_policy_candidates_v2"
    output_root: Path = Path("artifacts")
    pre_august_cutoff: str = "2026-08-01T00:00:00+07:00"
    forward_end: str = "2026-08-27T00:00:00+07:00"
    min_future_bars: int = 552
    warmup_days: int = 90
    oos_folds: int = 4
    min_signals_total: int = 40
    min_signals_per_fold: int = 5
    random_state: int = 42


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


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _wilson(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials <= 0:
        return 0.0, 0.0
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials)
    return (centre - radius) / denominator, (centre + radius) / denominator


def _episode_ids(frame: pd.DataFrame, group_columns: Iterable[str] = ()) -> pd.Series:
    result = pd.Series(index=frame.index, dtype="object")
    groups = [*group_columns, "symbol"]
    for key, indices in frame.groupby(groups, sort=False).groups.items():
        ordered = frame.loc[indices].sort_values("feature_time")
        new_episode = ordered["feature_time"].diff().gt(
            pd.Timedelta(hours=EPISODE_GAP_HOURS)
        )
        local = new_episode.fillna(True).cumsum().astype(int)
        prefix = key if isinstance(key, tuple) else (key,)
        result.loc[ordered.index] = [
            ":".join([*(str(item) for item in prefix), str(number)])
            for number in local
        ]
    return result


def _boundaries(frame: pd.DataFrame, warmup_days: int, folds: int) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    unique_times = pd.Series(frame["feature_time"].drop_duplicates().sort_values())
    start = pd.Timestamp(unique_times.iloc[0])
    end = pd.Timestamp(unique_times.iloc[-1]) + pd.Timedelta(microseconds=1)
    first_test = start + pd.Timedelta(days=warmup_days)
    step = (end - first_test) / folds
    return [(first_test + step * i, first_test + step * (i + 1)) for i in range(folds)]


def load_historical(config: Config) -> pd.DataFrame:
    cutoff = pd.Timestamp(config.pre_august_cutoff)
    latest_knowable_signal = cutoff - pd.Timedelta(hours=HORIZON_HOURS)
    conn = duckdb.connect(str(config.historical_db), read_only=True)
    try:
        frame = conn.execute(
            f"""
            SELECT *
            FROM {config.historical_table}
            WHERE label_value IS NOT NULL
              AND price_ret_24h >= 0.15
              AND feature_time <= ?
            ORDER BY feature_time, symbol
            """,
            [latest_knowable_signal.to_pydatetime()],
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["label_value"] = frame["label_value"].astype("int8")
    return frame


def _select_model_threshold(
    labels: np.ndarray,
    probabilities: np.ndarray,
    identities: pd.DataFrame,
) -> tuple[float, dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for threshold in np.arange(0.05, 0.951, 0.01):
        raw = probabilities >= threshold
        keep = np.zeros(len(raw), dtype=bool)
        last: dict[str, pd.Timestamp] = {}
        for index, row in enumerate(identities.itertuples(index=False)):
            if not raw[index]:
                continue
            when = pd.Timestamp(row.feature_time)
            previous = last.get(str(row.symbol))
            if previous is None or when >= previous + pd.Timedelta(hours=COOLDOWN_HOURS):
                keep[index] = True
                last[str(row.symbol)] = when
        signals = int(keep.sum())
        if signals < 10:
            continue
        tp = int((keep & (labels == 1)).sum())
        precision = tp / signals
        recall = tp / int((labels == 1).sum()) if int((labels == 1).sum()) else 0.0
        candidates.append(
            {
                "threshold": float(threshold),
                "signals": signals,
                "true_positives": tp,
                "precision": precision,
                "recall": recall,
                "conservative_ev": precision * TARGET - (1.0 - precision) * STOP - COST,
            }
        )
    eligible = [item for item in candidates if item["recall"] >= 0.10]
    pool = eligible or candidates
    if not pool:
        return 0.95, {"threshold": 0.95, "signals": 0}
    winner = max(
        pool,
        key=lambda item: (
            item["conservative_ev"], item["precision"], item["recall"], item["threshold"]
        ),
    )
    return float(winner["threshold"]), winner


def build_historical_oos(frame: pd.DataFrame, config: Config) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    embargo = pd.Timedelta(hours=EMBARGO_HOURS)
    features = list(SERVING_FEATURE_COLS)
    records: list[pd.DataFrame] = []
    fold_reports: list[dict[str, Any]] = []
    for fold, (test_start, test_end) in enumerate(
        _boundaries(frame, config.warmup_days, config.oos_folds), start=1
    ):
        history = frame[frame["feature_time"] < test_start - embargo]
        fit, calibration, policy = _partition_history(history, embargo)
        test = frame[
            (frame["feature_time"] >= test_start) & (frame["feature_time"] < test_end)
        ]
        if any(len(part) < 50 or part["label_value"].nunique() < 2 for part in (fit, calibration, policy, test)):
            raise RuntimeError(f"fold {fold} lacks a usable fit/calibration/policy/test partition")
        model = _build_estimator("lightgbm", config.random_state + fold)
        model.fit(fit[features], fit["label_value"])
        calibrator = _calibrator(model, calibration, features, "isotonic")
        _, policy_probability = _predict_calibrated(model, calibrator, policy, features)
        threshold, threshold_report = _select_model_threshold(
            policy["label_value"].to_numpy(),
            policy_probability,
            policy[["symbol", "feature_time"]],
        )
        raw, probability = _predict_calibrated(model, calibrator, test, features)
        record = test[
            [
                "symbol", "feature_time", "label_value", "price_ret_24h",
                "price_ret_5m", "distance_from_high_24h",
            ]
        ].copy()
        record["raw_probability"] = raw
        record["probability"] = probability
        record["threshold"] = threshold
        record["fold"] = fold
        records.append(record)
        fold_reports.append(
            {
                "fold": fold,
                "test_start": test["feature_time"].min(),
                "test_end": test["feature_time"].max(),
                "test_rows": len(test),
                "test_positives": int(test["label_value"].sum()),
                "threshold": threshold,
                "threshold_policy_partition": threshold_report,
                "fit_end": fit["feature_time"].max(),
                "calibration_start": calibration["feature_time"].min(),
                "calibration_end": calibration["feature_time"].max(),
                "policy_start": policy["feature_time"].min(),
                "policy_end": policy["feature_time"].max(),
            }
        )
    result = pd.concat(records, ignore_index=True)
    result["episode_id"] = _episode_ids(result, ("fold",))
    return result, fold_reports


def policy_grid() -> list[TimingPolicy]:
    policies = [
        TimingPolicy(
            min_peak_pump_24h=pump,
            confirmations=confirmations,
            min_episode_age_hours=age,
            min_probability_peak_drop=peak_drop,
            min_drawdown_from_high=drawdown,
            require_ret5_nonpositive=reversal,
            probability_tolerance=0.10,
        )
        for pump, confirmations, age, peak_drop, drawdown, reversal in itertools.product(
            (0.15, 0.20, 0.30),
            (1, 2),
            (0, 2, 4),
            (0.0, 0.05),
            (0.0, 0.05),
            (False, True),
        )
    ]
    # Keep the explicit first-crossing comparator even if grid settings change.
    policies.append(TimingPolicy())
    unique = {json.dumps(asdict(item), sort_keys=True): item for item in policies}
    return list(unique.values())


def select_signals(frame: pd.DataFrame, policy: TimingPolicy) -> pd.DataFrame:
    selected: list[int] = []
    for _, episode in frame.groupby("episode_id", sort=False):
        episode = episode.sort_values("feature_time")
        episode_start = pd.Timestamp(episode["feature_time"].iloc[0])
        probability_peak = -np.inf
        pump_peak = -np.inf
        consecutive = 0
        confirmed = False
        armed = False
        previous_time: pd.Timestamp | None = None
        for index, row in episode.iterrows():
            when = pd.Timestamp(row["feature_time"])
            probability = float(row["probability"])
            threshold = float(row["threshold"])
            above = probability >= threshold
            contiguous = previous_time is None or when - previous_time <= pd.Timedelta(minutes=90)
            consecutive = consecutive + 1 if above and contiguous else int(above)
            confirmed = confirmed or consecutive >= policy.confirmations
            armed = armed or above
            if armed:
                probability_peak = max(probability_peak, probability)
                pump_peak = max(pump_peak, float(row["price_ret_24h"]))
            previous_time = when
            if not armed or not confirmed:
                continue
            episode_age = (when - episode_start).total_seconds() / 3600.0
            probability_ok = probability >= max(0.0, threshold - policy.probability_tolerance)
            probability_drop_ok = (
                probability_peak - probability >= policy.min_probability_peak_drop
            )
            drawdown_ok = float(row["distance_from_high_24h"]) <= -policy.min_drawdown_from_high
            reversal_ok = (
                not policy.require_ret5_nonpositive or float(row["price_ret_5m"]) <= 0.0
            )
            if (
                pump_peak >= policy.min_peak_pump_24h
                and episode_age >= policy.min_episode_age_hours
                and probability_ok
                and probability_drop_ok
                and drawdown_ok
                and reversal_ok
            ):
                selected.append(int(index))
                break
    signals = frame.loc[selected].sort_values(["feature_time", "symbol"]).copy()
    if signals.empty:
        return signals
    keep: list[int] = []
    last_by_symbol: dict[str, pd.Timestamp] = {}
    for index, row in signals.iterrows():
        symbol = str(row["symbol"])
        when = pd.Timestamp(row["feature_time"])
        previous = last_by_symbol.get(symbol)
        if previous is None or when >= previous + pd.Timedelta(hours=COOLDOWN_HOURS):
            keep.append(int(index))
            last_by_symbol[symbol] = when
    return signals.loc[keep]


def _metrics(frame: pd.DataFrame, policy: TimingPolicy) -> dict[str, Any]:
    signals = select_signals(frame, policy)
    evaluable = signals[signals["label_value"].notna()]
    signal_count = len(evaluable)
    tp = int(evaluable["label_value"].eq(1).sum())
    precision = tp / signal_count if signal_count else 0.0
    positive_episodes = set(frame.loc[frame["label_value"].eq(1), "episode_id"].astype(str))
    caught = set(evaluable.loc[evaluable["label_value"].eq(1), "episode_id"].astype(str))
    recall = len(caught & positive_episodes) / len(positive_episodes) if positive_episodes else 0.0
    lower, upper = _wilson(tp, signal_count)
    return {
        "signals": int(len(signals)),
        "evaluable_signals": int(signal_count),
        "excluded_signals": int(len(signals) - signal_count),
        "true_positives": tp,
        "false_positives": int(signal_count - tp),
        "precision": precision,
        "precision_wilson95_lower": lower,
        "precision_wilson95_upper": upper,
        "positive_episodes": len(positive_episodes),
        "caught_positive_episodes": len(caught & positive_episodes),
        "episode_recall": recall,
        "conservative_ev": (
            precision * TARGET - (1.0 - precision) * STOP - COST
            if signal_count else None
        ),
    }


def select_policy(oos: pd.DataFrame, config: Config) -> tuple[TimingPolicy, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    folds = sorted(int(value) for value in oos["fold"].unique())
    for policy in policy_grid():
        per_fold = [_metrics(oos[oos["fold"].eq(fold)], policy) for fold in folds]
        aggregate = _metrics(oos, policy)
        fold_evs = np.asarray([
            item["conservative_ev"] if item["conservative_ev"] is not None else -(STOP + COST)
            for item in per_fold
        ])
        fold_signals = [item["evaluable_signals"] for item in per_fold]
        eligible = (
            aggregate["evaluable_signals"] >= config.min_signals_total
            and min(fold_signals, default=0) >= config.min_signals_per_fold
        )
        robust_score = float(fold_evs.mean() - 0.5 * fold_evs.std())
        rows.append(
            {
                "policy": json.dumps(asdict(policy), sort_keys=True),
                **aggregate,
                "eligible": eligible,
                "robust_score": robust_score,
                "mean_fold_ev": float(fold_evs.mean()),
                "worst_fold_ev": float(fold_evs.min()),
                "positive_ev_folds": int((fold_evs > 0).sum()),
                "fold_signals": json.dumps(fold_signals),
                "fold_precisions": json.dumps([item["precision"] for item in per_fold]),
                "fold_evs": json.dumps(fold_evs.tolist()),
            }
        )
    grid = pd.DataFrame(rows)
    eligible = grid[grid["eligible"]]
    if eligible.empty:
        raise RuntimeError("no timing policy meets historical coverage floors")
    winner_row = eligible.sort_values(
        ["robust_score", "precision_wilson95_lower", "episode_recall", "signals"],
        ascending=False,
    ).iloc[0]
    return TimingPolicy(**json.loads(winner_row["policy"])), grid


def fit_final_model(history: pd.DataFrame, config: Config) -> tuple[Any, Any, float, dict[str, Any]]:
    embargo = pd.Timedelta(hours=EMBARGO_HOURS)
    features = list(SERVING_FEATURE_COLS)
    fit, calibration, policy = _partition_history(history, embargo)
    model = _build_estimator("lightgbm", config.random_state + 1000)
    model.fit(fit[features], fit["label_value"])
    calibrator = _calibrator(model, calibration, features, "isotonic")
    _, probabilities = _predict_calibrated(model, calibrator, policy, features)
    threshold, threshold_report = _select_model_threshold(
        policy["label_value"].to_numpy(),
        probabilities,
        policy[["symbol", "feature_time"]],
    )
    report = {
        "fit_rows": len(fit),
        "fit_start": fit["feature_time"].min(),
        "fit_end": fit["feature_time"].max(),
        "calibration_rows": len(calibration),
        "calibration_start": calibration["feature_time"].min(),
        "calibration_end": calibration["feature_time"].max(),
        "policy_rows": len(policy),
        "policy_start": policy["feature_time"].min(),
        "policy_end": policy["feature_time"].max(),
        "threshold": threshold,
        "threshold_report": threshold_report,
    }
    return model, calibrator, threshold, report


def load_forward_features(config: Config) -> tuple[pd.DataFrame, dict[str, int]]:
    conn = duckdb.connect()
    conn.execute(f"ATTACH '{_sql_path(config.live_db)}' AS live (READ_ONLY)")
    conn.execute(f"ATTACH '{_sql_path(config.market_db)}' AS market (READ_ONLY)")
    feature_sql = ",\n                   ".join(f"f.{name}" for name in SERVING_FEATURE_COLS)
    try:
        total = conn.execute(
            """
            SELECT COUNT(*) FROM live.main.feature_results
            WHERE feature_time >= CAST(? AS TIMESTAMPTZ)
              AND feature_time < CAST(? AS TIMESTAMPTZ)
              AND price_ret_24h >= 0.15
              AND EXTRACT(MINUTE FROM feature_time)=4
            """,
            [config.pre_august_cutoff, config.forward_end],
        ).fetchone()[0]
        frame = conn.execute(
            f"""
            SELECT f.feature_time, f.symbol, k.close AS entry_price,
                   {feature_sql}
            FROM live.main.feature_results f
            INNER JOIN market.main.klines_5m k
              ON k.symbol=f.symbol AND k.close_time=f.feature_time
            WHERE f.feature_time >= CAST(? AS TIMESTAMPTZ)
              AND f.feature_time < CAST(? AS TIMESTAMPTZ)
              AND f.price_ret_24h >= 0.15
              AND EXTRACT(MINUTE FROM f.feature_time)=4
            ORDER BY f.feature_time, f.symbol
            """,
            [config.pre_august_cutoff, config.forward_end],
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    return frame, {"hourly_feature_candidates": int(total), "exact_entry_price_matches": len(frame)}


def load_forward_outcomes(candidates: pd.DataFrame, config: Config, output_dir: Path) -> pd.DataFrame:
    candidate_file = output_dir / "forward48_timing_candidates_for_outcomes.parquet"
    candidates[["symbol", "feature_time", "entry_price"]].to_parquet(candidate_file, index=False)
    conn = duckdb.connect()
    conn.execute(f"ATTACH '{_sql_path(config.market_db)}' AS market (READ_ONLY)")
    try:
        outcomes = conn.execute(
            f"""
            WITH candidates AS (
                SELECT * FROM read_parquet('{_sql_path(candidate_file)}')
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
                LEFT JOIN market.main.klines_5m f
                  ON f.symbol=c.symbol
                 AND f.close_time > c.feature_time
                 AND f.close_time <= c.feature_time + INTERVAL '{HORIZON_HOURS}' HOUR
                GROUP BY c.symbol, c.feature_time
            )
            SELECT *,
                   CASE
                     WHEN future_bars < {config.min_future_bars}
                       OR last_future_time < feature_time + INTERVAL '{HORIZON_HOURS}' HOUR - INTERVAL '5' MINUTE
                       THEN 'incomplete_future'
                     WHEN target_time IS NOT NULL AND target_time=stop_time
                       THEN 'ambiguous_same_bar'
                     ELSE NULL
                   END AS exclusion_reason,
                   CASE
                     WHEN future_bars < {config.min_future_bars}
                       OR last_future_time < feature_time + INTERVAL '{HORIZON_HOURS}' HOUR - INTERVAL '5' MINUTE
                       THEN NULL
                     WHEN target_time IS NOT NULL AND target_time=stop_time THEN NULL
                     WHEN target_time IS NOT NULL AND (stop_time IS NULL OR target_time<stop_time) THEN 1
                     ELSE 0
                   END AS label_value
            FROM outcomes
            ORDER BY feature_time, symbol
            """
        ).fetchdf()
    finally:
        conn.close()
    outcomes["feature_time"] = pd.to_datetime(outcomes["feature_time"], utc=True)
    return outcomes


def _weekly_metrics(frame: pd.DataFrame, policy: TimingPolicy) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for period, part in frame.groupby(frame["feature_time"].dt.to_period("W-MON"), sort=True):
        # Episodes were formed over the full forward period; weekly slicing only reports them.
        metrics = _metrics(part, policy)
        rows.append({"week": str(period), **metrics})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    config = Config()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or config.output_root / f"forward48_timing_{stamp}"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Phase 1: historical-only model OOS predictions and state-machine selection.
    history = load_historical(config)
    oos, fold_reports = build_historical_oos(history, config)
    selected_policy, grid = select_policy(oos, config)
    baseline_policy = TimingPolicy()
    grid.sort_values("robust_score", ascending=False).to_csv(
        output_dir / "forward48_timing_historical_grid.csv", index=False
    )
    oos.to_csv(output_dir / "forward48_timing_historical_oos.csv", index=False)
    model, calibrator, threshold, final_fit = fit_final_model(history, config)
    model_path = output_dir / "forward48_timing_research_model.joblib"
    joblib.dump(
        {
            "model": model,
            "calibrator": calibrator,
            "feature_columns": list(SERVING_FEATURE_COLS),
            "threshold": threshold,
            "trained_with_labels_available_before": config.pre_august_cutoff,
            "label_contract": "target -20% before +16% within 48h; cost 0.2%",
        },
        model_path,
    )
    lock_payload = {
        "artifact": "forward48_timing_pre_august_policy_lock",
        "research_only": True,
        "reconstruction_notice": "generated post-hoc, but selection is restricted to information knowable before August",
        "locked_at": datetime.now(timezone.utc),
        "information_cutoff": config.pre_august_cutoff,
        "latest_historical_signal": history["feature_time"].max(),
        "historical_rows": len(history),
        "historical_oos_rows": len(oos),
        "timing_variants_tested": len(grid),
        "selected_policy": asdict(selected_policy),
        "selected_historical_oos": _metrics(oos, selected_policy),
        "baseline_historical_oos": _metrics(oos, baseline_policy),
        "final_model": final_fit,
        "model_sha256": _sha256_file(model_path),
        "serving_features_sha256": hashlib.sha256(
            json.dumps(list(SERVING_FEATURE_COLS), separators=(",", ":")).encode()
        ).hexdigest(),
        "live_configuration_changed": False,
    }
    canonical = json.dumps(lock_payload, sort_keys=True, default=_json_default, separators=(",", ":"))
    lock_hash = hashlib.sha256(canonical.encode()).hexdigest()
    lock_payload["lock_sha256"] = lock_hash
    lock_path = output_dir / "forward48_timing_lock.json"
    lock_path.write_text(json.dumps(lock_payload, indent=2, default=_json_default), encoding="utf-8")

    # Phase 2 begins only after the historical policy/model lock exists on disk.
    forward, coverage = load_forward_features(config)
    raw_probability, probability = _predict_calibrated(
        model, calibrator, forward, list(SERVING_FEATURE_COLS)
    )
    forward["raw_probability"] = raw_probability
    forward["probability"] = probability
    forward["threshold"] = threshold
    forward["episode_id"] = _episode_ids(forward)
    locked_signal_keys = select_signals(forward, selected_policy)[["symbol", "feature_time"]].copy()
    baseline_signal_keys = select_signals(forward, baseline_policy)[["symbol", "feature_time"]].copy()

    # Outcome labels are the final input loaded, after signal selection is immutable.
    outcomes = load_forward_outcomes(forward, config, output_dir)
    evaluated = forward.merge(outcomes, on=["symbol", "feature_time"], how="left")
    locked = evaluated.merge(
        locked_signal_keys.assign(locked_signal=True),
        on=["symbol", "feature_time"], how="left",
    )
    baseline = evaluated.merge(
        baseline_signal_keys.assign(locked_signal=True),
        on=["symbol", "feature_time"], how="left",
    )
    locked["locked_signal"] = locked["locked_signal"].fillna(False).astype(bool)
    baseline["locked_signal"] = baseline["locked_signal"].fillna(False).astype(bool)

    # Reuse the state-machine metric function by masking non-selected episodes safely.
    # Exact selected rows are exported; headline results are computed directly from them.
    def selected_result(all_rows: pd.DataFrame, keys: pd.DataFrame) -> dict[str, Any]:
        signals = all_rows.merge(keys, on=["symbol", "feature_time"], how="inner")
        evaluable = signals[signals["label_value"].notna()]
        tp = int(evaluable["label_value"].eq(1).sum())
        n = len(evaluable)
        precision = tp / n if n else 0.0
        lower, upper = _wilson(tp, n)
        positive_episodes = set(all_rows.loc[all_rows["label_value"].eq(1), "episode_id"].astype(str))
        caught = set(evaluable.loc[evaluable["label_value"].eq(1), "episode_id"].astype(str))
        signaled_episodes = set(signals["episode_id"].astype(str))
        positive_signaled = positive_episodes & signaled_episodes
        result = {
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
            "conservative_ev": precision * TARGET - (1.0 - precision) * STOP - COST if n else None,
            "no_coverage": {
                "all_candidate_episodes": int(all_rows["episode_id"].nunique()),
                "episodes_with_entry1": len(signaled_episodes),
                "positive_episodes_without_entry1": len(positive_episodes - signaled_episodes),
                "positive_episodes_with_entry1_but_bad_timing": len(positive_signaled - caught),
            },
        }
        return result

    locked_result = selected_result(evaluated, locked_signal_keys)
    baseline_result = selected_result(evaluated, baseline_signal_keys)
    selected_rows = evaluated.merge(
        locked_signal_keys, on=["symbol", "feature_time"], how="inner"
    ).sort_values(["feature_time", "symbol"])
    selected_rows.to_csv(output_dir / "forward48_timing_august_signals.csv", index=False)

    weekly: list[dict[str, Any]] = []
    week_values = evaluated["feature_time"].dt.strftime("%G-W%V")
    for week in sorted(week_values.unique()):
        part = evaluated.loc[week_values.eq(week)]
        part_keys = locked_signal_keys.merge(
            part[["symbol", "feature_time"]], on=["symbol", "feature_time"], how="inner"
        )
        weekly.append({"week": week, **selected_result(part, part_keys)})

    report = {
        "artifact": "forward48_timing_august_reconstructed_oos",
        "generated_at": datetime.now(timezone.utc),
        "status": "research_only_not_live",
        "methodology": {
            "strict_information_cutoff": config.pre_august_cutoff,
            "latest_label_feature_time": history["feature_time"].max(),
            "latest_label_resolution_time": history["feature_time"].max() + pd.Timedelta(hours=HORIZON_HOURS),
            "timing_selected_on": "four fold-specific calibrated historical OOS streams only",
            "august_labels_used_for_selection": False,
            "policy_lock_written_before_august_loaded": True,
            "policy_lock_sha256": lock_hash,
            "one_entry1_per_episode": True,
            "episode_gap_hours": EPISODE_GAP_HOURS,
            "symbol_cooldown_hours": COOLDOWN_HOURS,
            "same_bar_policy": "exclude_ambiguous",
            "post_hoc_reconstruction": True,
        },
        "contract": {
            "target_drawdown": TARGET,
            "max_adverse_excursion": STOP,
            "horizon_hours": HORIZON_HOURS,
            "round_trip_cost": COST,
            "break_even_precision": BREAK_EVEN_PRECISION,
        },
        "historical": {
            "rows": len(history),
            "positives": int(history["label_value"].sum()),
            "oos_rows": len(oos),
            "folds": fold_reports,
            "variants_tested": len(grid),
            "selected_policy": asdict(selected_policy),
            "selected_metrics": _metrics(oos, selected_policy),
            "baseline_metrics": _metrics(oos, baseline_policy),
        },
        "model_lock": final_fit,
        "forward_coverage": {
            **coverage,
            "resolved_candidates": int(evaluated["label_value"].notna().sum()),
            "excluded_incomplete_future": int(evaluated["exclusion_reason"].eq("incomplete_future").sum()),
            "excluded_ambiguous_same_bar": int(evaluated["exclusion_reason"].eq("ambiguous_same_bar").sum()),
            "symbols": int(evaluated["symbol"].nunique()),
            "start": evaluated["feature_time"].min(),
            "end": evaluated["feature_time"].max(),
        },
        "august_locked_policy": locked_result,
        "august_baseline": baseline_result,
        "august_per_week": weekly,
        "promotion": {
            "required_new_independent_signals": 100,
            "minimum_precision": 0.50,
            "wilson_lower_above_break_even": True,
            "passed": (
                locked_result["evaluable_signals"] >= 100
                and locked_result["precision"] >= 0.50
                and locked_result["precision_wilson95_lower"] > BREAK_EVEN_PRECISION
            ),
        },
        "live_configuration_changed": False,
        "files": {
            "lock": lock_path,
            "research_model": model_path,
            "historical_grid": output_dir / "forward48_timing_historical_grid.csv",
            "august_signals": output_dir / "forward48_timing_august_signals.csv",
        },
    }
    report_path = output_dir / "forward48_timing_report.json"
    report_path.write_text(json.dumps(report, indent=2, default=_json_default), encoding="utf-8")
    print(json.dumps({
        "output_dir": str(output_dir),
        "lock_sha256": lock_hash,
        "selected_policy": asdict(selected_policy),
        "historical": report["historical"]["selected_metrics"],
        "august": locked_result,
        "baseline": baseline_result,
        "promotion": report["promotion"],
    }, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
