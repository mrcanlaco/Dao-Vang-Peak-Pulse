"""Leakage-safe trainer for the distribution_short_v2 label.

This module keeps candidate selection, outcome labels, model fitting,
calibration, threshold policy, OOS evaluation and promotion separate.
It never changes live configuration; freezing requires every gate to pass.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

from dao_vang.experiments.calibration import (
    ProbabilityCalibrator,
    fit_probability_calibrator,
)
from dao_vang.experiments.forward_test import freeze_model

LOGGER = logging.getLogger(__name__)

# Exact schema of the current serving bundle: v2 gets no research-only feature
# advantage and can be deployed without changing snapshot collection.
SERVING_FEATURE_COLS: tuple[str, ...] = (
    "price_ret_5m",
    "price_ret_1h",
    "price_ret_4h",
    "price_ret_24h",
    "price_volatility_24h",
    "distance_from_high_24h",
    "volume_percentile_24h",
    "momentum_deceleration_4h",
    "fake_breakout_1h",
    "funding_rate_raw",
    "funding_percentile_7d",
    "funding_percentile_30d",
    "funding_zscore_30d",
    "funding_change_8h",
    "funding_change_24h",
    "funding_persistence_7d",
    "oi_change_1h",
    "oi_change_4h",
    "oi_change_24h",
    "taker_buy_ratio",
    "global_ls_ratio",
    "top_ls_ratio",
    "retail_top_spread",
    "spread_trend_1h",
    "spread_trend_4h",
)


@dataclass(frozen=True)
class V2TrainingConfig:
    feature_db: Path = Path("artifacts/backtest_results_pit.duckdb")
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    dataset_db: Path = Path("artifacts/distribution_v2_training.duckdb")
    artifact_dir: Path = Path("artifacts")
    source_table: str = "bt_combined"
    dataset_table: str = "distribution_v2_hourly_candidates"
    label_version: str = "distribution_short_v2"
    target_drawdown: float = 0.20
    max_adverse_excursion: float = 0.16
    horizon_hours: int = 24
    pump_threshold_24h: float = 0.15
    sample_minute: int = 4
    min_future_bars: int = 276
    n_folds: int = 4
    warmup_days: int = 90
    embargo_hours: int = 24
    calibration_method: str = "isotonic"
    min_recall_for_threshold: float = 0.10
    min_policy_signals: int = 10
    round_trip_cost: float = 0.002
    random_state: int = 42
    rebuild_dataset: bool = False
    freeze_if_passed: bool = True

    def validate(self) -> None:
        if not 0.0 < self.target_drawdown < 1.0:
            raise ValueError("target_drawdown must be in (0, 1)")
        if not 0.0 < self.max_adverse_excursion < 1.0:
            raise ValueError("max_adverse_excursion must be in (0, 1)")
        if self.horizon_hours != 24:
            raise ValueError("distribution_short_v2 is fixed at 24 hours")
        if self.n_folds < 3:
            raise ValueError("at least three OOS folds are required")
        if not 0 <= self.sample_minute <= 59:
            raise ValueError("sample_minute must be in [0, 59]")


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def materialize_v2_dataset(config: V2TrainingConfig) -> dict[str, Any]:
    """Build the sampled PIT universe and exact target-before-stop labels."""

    config.validate()
    config.dataset_db.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(config.dataset_db))
    conn.execute("PRAGMA disable_progress_bar")
    conn.execute("SET threads=4")
    conn.execute(
        f"ATTACH '{_sql_path(config.feature_db)}' AS feature_source (READ_ONLY)"
    )
    conn.execute(
        f"ATTACH '{_sql_path(config.market_db)}' AS market_source (READ_ONLY)"
    )
    try:
        existing = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='main' AND table_name=?",
            [config.dataset_table],
        ).fetchone()[0]
        if existing and not config.rebuild_dataset:
            LOGGER.info("Reusing materialized dataset %s", config.dataset_db)
        else:
            feature_sql = ",\n                        ".join(
                f"f.{column}" for column in SERVING_FEATURE_COLS
            )
            conn.execute(f"DROP TABLE IF EXISTS {config.dataset_table}")
            LOGGER.info("Materializing hourly pump candidates and 24h outcomes")
            conn.execute(
                f"""
                CREATE TABLE {config.dataset_table} AS
                WITH candidates AS (
                    SELECT
                        f.feature_time,
                        f.symbol,
                        k.close AS entry_price,
                        {feature_sql}
                    FROM feature_source.main.{config.source_table} f
                    INNER JOIN market_source.main.klines_5m k
                        ON k.symbol = f.symbol
                       AND k.close_time = f.feature_time
                    WHERE f.price_ret_24h >= {config.pump_threshold_24h}
                      AND EXTRACT(MINUTE FROM f.feature_time) = {config.sample_minute}
                ),
                outcomes AS (
                    SELECT
                        c.symbol,
                        c.feature_time,
                        COUNT(f.close_time) AS future_bars,
                        MAX(f.close_time) AS last_future_time,
                        MIN(f.close_time) FILTER (
                            WHERE f.low <= c.entry_price * {1.0 - config.target_drawdown}
                        ) AS target_time,
                        MIN(f.close_time) FILTER (
                            WHERE f.high >= c.entry_price * {1.0 + config.max_adverse_excursion}
                        ) AS stop_time,
                        MIN(f.low) AS future_min_low,
                        MAX(f.high) AS future_max_high
                    FROM candidates c
                    LEFT JOIN market_source.main.klines_5m f
                        ON f.symbol = c.symbol
                       AND f.close_time > c.feature_time
                       AND f.close_time <= c.feature_time
                           + INTERVAL '{config.horizon_hours}' HOUR
                    GROUP BY c.symbol, c.feature_time
                )
                SELECT
                    c.*,
                    o.future_bars,
                    o.target_time,
                    o.stop_time,
                    o.future_min_low,
                    o.future_max_high,
                    CASE
                        WHEN o.future_bars < {config.min_future_bars} THEN NULL
                        WHEN o.last_future_time < c.feature_time
                            + INTERVAL '{config.horizon_hours}' HOUR
                            - INTERVAL '5' MINUTE THEN NULL
                        WHEN o.target_time IS NOT NULL
                         AND o.target_time = o.stop_time THEN NULL
                        WHEN o.target_time IS NOT NULL
                         AND (o.stop_time IS NULL OR o.target_time < o.stop_time) THEN 1
                        ELSE 0
                    END AS label_value,
                    CASE WHEN o.target_time IS NOT NULL THEN
                        CAST(EXTRACT(EPOCH FROM (o.target_time - c.feature_time))
                             / 60 AS INTEGER)
                    END AS lead_time_minutes,
                    c.feature_time + INTERVAL '{config.horizon_hours}' HOUR
                        AS invalidation_time
                FROM candidates c
                INNER JOIN outcomes o
                    ON o.symbol = c.symbol AND o.feature_time = c.feature_time
                ORDER BY c.feature_time, c.symbol
                """
            )
        cursor = conn.execute(
            f"""
            SELECT COUNT(*) AS rows,
                   COUNT(label_value) AS labeled_rows,
                   SUM(CASE WHEN label_value=1 THEN 1 ELSE 0 END) AS positives,
                   SUM(CASE WHEN label_value=0 THEN 1 ELSE 0 END) AS negatives,
                   COUNT(*) - COUNT(label_value) AS excluded,
                   COUNT(DISTINCT symbol) AS symbols,
                   MIN(feature_time) AS min_time,
                   MAX(feature_time) AS max_time
            FROM {config.dataset_table}
            """
        )
        row = cursor.fetchone()
        columns = [item[0] for item in cursor.description]
        return dict(zip(columns, row))
    finally:
        conn.close()


def load_v2_dataset(config: V2TrainingConfig) -> pd.DataFrame:
    conn = duckdb.connect(str(config.dataset_db), read_only=True)
    try:
        frame = conn.execute(
            f"SELECT * FROM {config.dataset_table} "
            "WHERE label_value IS NOT NULL ORDER BY feature_time, symbol"
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["label_value"] = frame["label_value"].astype("int8")
    return frame


def _build_estimator(model_name: str, seed: int) -> Pipeline:
    if model_name == "lightgbm":
        estimator: Any = lgb.LGBMClassifier(
            random_state=seed,
            n_estimators=300,
            learning_rate=0.03,
            max_depth=4,
            num_leaves=15,
            min_child_samples=80,
            subsample=0.85,
            colsample_bytree=0.85,
            reg_lambda=1.0,
            deterministic=True,
            force_col_wise=True,
            verbosity=-1,
            n_jobs=4,
        )
    elif model_name == "logistic_regression":
        estimator = LogisticRegression(max_iter=1500, random_state=seed)
    else:
        raise ValueError(f"unsupported model: {model_name}")
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("estimator", estimator),
        ]
    )


def _partition_history(
    history: pd.DataFrame, embargo: pd.Timedelta
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Create fit/calibration/policy partitions separated by label embargoes."""

    unique_times = pd.Series(history["feature_time"].drop_duplicates().sort_values())
    if len(unique_times) < 30:
        empty = history.iloc[:0]
        return empty, empty, empty
    fit_boundary = unique_times.iloc[int((len(unique_times) - 1) * 0.70)]
    calibration_boundary = unique_times.iloc[int((len(unique_times) - 1) * 0.85)]
    fit = history[history["feature_time"] < fit_boundary]
    calibration = history[
        (history["feature_time"] >= fit_boundary + embargo)
        & (history["feature_time"] < calibration_boundary)
    ]
    policy = history[history["feature_time"] >= calibration_boundary + embargo]
    return fit, calibration, policy


def _calibrator(
    model: Pipeline,
    calibration: pd.DataFrame,
    feature_cols: Iterable[str],
    method: str,
) -> ProbabilityCalibrator:
    columns = list(feature_cols)
    raw = model.predict_proba(calibration[columns])[:, 1]
    return fit_probability_calibrator(
        raw,
        calibration["label_value"].to_numpy(),
        method=method,
        calibrator_id=f"{method}_distribution_short_v2",
    )


def _predict_calibrated(
    model: Pipeline,
    calibrator: ProbabilityCalibrator,
    frame: pd.DataFrame,
    feature_cols: Iterable[str],
) -> tuple[np.ndarray, np.ndarray]:
    columns = list(feature_cols)
    raw = np.asarray(model.predict_proba(frame[columns])[:, 1], dtype=float)
    return raw, calibrator.transform(raw)


def _threshold_metrics(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
    target: float,
    stop: float,
    cost: float,
    identities: pd.DataFrame | None = None,
    cooldown_hours: int = 24,
) -> dict[str, Any]:
    signal = probabilities >= threshold
    if identities is not None:
        if len(identities) != len(signal):
            raise ValueError("identities and probabilities length mismatch")
        episode_signal = np.zeros(len(signal), dtype=bool)
        last_signal: dict[str, pd.Timestamp] = {}
        for index, (symbol, feature_time) in enumerate(
            identities[["symbol", "feature_time"]].itertuples(index=False)
        ):
            if not signal[index]:
                continue
            timestamp = pd.Timestamp(feature_time)
            previous = last_signal.get(str(symbol))
            if (
                previous is None
                or timestamp >= previous + pd.Timedelta(hours=cooldown_hours)
            ):
                episode_signal[index] = True
                last_signal[str(symbol)] = timestamp
        signal = episode_signal
    positives = int((y_true == 1).sum())
    true_positives = int((signal & (y_true == 1)).sum())
    false_positives = int((signal & (y_true == 0)).sum())
    signals = int(signal.sum())
    precision = true_positives / signals if signals else 0.0
    recall = true_positives / positives if positives else 0.0
    conservative_ev = precision * target - (1.0 - precision) * stop - cost
    return {
        "threshold": float(threshold),
        "signals": signals,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "precision": float(precision),
        "recall": float(recall),
        "conservative_ev": float(conservative_ev),
    }


def select_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    config: V2TrainingConfig,
    identities: pd.DataFrame | None = None,
) -> tuple[float, dict[str, Any]]:
    """Choose the policy threshold without looking at the OOS test fold."""

    candidates: list[dict[str, Any]] = []
    for threshold in np.arange(0.05, 0.951, 0.01):
        row = _threshold_metrics(
            y_true,
            probabilities,
            float(threshold),
            config.target_drawdown,
            config.max_adverse_excursion,
            config.round_trip_cost,
            identities,
        )
        if row["signals"] >= config.min_policy_signals:
            candidates.append(row)
    eligible = [
        row
        for row in candidates
        if row["recall"] >= config.min_recall_for_threshold
    ]
    pool = eligible or candidates
    if not pool:
        fallback = _threshold_metrics(
            y_true,
            probabilities,
            0.95,
            config.target_drawdown,
            config.max_adverse_excursion,
            config.round_trip_cost,
            identities,
        )
        return 0.95, fallback
    best = max(
        pool,
        key=lambda row: (
            row["conservative_ev"],
            row["precision"],
            row["recall"],
            row["threshold"],
        ),
    )
    return float(best["threshold"]), best


def _probability_metrics(
    y_true: np.ndarray, probabilities: np.ndarray
) -> dict[str, Any]:
    prevalence = float(np.mean(y_true))
    average_precision = float(average_precision_score(y_true, probabilities))
    roc_auc = (
        float(roc_auc_score(y_true, probabilities))
        if len(np.unique(y_true)) == 2
        else None
    )
    bins = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    for index in range(10):
        mask = (probabilities >= bins[index]) & (
            probabilities <= bins[index + 1]
            if index == 9
            else probabilities < bins[index + 1]
        )
        if mask.any():
            ece += float(mask.mean()) * abs(
                float(probabilities[mask].mean()) - float(y_true[mask].mean())
            )
    top_rates: dict[str, Any] = {}
    for fraction in (0.01, 0.02, 0.05):
        count = max(1, int(math.ceil(len(y_true) * fraction)))
        indices = np.argsort(-probabilities, kind="mergesort")[:count]
        top_rates[f"precision_top_{int(fraction * 100)}pct"] = float(
            y_true[indices].mean()
        )
    return {
        "rows": int(len(y_true)),
        "positives": int(y_true.sum()),
        "prevalence": prevalence,
        "average_precision": average_precision,
        "ap_lift_over_prevalence": (
            average_precision / prevalence if prevalence else None
        ),
        "roc_auc": roc_auc,
        "brier": float(brier_score_loss(y_true, probabilities)),
        "null_brier": float(
            brier_score_loss(y_true, np.full(len(y_true), prevalence))
        ),
        "ece": float(ece),
        **top_rates,
    }


def _walk_forward_boundaries(
    frame: pd.DataFrame, config: V2TrainingConfig
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start = frame["feature_time"].min()
    end = frame["feature_time"].max() + pd.Timedelta(microseconds=1)
    first_test = start + pd.Timedelta(days=config.warmup_days)
    if first_test >= end:
        raise ValueError("dataset is shorter than warmup period")
    step = (end - first_test) / config.n_folds
    return [
        (first_test + step * index, first_test + step * (index + 1))
        for index in range(config.n_folds)
    ]


def run_walk_forward_training(
    frame: pd.DataFrame, config: V2TrainingConfig
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Evaluate both models on identical expanding OOS windows."""

    feature_cols = list(SERVING_FEATURE_COLS)
    missing = [column for column in feature_cols if column not in frame.columns]
    if missing:
        raise ValueError(f"dataset is missing serving features: {missing}")
    embargo = pd.Timedelta(hours=config.embargo_hours)
    results: dict[str, list[dict[str, Any]]] = {
        "lightgbm": [],
        "logistic_regression": [],
    }
    oos: dict[str, list[dict[str, Any]]] = {name: [] for name in results}

    for fold_index, (test_start, test_end) in enumerate(
        _walk_forward_boundaries(frame, config), start=1
    ):
        history = frame[frame["feature_time"] < test_start - embargo]
        fit, calibration, policy = _partition_history(history, embargo)
        test = frame[
            (frame["feature_time"] >= test_start)
            & (frame["feature_time"] < test_end)
        ]
        partitions = {
            "fit": fit,
            "calibration": calibration,
            "policy": policy,
            "test": test,
        }
        if any(
            len(part) < 50 or part["label_value"].nunique() < 2
            for part in partitions.values()
        ):
            LOGGER.warning(
                "Skipping fold %d because a partition lacks two classes",
                fold_index,
            )
            continue

        for model_name in results:
            model = _build_estimator(
                model_name, config.random_state + fold_index
            )
            model.fit(fit[feature_cols], fit["label_value"])
            calibrator = _calibrator(
                model, calibration, feature_cols, config.calibration_method
            )
            _, policy_prob = _predict_calibrated(
                model, calibrator, policy, feature_cols
            )
            threshold, policy_selection = select_threshold(
                policy["label_value"].to_numpy(),
                policy_prob,
                config,
                policy[["symbol", "feature_time"]],
            )
            raw_test, test_prob = _predict_calibrated(
                model, calibrator, test, feature_cols
            )
            y_test = test["label_value"].to_numpy()
            probability = _probability_metrics(y_test, test_prob)
            decision = _threshold_metrics(
                y_test,
                test_prob,
                threshold,
                config.target_drawdown,
                config.max_adverse_excursion,
                config.round_trip_cost,
                test[["symbol", "feature_time"]],
            )
            fold = {
                "fold": fold_index,
                "train_start": fit["feature_time"].min(),
                "fit_end": fit["feature_time"].max(),
                "calibration_start": calibration["feature_time"].min(),
                "calibration_end": calibration["feature_time"].max(),
                "policy_start": policy["feature_time"].min(),
                "policy_end": policy["feature_time"].max(),
                "test_start": test["feature_time"].min(),
                "test_end": test["feature_time"].max(),
                "partition_rows": {
                    name: len(part) for name, part in partitions.items()
                },
                "policy_selection": policy_selection,
                "probability_metrics": probability,
                "decision_metrics": decision,
            }
            results[model_name].append(fold)
            test_identity = test[
                ["symbol", "feature_time", "label_value"]
            ].itertuples(index=False)
            for row_index, row in enumerate(test_identity):
                oos[model_name].append(
                    {
                        "symbol": row.symbol,
                        "feature_time": row.feature_time,
                        "label": int(row.label_value),
                        "raw_probability": float(raw_test[row_index]),
                        "probability": float(test_prob[row_index]),
                        "threshold": threshold,
                        "signal": bool(test_prob[row_index] >= threshold),
                        "fold": fold_index,
                    }
                )
            LOGGER.info(
                "%s fold %d: test=%d AP=%.4f signals=%d "
                "precision=%.3f recall=%.3f EV=%.4f",
                model_name,
                fold_index,
                len(test),
                probability["average_precision"],
                decision["signals"],
                decision["precision"],
                decision["recall"],
                decision["conservative_ev"],
            )

    summary: dict[str, Any] = {}
    for model_name, records in oos.items():
        if not records:
            summary[model_name] = {"folds": 0}
            continue
        oos_frame = pd.DataFrame(records)
        y = oos_frame["label"].to_numpy(dtype=int)
        probabilities = oos_frame["probability"].to_numpy(dtype=float)
        raw_signal = (
            oos_frame["probability"].to_numpy(dtype=float)
            >= oos_frame["threshold"].to_numpy(dtype=float)
        )
        signal = np.zeros(len(oos_frame), dtype=bool)
        last_signal: dict[str, pd.Timestamp] = {}
        for index, row in enumerate(
            oos_frame[["symbol", "feature_time"]].itertuples(index=False)
        ):
            if not raw_signal[index]:
                continue
            timestamp = pd.Timestamp(row.feature_time)
            previous = last_signal.get(str(row.symbol))
            if previous is None or timestamp >= previous + pd.Timedelta(hours=24):
                signal[index] = True
                last_signal[str(row.symbol)] = timestamp
        signals = int(signal.sum())
        true_positives = int((signal & (y == 1)).sum())
        precision = true_positives / signals if signals else 0.0
        positive_count = int((y == 1).sum())
        recall = true_positives / positive_count if positive_count else 0.0
        ev = (
            precision * config.target_drawdown
            - (1 - precision) * config.max_adverse_excursion
            - config.round_trip_cost
        )
        fold_evs = [
            float(fold["decision_metrics"]["conservative_ev"])
            for fold in results[model_name]
        ]
        summary[model_name] = {
            "folds": len(results[model_name]),
            **_probability_metrics(y, probabilities),
            "signals": signals,
            "true_positives": true_positives,
            "precision": float(precision),
            "recall": float(recall),
            "conservative_ev": float(ev),
            "positive_ev_folds": int(sum(value > 0 for value in fold_evs)),
            "mean_fold_ev": float(np.mean(fold_evs)),
        }
    return {"folds": results, "summary": summary}, oos


def promotion_gate(report: dict[str, Any]) -> dict[str, Any]:
    challenger = report["summary"].get("lightgbm", {})
    baseline = report["summary"].get("logistic_regression", {})
    checks = {
        "at_least_four_oos_folds": challenger.get("folds", 0) >= 4,
        "at_least_40_oos_signals": challenger.get("signals", 0) >= 40,
        "precision_at_least_50pct": challenger.get("precision", 0.0) >= 0.50,
        "recall_at_least_10pct": challenger.get("recall", 0.0) >= 0.10,
        "positive_conservative_ev": (
            challenger.get("conservative_ev", -1.0) > 0.0
        ),
        "positive_ev_in_three_folds": (
            challenger.get("positive_ev_folds", 0) >= 3
        ),
        "ap_lift_at_least_1_5x": (
            challenger.get("ap_lift_over_prevalence") or 0.0
        ) >= 1.5,
        "brier_beats_null": (
            challenger.get("brier", 1.0)
            < challenger.get("null_brier", 0.0)
        ),
        "ap_not_worse_than_logistic": (
            challenger.get("average_precision", 0.0)
            >= baseline.get("average_precision", 1.0)
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def fit_research_bundle(
    frame: pd.DataFrame, config: V2TrainingConfig, run_dir: Path
) -> dict[str, Any]:
    """Fit an inspectable challenger without implying release approval."""

    embargo = pd.Timedelta(hours=config.embargo_hours)
    fit, calibration, policy = _partition_history(frame, embargo)
    if any(
        len(part) < 50 or part["label_value"].nunique() < 2
        for part in (fit, calibration, policy)
    ):
        raise ValueError(
            "final fit/calibration/policy partitions are insufficient"
        )
    feature_cols = list(SERVING_FEATURE_COLS)
    model = _build_estimator("lightgbm", config.random_state)
    model.fit(fit[feature_cols], fit["label_value"])
    calibrator = _calibrator(
        model, calibration, feature_cols, config.calibration_method
    )
    _, policy_probability = _predict_calibrated(
        model, calibrator, policy, feature_cols
    )
    threshold, policy_metrics = select_threshold(
        policy["label_value"].to_numpy(),
        policy_probability,
        config,
        policy[["symbol", "feature_time"]],
    )
    model_path = run_dir / "model.joblib"
    calibrator_path = run_dir / "calibrator.joblib"
    joblib.dump(model, model_path)
    joblib.dump(calibrator, calibrator_path)
    return {
        "model": model,
        "calibrator": calibrator,
        "threshold": threshold,
        "policy_metrics": policy_metrics,
        "train_cutoff": policy["feature_time"].max(),
        "partition_rows": {
            "fit": len(fit),
            "calibration": len(calibration),
            "policy": len(policy),
        },
        "model_path": str(model_path),
        "calibrator_path": str(calibrator_path),
    }


def run(config: V2TrainingConfig) -> dict[str, Any]:
    config.validate()
    dataset = materialize_v2_dataset(config)
    LOGGER.info("Dataset summary: %s", dataset)
    frame = load_v2_dataset(config)
    if len(frame) < 500 or frame["label_value"].nunique() < 2:
        raise ValueError("insufficient labeled rows for v2 training")
    evaluation, oos = run_walk_forward_training(frame, config)
    gate = promotion_gate(evaluation)

    generated_at = datetime.now(timezone.utc)
    run_id = generated_at.strftime("distribution_v2_%Y%m%d_%H%M%S")
    run_dir = config.artifact_dir / "research_models" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    bundle = fit_research_bundle(frame, config, run_dir)

    fingerprint_payload = {
        "dataset": dataset,
        "feature_cols": SERVING_FEATURE_COLS,
        "label_version": config.label_version,
        "target": config.target_drawdown,
        "mae": config.max_adverse_excursion,
        "horizon": config.horizon_hours,
        "pump_threshold": config.pump_threshold_24h,
    }
    dataset_fingerprint = hashlib.sha256(
        json.dumps(
            fingerprint_payload, default=_jsonable, sort_keys=True
        ).encode("utf-8")
    ).hexdigest()
    frozen_model_id: str | None = None
    if gate["passed"] and config.freeze_if_passed:
        info = freeze_model(
            model=bundle["model"],
            calibrator=bundle["calibrator"],
            threshold=bundle["threshold"],
            feature_cols=list(SERVING_FEATURE_COLS),
            config={
                "hypothesis_id": "distribution_20pct_with_mae16",
                "dataset_version": dataset_fingerprint,
                "label_version": config.label_version,
                "feature_set_version": "serving_features_v1_25",
                "split_version": (
                    "expanding_4fold_fit_cal_policy_embargo24h_v1"
                ),
                "threshold_policy_version": "conservative_ev_v1",
                "seed": config.random_state,
            },
            train_cutoff=bundle["train_cutoff"],
            training_stats={
                **bundle["partition_rows"],
                "oos": evaluation["summary"]["lightgbm"],
                "promotion_gate": gate,
            },
            label_spec={
                "version": config.label_version,
                "horizon_hours": config.horizon_hours,
                "horizon_minutes": config.horizon_hours * 60,
                "target_drawdown": config.target_drawdown,
                "max_ae": config.max_adverse_excursion,
                "same_bar_policy": "exclude_ambiguous",
            },
            threshold_policy={
                "version": "conservative_ev_v1",
                "high_confidence_min_prob": bundle["threshold"],
                "watch_min_prob": max(0.05, bundle["threshold"] * 0.75),
            },
            artifact_dir=config.artifact_dir,
        )
        frozen_model_id = info.model_id

    serializable_bundle = {
        key: value
        for key, value in bundle.items()
        if key not in {"model", "calibrator"}
    }
    report = {
        "artifact": "distribution_short_v2_training_report",
        "run_id": run_id,
        "generated_at": generated_at,
        "status": (
            "frozen_challenger" if frozen_model_id else "research_only"
        ),
        "production_config_changed": False,
        "config": asdict(config),
        "label_contract": {
            "target_drawdown": config.target_drawdown,
            "horizon_hours": config.horizon_hours,
            "max_adverse_excursion": config.max_adverse_excursion,
            "ordering": "target_before_stop",
            "same_bar_policy": "exclude_ambiguous",
        },
        "dataset": dataset,
        "dataset_fingerprint": dataset_fingerprint,
        "feature_cols": list(SERVING_FEATURE_COLS),
        "evaluation": evaluation,
        "promotion_gate": gate,
        "research_bundle": serializable_bundle,
        "frozen_model_id": frozen_model_id,
    }
    report_path = run_dir / "report.json"
    report_path.write_text(
        json.dumps(
            report, indent=2, ensure_ascii=False, default=_jsonable
        ),
        encoding="utf-8",
    )
    for model_name, records in oos.items():
        pd.DataFrame(records).to_csv(
            run_dir / f"oos_{model_name}.csv", index=False
        )
    metadata = {
        "schema_version": "research_bundle_v1",
        "run_id": run_id,
        "label_version": config.label_version,
        "dataset_fingerprint": dataset_fingerprint,
        "feature_cols": list(SERVING_FEATURE_COLS),
        "threshold": bundle["threshold"],
        "train_cutoff": bundle["train_cutoff"],
        "promotion_gate": gate,
        "model_path": "model.joblib",
        "calibrator_path": "calibrator.joblib",
    }
    (run_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, default=_jsonable),
        encoding="utf-8",
    )
    report["report_path"] = str(report_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--feature-db", type=Path, default=V2TrainingConfig.feature_db
    )
    parser.add_argument(
        "--market-db", type=Path, default=V2TrainingConfig.market_db
    )
    parser.add_argument(
        "--dataset-db", type=Path, default=V2TrainingConfig.dataset_db
    )
    parser.add_argument(
        "--artifact-dir", type=Path, default=V2TrainingConfig.artifact_dir
    )
    parser.add_argument("--rebuild-dataset", action="store_true")
    parser.add_argument("--no-freeze", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    config = V2TrainingConfig(
        feature_db=args.feature_db,
        market_db=args.market_db,
        dataset_db=args.dataset_db,
        artifact_dir=args.artifact_dir,
        rebuild_dataset=args.rebuild_dataset,
        freeze_if_passed=not args.no_freeze,
    )
    report = run(config)
    print(
        json.dumps(
            {
                "status": report["status"],
                "report_path": report["report_path"],
                "promotion_gate": report["promotion_gate"],
                "summary": report["evaluation"]["summary"],
                "frozen_model_id": report["frozen_model_id"],
            },
            indent=2,
            default=_jsonable,
        )
    )


if __name__ == "__main__":
    main()
