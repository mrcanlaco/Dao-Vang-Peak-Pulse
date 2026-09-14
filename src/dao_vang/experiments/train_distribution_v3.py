"""Leakage-safe trainer for the distribution_short_v3_policy_48h contract.

Materializes 48h hourly pump candidates, applies 48h temporal embargoes,
trains calibrated opportunity models, and enforces fail-closed promotion gates.
Never changes live configuration; freezing requires every gate to pass.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb
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
from dao_vang.experiments.train_distribution_v2 import SERVING_FEATURE_COLS
from dao_vang.labels.specs.distribution_short_v3 import SPEC, TIMING

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class V3TrainingConfig:
    feature_db: Path = Path("artifacts/backtest_results_pit.duckdb")
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    cache_dataset_db: Path = Path("artifacts/universe_policy_v2_48h.duckdb")
    dataset_db: Path = Path("artifacts/distribution_v3_training.duckdb")
    artifact_dir: Path = Path("artifacts")
    source_table: str = "bt_combined"
    dataset_table: str = "distribution_v3_hourly_candidates"
    label_version: str = SPEC.version
    engine_version: str = SPEC.engine_version
    target_drawdown: float = SPEC.target
    max_adverse_excursion: float = SPEC.stop
    horizon_hours: int = SPEC.horizon_hours
    scale_in_hours: int = SPEC.scale_in_hours
    offsets: tuple[float, ...] = SPEC.offsets
    notional_weights: tuple[float, ...] = SPEC.notional_weights
    cost_per_side: float = SPEC.cost_per_side
    pump_threshold_24h: float = TIMING.min_return_24h
    sample_minute: int = 4
    min_future_bars: int = 552
    n_folds: int = 4
    warmup_days: int = 90
    embargo_hours: int = 48
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
        if self.horizon_hours != 48:
            raise ValueError("distribution_short_v3 is fixed at 48 hours")
        if self.n_folds < 3:
            raise ValueError("at least three OOS folds are required")
        if not 0 <= self.sample_minute <= 59:
            raise ValueError("sample_minute must be in [0, 59]")
        if self.embargo_hours < 48:
            raise ValueError("v3 embargo must be at least 48 hours")


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


def materialize_v3_dataset(config: V3TrainingConfig) -> dict[str, Any]:
    """Build the sampled PIT universe and 48h compact policy outcomes."""
    config.validate()
    config.dataset_db.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(config.dataset_db))
    conn.execute("PRAGMA disable_progress_bar")
    conn.execute("SET threads=4")

    try:
        existing_row = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='main' AND table_name=?",
            [config.dataset_table],
        ).fetchone()
        existing = existing_row[0] if existing_row else 0
        if existing and not config.rebuild_dataset:
            LOGGER.info("Reusing materialized dataset %s", config.dataset_db)
        else:
            conn.execute(f"DROP TABLE IF EXISTS {config.dataset_table}")
            # If cached 48h dataset exists with identical columns, reuse as base
            if config.cache_dataset_db.exists():
                LOGGER.info("Materializing from 48h cache %s", config.cache_dataset_db)
                conn.execute(
                    f"ATTACH '{_sql_path(config.cache_dataset_db)}' AS cache_source (READ_ONLY)"
                )
                conn.execute(f"""
                    CREATE TABLE {config.dataset_table} AS
                    SELECT
                        symbol,
                        feature_time,
                        entry_price,
                        {", ".join(SERVING_FEATURE_COLS)},
                        future_bars,
                        target_time,
                        stop_time,
                        label_value AS entry1_label_value,
                        label_value,
                        feature_time + INTERVAL '{config.horizon_hours}' HOUR AS invalidation_time
                    FROM cache_source.main.universe_policy_candidates_v2
                    WHERE price_ret_24h >= {config.pump_threshold_24h}
                      AND symbol NOT IN ('USDCUSDT', 'FDUSDUSDT', 'TUSDUSDT', 'BUSDUSDT', 'USDPUSDT', 'EURUSDT')
                    ORDER BY feature_time, symbol
                """)
                conn.execute("DETACH cache_source")
            else:
                conn.execute(
                    f"ATTACH '{_sql_path(config.feature_db)}' AS feature_source (READ_ONLY)"
                )
                conn.execute(
                    f"ATTACH '{_sql_path(config.market_db)}' AS market_source (READ_ONLY)"
                )
                feature_sql = ",\n                        ".join(
                    f"f.{column}" for column in SERVING_FEATURE_COLS
                )
                conn.execute(f"""
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
                          AND f.symbol NOT IN ('USDCUSDT', 'FDUSDUSDT', 'TUSDUSDT', 'BUSDUSDT', 'USDPUSDT', 'EURUSDT')
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
                            ) AS stop_time
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
                        END AS entry1_label_value,
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
                        c.feature_time + INTERVAL '{config.horizon_hours}' HOUR AS invalidation_time
                    FROM candidates c
                    INNER JOIN outcomes o
                        ON o.symbol = c.symbol AND o.feature_time = c.feature_time
                    ORDER BY c.feature_time, c.symbol
                """)
                conn.execute("DETACH feature_source")
                conn.execute("DETACH market_source")

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
        columns = [item[0] for item in (cursor.description or [])]
        return dict(zip(columns, row or ()))
    finally:
        conn.close()


def load_v3_dataset(config: V3TrainingConfig) -> pd.DataFrame:
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
    unique_times = pd.Series(history["feature_time"].drop_duplicates()).sort_values()
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
    return pd.DataFrame(fit), pd.DataFrame(calibration), pd.DataFrame(policy)


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
        calibrator_id=f"{method}_distribution_short_v3_48h",
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
    config: V3TrainingConfig,
    identities: pd.DataFrame | None = None,
) -> tuple[float, dict[str, Any]]:
    """Choose policy threshold without leaking the OOS test fold."""
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
    frame: pd.DataFrame, config: V3TrainingConfig
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start = frame["feature_time"].min()
    end = frame["feature_time"].max() + pd.Timedelta(microseconds=1)
    first_test = start + pd.Timedelta(days=config.warmup_days)
    if first_test >= end:
        raise ValueError("dataset is shorter than warmup period")
    step = (end - first_test) / config.n_folds
    return [
        (first_test + i * step, first_test + (i + 1) * step)
        for i in range(config.n_folds)
    ]


def evaluate_oos(
    config: V3TrainingConfig, frame: pd.DataFrame
) -> dict[str, Any]:
    """Run strict walk-forward evaluation across all OOS folds with 48h embargo."""
    embargo = pd.Timedelta(hours=config.embargo_hours)
    boundaries = _walk_forward_boundaries(frame, config)
    results: dict[str, list[dict[str, Any]]] = {
        "lightgbm": [],
        "logistic_regression": [],
    }
    feature_cols = list(SERVING_FEATURE_COLS)

    for fold_idx, (test_start, test_end) in enumerate(boundaries, 1):
        history_df = pd.DataFrame(frame[frame["feature_time"] < test_start - embargo])
        test_df = pd.DataFrame(
            frame[
                (frame["feature_time"] >= test_start)
                & (frame["feature_time"] < test_end)
            ]
        )
        if test_df.empty:
            continue
        fit, calibration, policy = _partition_history(history_df, embargo)
        if any(
            len(part) < 30 or part["label_value"].nunique() < 2
            for part in (fit, calibration, policy)
        ):
            continue

        for model_name in ("lightgbm", "logistic_regression"):
            model = _build_estimator(model_name, config.random_state + fold_idx)
            model.fit(fit[feature_cols], fit["label_value"])
            calibrator = _calibrator(
                model, calibration, feature_cols, config.calibration_method
            )
            _, policy_probs = _predict_calibrated(
                model, calibrator, policy, feature_cols
            )
            threshold, _ = select_threshold(
                np.asarray(policy["label_value"], dtype=np.int8),
                policy_probs,
                config,
                pd.DataFrame(policy[["symbol", "feature_time"]]),
            )
            _, test_probs = _predict_calibrated(
                model, calibrator, test_df, feature_cols
            )
            test_y = np.asarray(test_df["label_value"], dtype=np.int8)
            metrics = _probability_metrics(test_y, test_probs)
            t_metrics = _threshold_metrics(
                test_y,
                test_probs,
                threshold,
                config.target_drawdown,
                config.max_adverse_excursion,
                config.round_trip_cost,
                pd.DataFrame(test_df[["symbol", "feature_time"]]),
            )
            results[model_name].append(
                {
                    "fold": fold_idx,
                    "test_start": test_start,
                    "test_end": test_end,
                    "threshold": threshold,
                    **metrics,
                    **t_metrics,
                }
            )

    summary: dict[str, Any] = {}
    for model_name, folds in results.items():
        if not folds:
            summary[model_name] = {"error": "no evaluable folds"}
            continue
        summary[model_name] = {
            "folds": len(folds),
            "signals": int(sum(f["signals"] for f in folds)),
            "true_positives": int(sum(f["true_positives"] for f in folds)),
            "precision": float(
                np.mean([f["precision"] for f in folds if f["signals"] > 0])
                if any(f["signals"] > 0 for f in folds)
                else 0.0
            ),
            "recall": float(np.mean([f["recall"] for f in folds])),
            "conservative_ev": float(np.mean([f["conservative_ev"] for f in folds])),
            "positive_ev_folds": int(sum(f["conservative_ev"] > 0 for f in folds)),
            "average_precision": float(np.mean([f["average_precision"] for f in folds])),
            "ap_lift_over_prevalence": float(
                np.mean([f["ap_lift_over_prevalence"] for f in folds if f["ap_lift_over_prevalence"]])
            ),
            "roc_auc": float(np.mean([f["roc_auc"] for f in folds if f["roc_auc"] is not None])),
            "brier": float(np.mean([f["brier"] for f in folds])),
            "null_brier": float(np.mean([f["null_brier"] for f in folds])),
            "ece": float(np.mean([f["ece"] for f in folds])),
            "fold_details": folds,
        }
    return {"summary": summary, "boundaries": boundaries}


def promotion_gate(evaluation: dict[str, Any]) -> dict[str, Any]:
    """Strict fail-closed promotion gate per distribution_v3_research_standard."""
    summary = evaluation.get("summary", {})
    challenger = summary.get("lightgbm", {})
    baseline = summary.get("logistic_regression", {})

    if not challenger or "error" in challenger:
        return {"passed": False, "reason": "evaluation failed"}

    checks = {
        "sufficient_folds": challenger.get("folds", 0) >= 3,
        "sufficient_signals": challenger.get("signals", 0) >= 50,
        "positive_conservative_ev": challenger.get("conservative_ev", -1.0) > 0.0,
        "positive_ev_folds_majority": challenger.get("positive_ev_folds", 0)
        >= (challenger.get("folds", 1) / 2),
        "precision_above_breakeven": challenger.get("precision", 0.0) >= 0.45,
        "recall_above_minimum": challenger.get("recall", 0.0) >= 0.05,
        "brier_better_than_null": challenger.get("brier", 1.0)
        < challenger.get("null_brier", 0.0),
        "ece_under_threshold": challenger.get("ece", 1.0) <= 0.05,
        "ap_higher_than_baseline": challenger.get("average_precision", 0.0)
        > baseline.get("average_precision", 0.0),
    }
    return {"passed": all(checks.values()), "checks": checks}
