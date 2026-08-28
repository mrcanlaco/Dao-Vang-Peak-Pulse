# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUnknownMemberType=false, reportMissingTypeStubs=false, reportMissingImports=false, reportPrivateUsage=false
"""Guarded batch self-learning for the live scanner.

The scanner deliberately serves an immutable champion bundle.  This module
closes the feedback loop without changing that serving contract:

    materialized outcomes -> chronological challenger training -> holdout gate
    -> frozen challenger artifact (never promoted automatically)

The implementation is intentionally batch-oriented.  Labels arrive after the
prediction horizon, so ``partial_fit`` would be both hard to audit and easy to
misuse.  A scheduler or the scanner daemon may call ``run_self_learning``
repeatedly; the state file makes repeated calls idempotent until new outcomes
arrive.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

import duckdb
import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_score, recall_score
from sklearn.pipeline import Pipeline

from dao_vang.domain.time import system_now
from dao_vang.experiments.forward_test import freeze_model, load_frozen_model
from dao_vang.experiments.walk_forward import _precision_first_threshold


def _utc_now() -> datetime:
    """Compatibility name; application wall-clock time is UTC+7."""
    return system_now()


def _iso(value: datetime | None = None) -> str:
    return (value or _utc_now()).isoformat()


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _has_table(conn: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = ?
        LIMIT 1
        """,
        [table_name],
    ).fetchone()
    return row is not None


def _load_resolved_training_frame(
    conn: duckdb.DuckDBPyConnection,
    *,
    horizon_hours: int,
    preferred_horizon: int = 12,
) -> pd.DataFrame:
    """Load one point-in-time feature row per resolved signal.

    Multiple model bundles may score the same signal.  Deduplicating by
    symbol/signal/horizon prevents those repeated observations from inflating
    the training set while keeping the outcome attached to the original
    prediction audit.
    """

    if not _has_table(conn, "predictions") or not _has_table(
        conn, "prediction_outcomes"
    ) or not _has_table(conn, "feature_results"):
        return pd.DataFrame()

    feature_columns = {
        str(row[0])
        for row in conn.execute("DESCRIBE feature_results").fetchall()
    }
    quality_filter = (
        "AND COALESCE(CAST(f.quality_status AS VARCHAR), 'valid') = 'valid'"
        if "quality_status" in feature_columns
        else ""
    )

    return conn.execute(
        f"""
        WITH resolved AS (
            SELECT
                p.prediction_id,
                p.symbol,
                p.signal_time,
                p.horizon_hours,
                o.label_value,
                o.materialized_at,
                o.event_id,
                o.max_drawdown_{preferred_horizon}h,
                ROW_NUMBER() OVER (
                    PARTITION BY p.symbol, p.signal_time, p.horizon_hours
                    ORDER BY o.materialized_at DESC, p.created_at DESC,
                             p.prediction_id DESC
                ) AS row_number
            FROM predictions p
            INNER JOIN prediction_outcomes o
                ON o.prediction_id = p.prediction_id
            WHERE o.outcome_status = 'materialized'
              AND o.label_value IN (0, 1)
              AND p.quality_status = 'valid'
              AND p.horizon_hours = ?
        )
        SELECT
            f.*,
            r.prediction_id,
            r.horizon_hours,
            CASE 
                WHEN r.max_drawdown_{preferred_horizon}h IS NOT NULL THEN
                    CASE WHEN r.max_drawdown_{preferred_horizon}h <= -0.04 THEN 1 ELSE 0 END
                ELSE r.label_value 
            END AS target_label,
            r.materialized_at AS outcome_materialized_at,
            r.event_id AS outcome_event_id,
            'live' AS training_source
        FROM feature_results f
        INNER JOIN resolved r
            ON f.symbol = r.symbol
           AND f.feature_time = r.signal_time
        WHERE r.row_number = 1
          {quality_filter}
        ORDER BY f.feature_time, f.symbol
        """,
        [int(horizon_hours)],
    ).df()


def _load_historical_training_frame(
    conn: duckdb.DuckDBPyConnection,
    *,
    horizon_hours: int,
) -> pd.DataFrame:
    """Load point-in-time historical features joined to materialized labels.

    Historical labels bootstrap the first challenger before live prediction
    outcomes have accumulated. Only explicit 0/1 labels for the champion
    horizon are accepted. Rows marked ``warning`` remain usable because the
    existing backtest pipeline treats them as labeled observations.
    """

    if not _has_table(conn, "labels") or not _has_table(conn, "feature_results"):
        return pd.DataFrame()

    feature_columns = {
        str(row[0])
        for row in conn.execute("DESCRIBE feature_results").fetchall()
    }
    quality_filter = (
        "AND COALESCE(CAST(f.quality_status AS VARCHAR), 'valid') = 'valid'"
        if "quality_status" in feature_columns
        else ""
    )

    return conn.execute(
        f"""
        SELECT
            f.*,
            l.horizon_hours,
            l.label_value AS target_label,
            l.signal_time AS outcome_materialized_at,
            CAST(NULL AS VARCHAR) AS outcome_event_id,
            'historical' AS training_source,
            concat(
                'historical:', f.symbol, ':', CAST(f.feature_time AS VARCHAR),
                ':', CAST(l.horizon_hours AS VARCHAR)
            ) AS prediction_id
        FROM feature_results f
        INNER JOIN labels l
            ON f.feature_time = l.signal_time
           AND f.symbol = l.symbol
        WHERE l.horizon_hours = ?
          AND l.label_value IN (0, 1)
          {quality_filter}
        ORDER BY f.feature_time, f.symbol
        """,
        [int(horizon_hours)],
    ).df()


def _combine_training_frames(
    historical: pd.DataFrame,
    live: pd.DataFrame,
    *,
    max_historical_rows: int,
    seed: int,
) -> pd.DataFrame:
    """Combine historical bootstrap data and newer live outcomes.

    Live outcomes win when the same symbol/time/horizon exists in both
    sources. Historical rows are capped by a seeded sample so a routine check
    cannot become an unbounded memory job.
    """

    historical = historical.copy()
    live = live.copy()
    if not historical.empty:
        historical["training_source"] = "historical"
        historical["source_priority"] = 1
        historical = historical.sample(
            n=min(len(historical), int(max_historical_rows)),
            random_state=int(seed),
        )
    if not live.empty:
        live["training_source"] = "live"
        live["source_priority"] = 0

    frames = [frame for frame in (live, historical) if not frame.empty]
    if not frames:
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined = combined.sort_values(
        ["source_priority", "feature_time", "symbol"]
    )
    dedupe_columns = ["symbol", "feature_time"]
    if "horizon_hours" in combined.columns:
        dedupe_columns.append("horizon_hours")
    combined = combined.drop_duplicates(dedupe_columns, keep="first")
    return combined.sort_values(["feature_time", "symbol"]).reset_index(drop=True)


def _sample_weights(
    frame: pd.DataFrame,
    *,
    recent_window_days: int,
    recent_sample_weight: float,
) -> np.ndarray:
    """Weight recent observations more heavily without dropping history."""

    if frame.empty:
        return np.asarray([], dtype=float)
    cutoff = frame["feature_time"].max() - pd.Timedelta(days=int(recent_window_days))
    recent = frame["feature_time"] >= cutoff
    return np.where(recent.to_numpy(), float(recent_sample_weight), 1.0)


def _fit_estimator(
    model: Pipeline,
    features: pd.DataFrame,
    labels: pd.Series,
    weights: np.ndarray,
) -> Pipeline:
    """Fit the pipeline with estimator-level sample weights."""

    model.fit(
        features,
        labels,
        model__sample_weight=np.asarray(weights, dtype=float),
    )
    return model


def _build_estimator(seed: int) -> Pipeline:
    """Build the same serving-compatible estimator family as freeze_model."""

    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            (
                "model",
                LogisticRegression(
                    max_iter=1000,
                    random_state=seed,
                    class_weight="balanced",
                ),
            ),
        ]
    )


def _probabilities(model: Any, frame: pd.DataFrame) -> np.ndarray:
    if not hasattr(model, "predict_proba"):
        return np.zeros(len(frame), dtype=float)
    values = np.asarray(model.predict_proba(frame))
    if values.ndim != 2 or values.shape[1] == 0:
        return np.zeros(len(frame), dtype=float)
    if values.shape[1] == 1:
        classes = getattr(model, "classes_", None)
        if classes is not None and len(classes) == 1 and int(classes[0]) == 1:
            return np.ones(len(frame), dtype=float)
        return np.zeros(len(frame), dtype=float)
    return values[:, 1].astype(float)


def _metrics(
    y_true: pd.Series | np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> dict[str, float]:
    actual = np.asarray(y_true, dtype=int)
    predicted = (probabilities >= threshold).astype(int)
    return {
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "brier": float(brier_score_loss(actual, probabilities)),
        "threshold": float(threshold),
        "n_rows": float(len(actual)),
        "n_positive": float(actual.sum()),
        "n_predicted_positive": float(predicted.sum()),
    }


def _dataset_fingerprint(frame: pd.DataFrame) -> str:
    ids = sorted(str(value) for value in frame["prediction_id"].tolist())
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()


def _positive_event_count(frame: pd.DataFrame) -> int:
    if frame.empty or "target_label" not in frame.columns:
        return 0
    positives = frame[frame["target_label"].astype(int) == 1]
    if positives.empty:
        return 0
    event_ids = positives["outcome_event_id"].dropna().astype(str)
    if not event_ids.empty:
        return int(event_ids.nunique())
    return int(len(positives))


def _normalise_frame(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    if result.empty and not {
        "feature_time",
        "target_label",
    }.issubset(result.columns):
        return result
    result["feature_time"] = pd.to_datetime(result["feature_time"], utc=True)
    result["target_label"] = pd.to_numeric(result["target_label"], errors="coerce")
    result = result.dropna(subset=["feature_time", "target_label"])
    result = result[result["target_label"].isin([0, 1])]
    return result.sort_values(["feature_time", "symbol"]).reset_index(drop=True)


def _gate(
    champion: Mapping[str, float],
    challenger: Mapping[str, float],
    *,
    min_precision_improvement: float,
    max_recall_regression: float,
    max_brier_regression: float,
) -> dict[str, Any]:
    precision_delta = float(challenger["precision"] - champion["precision"])
    recall_delta = float(challenger["recall"] - champion["recall"])
    brier_delta = float(challenger["brier"] - champion["brier"])
    checks = {
        "precision_improvement": {
            "actual": precision_delta,
            "required": float(min_precision_improvement),
            "passed": precision_delta >= min_precision_improvement,
        },
        "recall_regression": {
            "actual": recall_delta,
            "minimum": -float(max_recall_regression),
            "passed": recall_delta >= -max_recall_regression,
        },
        "brier_regression": {
            "actual": brier_delta,
            "maximum": float(max_brier_regression),
            "passed": brier_delta <= max_brier_regression,
        },
    }
    return {
        "passed": all(bool(item["passed"]) for item in checks.values()),
        "checks": checks,
    }


def run_self_learning(
    *,
    db_path: str | Path,
    artifact_dir: str | Path,
    champion_model_id: str,
    state_path: str | Path,
    report_dir: str | Path,
    min_training_outcomes: int = 200,
    min_new_outcomes: int = 50,
    min_positive_events: int = 20,
    min_precision_improvement: float = 0.01,
    max_recall_regression: float = 0.05,
    max_brier_regression: float = 0.01,
    recent_window_days: int = 14,
    recent_sample_weight: float = 2.0,
    historical_max_rows: int = 100_000,
    seed: int = 42,
    force: bool = False,
) -> dict[str, Any]:
    """Train and gate one hybrid historical/live challenger.

    Historical point-in-time labels provide the bootstrap dataset. New live
    outcomes are merged in when available, and observations in the recent
    window receive a higher sample weight. The function never changes scanner
    configuration or the active bundle.
    """

    state_file = Path(state_path)
    reports = Path(report_dir)
    state = _read_json(state_file)
    started_at = _utc_now()

    try:
        champion_info = load_frozen_model(champion_model_id, Path(artifact_dir))
    except (FileNotFoundError, ValueError, OSError) as exc:
        return {
            "status": "blocked",
            "reason": "champion_model_unavailable",
            "message": str(exc),
            "champion_model_id": champion_model_id,
        }

    label_spec = dict(champion_info.label_spec or {})
    horizon_hours = int(label_spec.get("horizon_hours", 24))

    try:
        # DuckDB is commonly held by the live scanner.  ScanResultStore's
        # read-only connection has the repository's copy fallback, so a
        # training check never competes with or interrupts serving.
        # Local import avoids the scanner package's daemon import cycle during
        # CLI startup.
        from dao_vang.scanner.scan_results_store import ScanResultStore

        store = ScanResultStore(
            str(db_path),
            read_only=True,
            prefer_snapshot=True,
        )
        with store._conn() as conn:  # noqa: SLF001 - shared read-only fallback
            historical = _normalise_frame(
                _load_historical_training_frame(
                    conn,
                    horizon_hours=horizon_hours,
                )
            )
            live = _normalise_frame(
                _load_resolved_training_frame(
                    conn,
                    horizon_hours=horizon_hours,
                )
            )
            frame = _combine_training_frames(
                historical,
                live,
                max_historical_rows=historical_max_rows,
                seed=seed,
            )
    except Exception as exc:
        return {
            "status": "blocked",
            "reason": "training_data_unavailable",
            "message": str(exc),
            "champion_model_id": champion_model_id,
        }

    historical_outcomes = int(len(historical))
    live_outcomes = int(len(live))
    total_outcomes = int(len(frame))
    recent_cutoff = (
        frame["feature_time"].max() - pd.Timedelta(days=int(recent_window_days))
        if not frame.empty
        else None
    )
    recent_outcomes = (
        int((frame["feature_time"] >= recent_cutoff).sum())
        if recent_cutoff is not None
        else 0
    )
    positive_events = _positive_event_count(frame)
    dataset_fingerprint = _dataset_fingerprint(frame) if not frame.empty else None
    previous_count = int(state.get("last_training_outcome_count", 0) or 0)
    new_outcomes = max(0, total_outcomes - previous_count)

    readiness = {
        "training_outcomes": total_outcomes,
        "positive_events": positive_events,
        "new_outcomes": new_outcomes,
        "min_training_outcomes": int(min_training_outcomes),
        "min_positive_events": int(min_positive_events),
        "min_new_outcomes": int(min_new_outcomes),
        "historical_outcomes": historical_outcomes,
        "live_outcomes": live_outcomes,
        "recent_outcomes": recent_outcomes,
        "recent_window_days": int(recent_window_days),
        "recent_sample_weight": float(recent_sample_weight),
    }
    if total_outcomes < min_training_outcomes or positive_events < min_positive_events:
        return {
            "status": "not_ready",
            "reason": "insufficient_materialized_outcomes",
            "readiness": readiness,
            "champion_model_id": champion_model_id,
        }
    if (
        not force
        and new_outcomes < min_new_outcomes
        and dataset_fingerprint == state.get("last_training_fingerprint")
    ):
        return {
            "status": "skipped",
            "reason": "no_new_outcomes_since_last_run",
            "readiness": readiness,
            "champion_model_id": champion_model_id,
            "last_report_path": state.get("last_report_path"),
        }

    feature_cols = list(champion_info.feature_cols)
    missing_features = [
        column for column in feature_cols if column not in frame.columns
    ]
    if missing_features:
        return {
            "status": "blocked",
            "reason": "champion_features_missing_from_dataset",
            "missing_features": missing_features,
            "readiness": readiness,
            "champion_model_id": champion_model_id,
        }

    champion_cutoff = pd.Timestamp(champion_info.train_cutoff)
    if champion_cutoff.tzinfo is None:
        champion_cutoff = champion_cutoff.tz_localize("UTC")
    else:
        champion_cutoff = champion_cutoff.tz_convert("UTC")
    post_champion = frame[frame["feature_time"] > champion_cutoff].copy()
    if len(post_champion) < 4:
        return {
            "status": "blocked",
            "reason": "no_sufficient_forward_historical_data",
            "readiness": readiness,
            "champion_train_cutoff": str(champion_cutoff),
            "champion_model_id": champion_model_id,
        }

    # Keep the newest half of the post-champion data untouched for the gate.
    # The earlier portion of the post-champion data is available for threshold
    # validation, while the pre-champion history supplies the stable base.
    holdout_start_index = max(1, int(len(post_champion) * 0.50))
    holdout_start = post_champion.iloc[holdout_start_index]["feature_time"]
    holdout = frame[frame["feature_time"] >= holdout_start].copy()
    pre_holdout = frame[frame["feature_time"] < holdout_start].copy()
    validation_start = max(1, int(len(pre_holdout) * 0.80))
    train = pre_holdout.iloc[:validation_start]
    validation = pre_holdout.iloc[validation_start:]

    if (
        train.empty
        or validation.empty
        or holdout.empty
        or train["target_label"].nunique() < 2
        or validation["target_label"].nunique() < 2
        or holdout["target_label"].nunique() < 2
    ):
        return {
            "status": "blocked",
            "reason": "chronological_split_lacks_class_diversity",
            "readiness": readiness,
            "split_sizes": {
                "train": len(train),
                "validation": len(validation),
                "holdout": len(holdout),
            },
            "champion_train_cutoff": str(champion_cutoff),
            "holdout_start": str(holdout_start),
            "champion_model_id": champion_model_id,
        }

    X_train = train[feature_cols]
    y_train = train["target_label"].astype(int)
    X_validation = validation[feature_cols]
    y_validation = validation["target_label"].astype(int)
    X_holdout = holdout[feature_cols]
    y_holdout = holdout["target_label"].astype(int)
    train_weights = _sample_weights(
        train,
        recent_window_days=recent_window_days,
        recent_sample_weight=recent_sample_weight,
    )
    validation_weights = _sample_weights(
        validation,
        recent_window_days=recent_window_days,
        recent_sample_weight=recent_sample_weight,
    )

    validation_model = _build_estimator(seed)
    validation_model = _fit_estimator(
        validation_model,
        X_train,
        y_train,
        train_weights,
    )
    validation_probability = _probabilities(validation_model, X_validation)
    threshold = _precision_first_threshold(
        validation_probability,
        y_validation.to_numpy(),
        min_recall=0.50,
    )

    evaluation_model = _build_estimator(seed)
    _fit_estimator(
        evaluation_model,
        pd.concat([X_train, X_validation], ignore_index=True),
        pd.concat([y_train, y_validation], ignore_index=True),
        np.concatenate([train_weights, validation_weights]),
    )
    challenger_probability = _probabilities(evaluation_model, X_holdout)
    challenger_metrics = _metrics(y_holdout, challenger_probability, threshold)

    try:
        champion_model = joblib.load(champion_info.model_path)
        champion_probability = _probabilities(champion_model, X_holdout)
        champion_metrics = _metrics(
            y_holdout,
            champion_probability,
            float(champion_info.threshold),
        )
    except (OSError, ValueError, AttributeError) as exc:
        return {
            "status": "blocked",
            "reason": "champion_inference_failed",
            "message": str(exc),
            "readiness": readiness,
            "champion_model_id": champion_model_id,
        }

    gate = _gate(
        champion_metrics,
        challenger_metrics,
        min_precision_improvement=min_precision_improvement,
        max_recall_regression=max_recall_regression,
        max_brier_regression=max_brier_regression,
    )
    run_id = f"selflearn_{started_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"
    report: dict[str, Any] = {
        "schema_version": "self_learning_run_v1",
        "run_id": run_id,
        "started_at": _iso(started_at),
        "completed_at": _iso(),
        "status": "challenger_ready" if gate["passed"] else "gate_failed",
        "promotion": {
            "auto_promote": False,
            "promoted": False,
            "requires_human_approval": True,
        },
        "champion_model_id": champion_model_id,
        "challenger_model_id": None,
        "readiness": readiness,
        "dataset": {
            "fingerprint": dataset_fingerprint,
            "feature_time_start": str(frame["feature_time"].min()),
            "feature_time_end": str(frame["feature_time"].max()),
            "outcome_materialized_through": str(frame["outcome_materialized_at"].max()),
            "historical_outcomes": historical_outcomes,
            "live_outcomes": live_outcomes,
            "recent_outcomes": recent_outcomes,
            "recent_window_days": int(recent_window_days),
            "recent_sample_weight": float(recent_sample_weight),
        },
        "split_sizes": {
            "train": len(train),
            "validation": len(validation),
            "holdout": len(holdout),
        },
        "feature_cols": feature_cols,
        "threshold": float(threshold),
        "champion_metrics": champion_metrics,
        "challenger_metrics": challenger_metrics,
        "gate": gate,
        "config": {
            "min_precision_improvement": float(min_precision_improvement),
            "max_recall_regression": float(max_recall_regression),
            "max_brier_regression": float(max_brier_regression),
            "recent_window_days": int(recent_window_days),
            "recent_sample_weight": float(recent_sample_weight),
            "historical_max_rows": int(historical_max_rows),
            "seed": int(seed),
        },
    }

    if gate["passed"]:
        final_model = _build_estimator(seed)
        _fit_estimator(
            final_model,
            frame[feature_cols],
            frame["target_label"].astype(int),
            _sample_weights(
                frame,
                recent_window_days=recent_window_days,
                recent_sample_weight=recent_sample_weight,
            ),
        )
        parent_config = dict(champion_info.config or {})
        parent_config.update(
            {
                "parent_model_id": champion_model_id,
                "training_method": "hybrid_historical_recent_self_learning_v1",
                "self_learning_run_id": run_id,
                "source_outcome_count": total_outcomes,
                "historical_outcome_count": historical_outcomes,
                "live_outcome_count": live_outcomes,
                "recent_window_days": int(recent_window_days),
                "recent_sample_weight": float(recent_sample_weight),
            }
        )
        threshold_policy = dict(champion_info.threshold_policy or {})
        threshold_policy["threshold"] = float(threshold)
        candidate_info = freeze_model(
            model=final_model,
            threshold=float(threshold),
            feature_cols=feature_cols,
            config=parent_config,
            train_cutoff=frame["feature_time"].max(),
            training_stats={
                "precision": challenger_metrics["precision"],
                "recall": challenger_metrics["recall"],
                "brier": challenger_metrics["brier"],
                "threshold": float(threshold),
                "train_size": total_outcomes,
                "train_positives": int(frame["target_label"].sum()),
                "holdout_metrics": challenger_metrics,
                "parent_model_id": champion_model_id,
                "self_learning_run_id": run_id,
            },
            label_spec=label_spec,
            threshold_policy=threshold_policy,
            artifact_dir=Path(artifact_dir),
        )
        report["challenger_model_id"] = candidate_info.model_id

    report_path = reports / f"{run_id}.json"
    report["report_path"] = str(report_path)
    _atomic_json_write(report_path, report)
    _atomic_json_write(
        state_file,
        {
            **state,
            "schema_version": "self_learning_state_v1",
            "last_run_at": _iso(),
            "last_status": report["status"],
            "last_training_outcome_count": total_outcomes,
            "last_training_positive_events": positive_events,
            "last_training_fingerprint": dataset_fingerprint,
            "last_report_path": str(report_path),
            "last_challenger_model_id": report["challenger_model_id"],
        },
    )
    return report


__all__ = ["run_self_learning"]
