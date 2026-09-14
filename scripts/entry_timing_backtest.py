"""Episode-aware, sealed-holdout backtest for distribution_short_v2 timing.

This research runner consumes the already out-of-sample probabilities produced by
``train_distribution_v2.py``.  Folds 1-3 are the only development data.  A timing
policy is locked and hashed before fold 4 is queried from disk.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TimingPolicy:
    family: str
    threshold_add: float = 0.0
    confirmations: int = 1
    min_delay_hours: int = 0
    probability_tolerance: float = 0.0
    peak_drop: float = 0.0
    reversal: str = "none"


TARGET = 0.20
STOP = 0.16
COST = 0.002
EPISODE_GAP_HOURS = 6
COOLDOWN_HOURS = 24
MIN_SIGNALS_PER_DEV_FOLD = 12


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    raise TypeError(type(value).__name__)


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def load_folds(
    dataset_db: Path, predictions_csv: Path, folds: Iterable[int]
) -> pd.DataFrame:
    """Return only the requested folds; callers load holdout after policy lock."""

    fold_values = ",".join(str(int(value)) for value in folds)
    conn = duckdb.connect(str(dataset_db), read_only=True)
    try:
        frame = conn.execute(
            f"""
            SELECT p.symbol,
                   CAST(p.feature_time AS TIMESTAMPTZ) AS feature_time,
                   CAST(p.label AS INTEGER) AS label,
                   CAST(p.probability AS DOUBLE) AS probability,
                   CAST(p.threshold AS DOUBLE) AS threshold,
                   CAST(p.fold AS INTEGER) AS fold,
                   d.price_ret_5m,
                   d.price_ret_1h,
                   d.momentum_deceleration_4h,
                   d.distance_from_high_24h,
                   d.fake_breakout_1h
            FROM read_csv_auto('{_sql_path(predictions_csv)}', header=true) p
            INNER JOIN distribution_v2_hourly_candidates d
              ON d.symbol = p.symbol
             AND d.feature_time = CAST(p.feature_time AS TIMESTAMPTZ)
            WHERE CAST(p.fold AS INTEGER) IN ({fold_values})
            ORDER BY fold, feature_time, symbol
            """
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["episode_id"] = _episode_ids(frame)
    return frame


def _episode_ids(frame: pd.DataFrame) -> pd.Series:
    result = pd.Series(index=frame.index, dtype="object")
    for (fold, symbol), indices in frame.groupby(["fold", "symbol"], sort=False).groups.items():
        ordered = frame.loc[indices].sort_values("feature_time")
        gaps = ordered["feature_time"].diff().gt(pd.Timedelta(hours=EPISODE_GAP_HOURS))
        local = gaps.fillna(True).cumsum().astype(int)
        result.loc[ordered.index] = [f"f{fold}:{symbol}:{value}" for value in local]
    return result


def _reversal_mask(frame: pd.DataFrame, name: str) -> np.ndarray:
    if name == "none":
        return np.ones(len(frame), dtype=bool)
    if name == "ret5_nonpositive":
        return frame["price_ret_5m"].to_numpy() <= 0.0
    if name == "ret5_minus_1pct":
        return frame["price_ret_5m"].to_numpy() <= -0.01
    if name == "ret1_nonpositive":
        return frame["price_ret_1h"].to_numpy() <= 0.0
    if name == "ret1_minus_1pct":
        return frame["price_ret_1h"].to_numpy() <= -0.01
    if name == "momentum_nonpositive":
        return frame["momentum_deceleration_4h"].to_numpy() <= 0.0
    if name == "momentum_minus_2pct":
        return frame["momentum_deceleration_4h"].to_numpy() <= -0.02
    if name == "drawdown_3pct":
        return frame["distance_from_high_24h"].to_numpy() <= -0.03
    if name == "drawdown_5pct":
        return frame["distance_from_high_24h"].to_numpy() <= -0.05
    if name == "drawdown_8pct":
        return frame["distance_from_high_24h"].to_numpy() <= -0.08
    if name == "drawdown_12pct":
        return frame["distance_from_high_24h"].to_numpy() <= -0.12
    if name == "fake_breakout":
        return frame["fake_breakout_1h"].fillna(0.0).to_numpy() >= 0.5
    if name == "ret5_and_momentum":
        return (frame["price_ret_5m"].to_numpy() <= 0.0) & (
            frame["momentum_deceleration_4h"].to_numpy() <= 0.0
        )
    if name == "ret1_and_momentum":
        return (frame["price_ret_1h"].to_numpy() <= 0.0) & (
            frame["momentum_deceleration_4h"].to_numpy() <= 0.0
        )
    raise ValueError(f"unknown reversal rule: {name}")


def select_signals(frame: pd.DataFrame, policy: TimingPolicy) -> pd.DataFrame:
    """Apply one causal state machine and return at most one Entry 1 per episode."""

    selected: list[int] = []
    for _, episode in frame.groupby("episode_id", sort=False):
        episode = episode.sort_values("feature_time")
        times = episode["feature_time"].tolist()
        probabilities = episode["probability"].to_numpy(dtype=float)
        cutoffs = episode["threshold"].to_numpy(dtype=float) + policy.threshold_add
        above = probabilities >= cutoffs
        reversal = _reversal_mask(episode, policy.reversal)

        armed_at: int | None = None
        consecutive = 0
        running_peak = -np.inf
        for offset in range(len(episode)):
            contiguous = offset == 0 or (
                times[offset] - times[offset - 1] <= pd.Timedelta(minutes=90)
            )
            consecutive = consecutive + 1 if above[offset] and contiguous else int(above[offset])
            if armed_at is None and above[offset]:
                armed_at = offset
                running_peak = probabilities[offset]
            elif armed_at is not None:
                running_peak = max(running_peak, probabilities[offset])
            if armed_at is None:
                continue

            elapsed = (times[offset] - times[armed_at]).total_seconds() / 3600.0
            probability_ok = probabilities[offset] >= max(
                0.0, cutoffs[offset] - policy.probability_tolerance
            )
            peak_ok = (running_peak - probabilities[offset]) >= policy.peak_drop
            if policy.family == "confirmation":
                ready = consecutive >= policy.confirmations and reversal[offset]
            elif policy.family == "armed_reversal":
                ready = (
                    elapsed >= policy.min_delay_hours
                    and probability_ok
                    and peak_ok
                    and reversal[offset]
                )
            else:
                raise ValueError(f"unknown family: {policy.family}")
            if ready:
                selected.append(int(episode.index[offset]))
                break

    signals = frame.loc[selected].sort_values(["feature_time", "symbol"]).copy()
    if signals.empty:
        return signals
    keep: list[int] = []
    last_by_symbol: dict[str, pd.Timestamp] = {}
    for index, row in signals.iterrows():
        previous = last_by_symbol.get(str(row["symbol"]))
        current = pd.Timestamp(row["feature_time"])
        if previous is None or current >= previous + pd.Timedelta(hours=COOLDOWN_HOURS):
            keep.append(index)
            last_by_symbol[str(row["symbol"])] = current
    return signals.loc[keep]


def metrics(frame: pd.DataFrame, policy: TimingPolicy) -> dict[str, Any]:
    signals = select_signals(frame, policy)
    positive_episodes = set(
        frame.loc[frame["label"].eq(1), "episode_id"].astype(str).unique()
    )
    tp_rows = signals["label"].eq(1) if len(signals) else pd.Series(dtype=bool)
    true_positives = int(tp_rows.sum())
    signal_count = int(len(signals))
    precision = true_positives / signal_count if signal_count else 0.0
    caught = set(signals.loc[tp_rows, "episode_id"].astype(str))
    episode_recall = len(caught & positive_episodes) / len(positive_episodes) if positive_episodes else 0.0
    conservative_ev = (
        precision * TARGET - (1.0 - precision) * STOP - COST
        if signal_count
        else None
    )
    return {
        "signals": signal_count,
        "true_positives": true_positives,
        "false_positives": signal_count - true_positives,
        "precision": precision,
        "positive_episodes": len(positive_episodes),
        "caught_positive_episodes": len(caught & positive_episodes),
        "episode_recall": episode_recall,
        "conservative_ev": conservative_ev,
    }


def policy_grid() -> list[TimingPolicy]:
    policies: list[TimingPolicy] = []
    for threshold_add, confirmations, reversal in itertools.product(
        (0.0, 0.05, 0.10),
        (1, 2, 3),
        ("none", "ret5_nonpositive", "momentum_nonpositive", "drawdown_5pct"),
    ):
        policies.append(
            TimingPolicy(
                family="confirmation",
                threshold_add=threshold_add,
                confirmations=confirmations,
                reversal=reversal,
            )
        )
    reversals = (
        "none",
        "ret5_nonpositive",
        "ret1_nonpositive",
        "momentum_nonpositive",
        "drawdown_3pct",
        "drawdown_5pct",
        "drawdown_8pct",
        "drawdown_12pct",
        "ret5_and_momentum",
    )
    for threshold_add, delay, tolerance, peak_drop, reversal in itertools.product(
        (0.0, 0.05, 0.10),
        (0, 1, 2),
        (0.05, 0.10),
        (0.0, 0.05),
        reversals,
    ):
        if peak_drop == 0.0 and reversal == "none" and delay == 0:
            continue
        policies.append(
            TimingPolicy(
                family="armed_reversal",
                threshold_add=threshold_add,
                min_delay_hours=delay,
                probability_tolerance=tolerance,
                peak_drop=peak_drop,
                reversal=reversal,
            )
        )
    # Stable de-duplication and an explicit frozen comparator.
    unique = {json.dumps(asdict(policy), sort_keys=True): policy for policy in policies}
    baseline = TimingPolicy(family="confirmation")
    unique[json.dumps(asdict(baseline), sort_keys=True)] = baseline
    return list(unique.values())


def evaluate_development(frame: pd.DataFrame) -> tuple[TimingPolicy, pd.DataFrame]:
    rows: list[dict[str, Any]] = []
    for policy in policy_grid():
        per_fold = [metrics(part, policy) for _, part in frame.groupby("fold", sort=True)]
        fold_evs = np.asarray(
            [
                item["conservative_ev"]
                if item["conservative_ev"] is not None
                else -(STOP + COST)
                for item in per_fold
            ]
        )
        fold_signals = [item["signals"] for item in per_fold]
        aggregate = metrics(frame, policy)
        eligible = min(fold_signals, default=0) >= MIN_SIGNALS_PER_DEV_FOLD
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
    result = pd.DataFrame(rows)
    eligible = result[result["eligible"]]
    if eligible.empty:
        raise RuntimeError("no timing policy meets the pre-registered sample floor")
    winner_row = eligible.sort_values(
        ["robust_score", "episode_recall", "signals"], ascending=False
    ).iloc[0]
    return TimingPolicy(**json.loads(winner_row["policy"])), result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-db", type=Path, default=Path("artifacts/distribution_v2_training.duckdb"))
    parser.add_argument(
        "--predictions",
        type=Path,
        default=Path("artifacts/research_models/distribution_v2_20260913_130613/oos_lightgbm.csv"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/entry_timing_20260913"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    development = load_folds(args.dataset_db, args.predictions, (1, 2, 3))
    winner, grid = evaluate_development(development)
    locked_json = json.dumps(asdict(winner), sort_keys=True, separators=(",", ":"))
    locked_hash = hashlib.sha256(locked_json.encode()).hexdigest()
    grid.sort_values("robust_score", ascending=False).to_csv(
        args.output_dir / "entry_timing_development_grid.csv", index=False
    )

    # Sealed boundary: fold 4 is first queried only after winner and hash exist.
    holdout = load_folds(args.dataset_db, args.predictions, (4,))
    baseline = TimingPolicy(family="confirmation")
    selected_signals = select_signals(holdout, winner)
    selected_signals.to_csv(args.output_dir / "entry_timing_holdout_signals.csv", index=False)

    def fold_metrics(frame: pd.DataFrame, policy: TimingPolicy) -> list[dict[str, Any]]:
        return [
            {"fold": int(fold), **metrics(part, policy)}
            for fold, part in frame.groupby("fold", sort=True)
        ]

    winner_dev = metrics(development, winner)
    winner_holdout = metrics(holdout, winner)
    baseline_dev = metrics(development, baseline)
    baseline_holdout = metrics(holdout, baseline)
    report = {
        "artifact": "entry_timing_distribution_short_v2_backtest",
        "generated_at": datetime.now(timezone.utc),
        "status": "research_only",
        "label_contract": {
            "target": TARGET,
            "stop": STOP,
            "round_trip_cost": COST,
            "success": "20pct target before 16pct MAE within 24h",
        },
        "protocol": {
            "development_folds": [1, 2, 3],
            "sealed_holdout_fold": 4,
            "model_probabilities": "pre-existing fold-specific OOS calibrated probabilities",
            "model_thresholds": "selected in pre-test policy partitions by upstream runner",
            "embargo_hours_upstream": 24,
            "episode_gap_hours": EPISODE_GAP_HOURS,
            "one_entry_per_episode": True,
            "symbol_cooldown_hours": COOLDOWN_HOURS,
            "minimum_signals_per_development_fold": MIN_SIGNALS_PER_DEV_FOLD,
            "selection_score": "mean_fold_ev - 0.5 * std_fold_ev",
            "holdout_loaded_after_policy_hash": True,
            "variants_tested_on_development": int(len(grid)),
        },
        "locked_policy": asdict(winner),
        "locked_policy_sha256": locked_hash,
        "development": {
            "selected": winner_dev,
            "selected_per_fold": fold_metrics(development, winner),
            "baseline": baseline_dev,
            "baseline_per_fold": fold_metrics(development, baseline),
        },
        "sealed_holdout": {
            "selected": winner_holdout,
            "selected_per_fold": fold_metrics(holdout, winner),
            "baseline": baseline_holdout,
            "baseline_per_fold": fold_metrics(holdout, baseline),
            "evaluated_policies": ["locked_selected", "pre_registered_baseline"],
        },
        "promotion_gate": {
            "break_even_precision": (STOP + COST) / (TARGET + STOP),
            "selected_holdout_positive_ev": (
                winner_holdout["conservative_ev"] is not None
                and winner_holdout["conservative_ev"] > 0
            ),
            "selected_holdout_min_signals_30": winner_holdout["signals"] >= 30,
            "passed": (
                winner_holdout["conservative_ev"] is not None
                and winner_holdout["conservative_ev"] > 0
                and winner_holdout["signals"] >= 30
            ),
        },
    }
    (args.output_dir / "entry_timing_report.json").write_text(
        json.dumps(report, indent=2, default=_json_default), encoding="utf-8"
    )
    print(json.dumps(report, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
