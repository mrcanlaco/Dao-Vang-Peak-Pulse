"""Forward test loop — freeze a model, score new data, track predictions vs
materialized labels over time.

This implements ROADMAP Phase 5 (Forward Collection) and Phase 6 (Watchlist)
gating: a model must be frozen (code + config + threshold locked) BEFORE the
forward test period starts. Data arriving after the freeze date is scored
with the frozen model and never used for retraining.

Constitution §9: "chạy end-to-end bằng một command" + "có thể tái tạo cùng
kết quả từ cùng raw snapshot và config". A frozen model guarantees
reproducibility — the same frozen model + same new data = same predictions.

Flow:
    1. freeze_model(model, threshold, feature_cols, config, train_cutoff)
       -> saves model.joblib + metadata.json to artifacts/frozen_models/
    2. score_frozen(model_id, df_new)
       -> returns predictions for data AFTER train_cutoff
    3. evaluate_frozen(model_id, df_with_materialized_labels)
       -> compares predictions vs labels that have now materialized
    4. list_frozen_models() / load_frozen_model(model_id)
       -> registry operations
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd

from dao_vang.domain.time import system_now

FROZEN_DIR_NAME = "frozen_models"

_DEFAULT_LABEL_SPEC: Dict[str, Any] = {
    "horizon_minutes": 1440,
    "target_drawdown": 0.08,
    "max_ae": 0.04,
}


@dataclass
class FrozenModelInfo:
    """Metadata for a frozen model."""
    model_id: str
    freeze_time: str
    train_cutoff: str  # ISO â€” data after this is forward test
    threshold: float
    feature_cols: List[str]
    config: Dict[str, Any]
    training_stats: Dict[str, Any]
    label_spec: Dict[str, Any]
    model_path: Path
    metadata_path: Path
    schema_version: str = "frozen_bundle_v1"
    calibrator_id: str = "identity_v1"
    calibrator_path: Path | None = None
    checksums: Dict[str, str] | None = None
    threshold_policy: Dict[str, Any] | None = None


class _IdentityCalibrator:
    """Explicit identity calibrator for bundles without a fitted calibrator.

    Identity is a declared policy, not an implicit placeholder: it is saved,
    hashed and loaded exactly like an isotonic/logistic calibrator.  Training
    code can pass a fitted object implementing ``transform`` or ``predict``.
    """

    version = "identity_v1"

    def transform(self, values: Any) -> np.ndarray:
        return np.clip(np.asarray(values, dtype=float), 0.0, 1.0)

    def predict(self, values: Any) -> np.ndarray:
        return self.transform(values)


def _calibrator_identifier(calibrator: Any, config: Dict[str, Any]) -> tuple[str, str]:
    """Infer a truthful stable id and method for a serialized calibrator.

    Older bundles used ``config['calibrator_id']`` as a fallback even when a
    fitted sklearn calibrator was supplied.  That made an isotonic artifact
    look like the explicitly rejected ``identity_v1`` calibrator at serving
    time.  Prefer identifiers exposed by the object, then infer the supported
    sklearn class, and only use a non-identity configured id as a final
    fallback.
    """

    declared = getattr(calibrator, "calibrator_id", None) or getattr(
        calibrator, "version", None
    )
    if declared:
        normalized = str(declared).strip().lower()
        if normalized != "identity_v1":
            method = "platt" if "platt" in normalized or "sigmoid" in normalized else normalized.split("_", 1)[0]
            return str(declared), method
        return "identity_v1", "identity"

    class_name = type(calibrator).__name__.strip().lower()
    module_name = type(calibrator).__module__.strip().lower()
    if class_name == "isotonicregression" or module_name == "sklearn.isotonic":
        return "isotonic_v1", "isotonic"
    if class_name == "logisticregression" and module_name.startswith("sklearn."):
        return "platt_v1", "platt"

    configured = str((config or {}).get("calibrator_id") or "").strip()
    if configured and configured.lower() != "identity_v1":
        return configured, configured.split("_", 1)[0].lower()
    return "calibrator_v1", "custom"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frozen_base_dir(artifact_dir: Path) -> Path:
    """Return the frozen models directory."""
    d = artifact_dir / FROZEN_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def freeze_model(
    model: Any,
    threshold: float,
    feature_cols: List[str],
    config: Dict[str, Any],
    train_cutoff: Any,
    training_stats: Optional[Dict[str, Any]] = None,
    label_spec: Optional[Dict[str, Any]] = None,
    artifact_dir: Path = Path("artifacts"),
    calibrator: Any | None = None,
    threshold_policy: Optional[Dict[str, Any]] = None,
) -> FrozenModelInfo:
    """Freeze a trained model for forward testing.

    Saves the model (joblib) and metadata (JSON) to
    ``artifact_dir/frozen_models/frozen_<timestamp>_<uuid>/``.

    Args:
        model: Trained sklearn estimator (must be pickleable).
        threshold: Decision threshold tuned on validation set.
        feature_cols: Ordered list of feature column names the model expects.
        config: Experiment config dict (hypothesis_id, versions, seed, ...).
        train_cutoff: The latest feature_time in training data. Data after
            this point is forward-test data and must NOT be used for retraining.
        training_stats: Optional stats from training (precision, recall, brier,
            train_size, train_positives, ...).
        artifact_dir: Base artifacts directory.

    Returns:
        FrozenModelInfo with paths to the saved model and metadata.
    """
    now_system = system_now()
    timestamp = now_system.strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    model_id = f"frozen_{timestamp}_{short_uuid}"

    model_dir = _frozen_base_dir(artifact_dir) / model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "model.joblib"
    calibrator_path = model_dir / "calibrator.joblib"
    metadata_path = model_dir / "metadata.json"

    joblib.dump(model, model_path)
    calibrator_obj = calibrator if calibrator is not None else _IdentityCalibrator()
    joblib.dump(calibrator_obj, calibrator_path)

    cutoff_str = (
        train_cutoff.isoformat() if hasattr(train_cutoff, "isoformat")
        else str(train_cutoff)
    )

    label_spec = label_spec or {
        "horizon_minutes": 1440,
        "target_drawdown": 0.08,
        "max_ae": 0.04,
    }
    resolved_label_spec = dict(label_spec)
    resolved_label_spec.setdefault("version", "distribution_short_v1")
    resolved_label_spec.setdefault(
        "horizon_hours", int(resolved_label_spec.get("horizon_minutes", 1440)) // 60
    )
    resolved_label_spec.setdefault("horizon_minutes", int(resolved_label_spec["horizon_hours"]) * 60)
    resolved_threshold_policy = dict(threshold_policy or {})
    resolved_threshold_policy.setdefault("version", config.get("threshold_policy_version", "frozen_threshold_v1"))
    resolved_threshold_policy.setdefault("threshold", float(threshold))
    calibrator_id, calibration_method = _calibrator_identifier(
        calibrator_obj, config or {}
    )
    checksums = {
        "model_sha256": _sha256(model_path),
        "calibrator_sha256": _sha256(calibrator_path),
    }
    metadata = {
        "schema_version": "frozen_bundle_v1",
        "artifact_schema_version": "frozen_bundle_v1",
        "model_id": model_id,
        "freeze_time": now_system.isoformat(),
        "train_cutoff": cutoff_str,
        "threshold": float(threshold),
        "feature_cols": list(feature_cols),
        "config": config,
        "training_stats": training_stats or {},
        "label_spec": resolved_label_spec,
        "threshold_policy": resolved_threshold_policy,
        "thresholds": {"default": float(threshold)},
        "calibrator_id": calibrator_id,
        "calibrator": {"id": calibrator_id, "path": calibrator_path.name},
        "calibration_method": calibration_method,
        "preprocessing": {
            "feature_cols": list(feature_cols),
            "missing_policy": "reject_at_serving",
        },
        "checksums": checksums,
        "artifact_checksums": checksums,
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return FrozenModelInfo(
        model_id=model_id,
        freeze_time=str(metadata["freeze_time"]),
        train_cutoff=cutoff_str,
        threshold=float(threshold),
        feature_cols=list(feature_cols),
        config=config,
        training_stats=training_stats or {},
        label_spec=resolved_label_spec,
        model_path=model_path,
        metadata_path=metadata_path,
        schema_version="frozen_bundle_v1",
        calibrator_id=calibrator_id,
        calibrator_path=calibrator_path,
        checksums=checksums,
        threshold_policy=resolved_threshold_policy,
    )


def load_frozen_model(
    model_id: str,
    artifact_dir: Path = Path("artifacts"),
) -> FrozenModelInfo:
    """Load a frozen model's metadata (not the model itself).

    Use ``load_frozen_model_estimator`` to get the actual sklearn model.
    """
    model_dir = _frozen_base_dir(artifact_dir) / model_id
    metadata_path = model_dir / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(
            f"Frozen model {model_id} not found in {model_dir}"
        )
    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    checksums = metadata.get("checksums") or metadata.get("artifact_checksums") or {}
    calibrator_meta = metadata.get("calibrator") or {}
    calibrator_path = model_dir / str(calibrator_meta.get("path", "calibrator.joblib"))
    return FrozenModelInfo(
        model_id=metadata["model_id"],
        freeze_time=metadata["freeze_time"],
        train_cutoff=metadata["train_cutoff"],
        threshold=metadata["threshold"],
        feature_cols=metadata["feature_cols"],
        config=metadata["config"],
        training_stats=metadata.get("training_stats", {}),
        label_spec=metadata.get("label_spec", _DEFAULT_LABEL_SPEC),
        model_path=model_dir / "model.joblib",
        metadata_path=metadata_path,
        schema_version=metadata.get("schema_version", metadata.get("artifact_schema_version", "frozen_bundle_v1")),
        calibrator_id=str(metadata.get("calibrator_id", calibrator_meta.get("id", "identity_v1"))),
        calibrator_path=calibrator_path if calibrator_path.exists() else None,
        checksums=checksums,
        threshold_policy=metadata.get("threshold_policy") or metadata.get("thresholds"),
    )


def load_frozen_model_estimator(
    model_id: str,
    artifact_dir: Path = Path("artifacts"),
) -> Any:
    """Load and return the actual sklearn estimator from a frozen model."""
    info = load_frozen_model(model_id, artifact_dir)
    return joblib.load(info.model_path)


def list_frozen_models(
    artifact_dir: Path = Path("artifacts"),
) -> List[FrozenModelInfo]:
    """List all frozen models, newest first (by freeze_time, then model_id)."""
    base = _frozen_base_dir(artifact_dir)
    models = []
    for d in base.iterdir():
        if not d.is_dir():
            continue
        meta = d / "metadata.json"
        if not meta.exists():
            continue
        try:
            with open(meta, "r", encoding="utf-8") as f:
                m = json.load(f)
            checksums = m.get("checksums") or m.get("artifact_checksums") or {}
            calibrator_meta = m.get("calibrator") or {}
            calibrator_path = d / str(calibrator_meta.get("path", "calibrator.joblib"))
            models.append(FrozenModelInfo(
                model_id=m["model_id"],
                freeze_time=m["freeze_time"],
                train_cutoff=m["train_cutoff"],
                threshold=m["threshold"],
                feature_cols=m["feature_cols"],
                config=m["config"],
                training_stats=m.get("training_stats", {}),
                label_spec=m.get("label_spec", _DEFAULT_LABEL_SPEC),
                model_path=d / "model.joblib",
                metadata_path=meta,
                schema_version=m.get("schema_version", m.get("artifact_schema_version", "frozen_bundle_v1")),
                calibrator_id=str(m.get("calibrator_id", calibrator_meta.get("id", "identity_v1"))),
                calibrator_path=calibrator_path if calibrator_path.exists() else None,
                checksums=checksums,
                threshold_policy=m.get("threshold_policy") or m.get("thresholds"),
            ))
        except (json.JSONDecodeError, KeyError):
            continue
    # Sort by freeze_time (ISO string sorts chronologically), then model_id
    models.sort(key=lambda x: (x.freeze_time, x.model_id), reverse=True)
    return models


def score_frozen(
    model_id: str,
    df: pd.DataFrame,
    artifact_dir: Path = Path("artifacts"),
    only_after_cutoff: bool = True,
) -> pd.DataFrame:
    """Score new data with a frozen model.

    Args:
        model_id: Frozen model ID.
        df: DataFrame with feature columns + feature_time + symbol.
        artifact_dir: Base artifacts directory.
        only_after_cutoff: If True, only score rows with feature_time >
            train_cutoff (forward test data). If False, score all rows.

    Returns:
        DataFrame with columns: feature_time, symbol, probability,
        risk_level, threshold, invalidation_time, model_id.
    """
    info = load_frozen_model(model_id, artifact_dir)
    model = joblib.load(info.model_path)

    cutoff = pd.Timestamp(info.train_cutoff)

    if only_after_cutoff and "feature_time" in df.columns:
        work = df[df["feature_time"] > cutoff].copy()
    else:
        work = df.copy()

    if len(work) == 0:
        return pd.DataFrame(columns=[
            "feature_time", "symbol", "probability", "risk_level",
            "threshold", "invalidation_time", "model_id",
        ])

    # A frozen bundle must not invent evidence for missing inputs.  Exclude
    # incomplete rows from replay; the caller can audit them separately.
    if any(col not in work.columns for col in info.feature_cols):
        return pd.DataFrame(columns=[
            "feature_time", "symbol", "probability", "risk_level",
            "threshold", "invalidation_time", "model_id",
        ])
    complete = ~work[info.feature_cols].isna().any(axis=1)
    work = work.loc[complete].copy()
    if work.empty:
        return pd.DataFrame(columns=[
            "feature_time", "symbol", "probability", "risk_level",
            "threshold", "invalidation_time", "model_id",
        ])
    X = work[info.feature_cols]

    # Get probabilities
    if hasattr(model, "predict_proba") and len(getattr(model, "classes_", [])) > 1:
        proba = model.predict_proba(X)[:, 1]
    else:
        proba = np.zeros(len(work))

    threshold = info.threshold
    horizon_minutes = int(info.label_spec.get("horizon_minutes", 1440))

    results = []
    for i in range(len(work)):
        prob = float(proba[i])
        if prob >= threshold:
            risk = "CAO" if prob >= threshold * 1.5 else "TRUNG BÃŒNH"
        elif prob >= threshold * 0.5:
            risk = "THáº¤P"
        else:
            risk = "Ráº¤T THáº¤P"

        ft = work["feature_time"].iloc[i] if "feature_time" in work.columns else None
        inv_time = (
            ft + pd.Timedelta(minutes=horizon_minutes)
            if ft is not None else None
        )
        results.append({
            "feature_time": str(ft) if ft is not None else None,
            "symbol": work["symbol"].iloc[i] if "symbol" in work.columns else "N/A",
            "probability": prob,
            "risk_level": risk,
            "threshold": threshold,
            "invalidation_time": str(inv_time) if inv_time is not None else None,
            "model_id": model_id,
        })

    return pd.DataFrame(results)


def evaluate_frozen(
    model_id: str,
    df: pd.DataFrame,
    artifact_dir: Path = Path("artifacts"),
) -> Dict[str, Any]:
    """Evaluate a frozen model against materialized labels.

    Scores data after train_cutoff, then joins with labels (is_distribution)
    that have now materialized (i.e., enough time has passed for the 24h
    horizon to complete). Computes precision, recall, brier, and per-risk-level
    breakdown.

    Args:
        model_id: Frozen model ID.
        df: DataFrame with features + feature_time + symbol + is_distribution
            (labels). Labels may be NaN for rows where the horizon hasn't
            completed yet â€” those are excluded from metrics.
        artifact_dir: Base artifacts directory.

    Returns:
        Dict with predictions, metrics, and summary.
    """
    from sklearn.metrics import brier_score_loss, precision_score, recall_score

    info = load_frozen_model(model_id, artifact_dir)
    cutoff = pd.Timestamp(info.train_cutoff)

    # Only evaluate rows after cutoff that have materialized labels
    if "is_distribution" not in df.columns:
        return {"status": "no_labels", "message": "DataFrame missing is_distribution column"}
    if "feature_time" not in df.columns:
        return {"status": "no_time", "message": "DataFrame missing feature_time column"}

    work = df[df["feature_time"] > cutoff].copy()
    work = work.dropna(subset=["is_distribution"])

    if len(work) == 0:
        return {
            "status": "no_forward_data",
            "message": f"No labeled data after train_cutoff ({info.train_cutoff})",
            "model_id": model_id,
        }

    # Score only complete snapshots; a frozen model must not turn missing
    # evidence into a synthetic zero-valued feature.
    missing_columns = [col for col in info.feature_cols if col not in work.columns]
    if missing_columns:
        return {
            "status": "quality_failed",
            "message": f"Missing frozen features: {', '.join(missing_columns)}",
            "model_id": model_id,
        }
    complete = ~work[info.feature_cols].isna().any(axis=1)
    work = work.loc[complete].copy()
    if work.empty:
        return {
            "status": "quality_failed",
            "message": "No complete feature rows after missing-data gate",
            "model_id": model_id,
        }
    X = work[info.feature_cols]

    if hasattr(info, "model_path"):
        model = joblib.load(info.model_path)
    else:
        model = load_frozen_model_estimator(model_id, artifact_dir)

    if hasattr(model, "predict_proba") and len(getattr(model, "classes_", [])) > 1:
        proba = model.predict_proba(X)[:, 1]
    else:
        proba = np.zeros(len(work))

    threshold = info.threshold
    y_pred = (proba >= threshold).astype(int)
    y_true = work["is_distribution"].astype(int).values

    try:
        precision = float(precision_score(y_true, y_pred, zero_division=0))
        recall = float(recall_score(y_true, y_pred, zero_division=0))
        brier = float(brier_score_loss(y_true, proba))
    except Exception:
        precision, recall, brier = 0.0, 0.0, 0.0

    # Per-risk-level breakdown
    risk_levels = pd.Series(
        ["CAO" if p >= threshold * 1.5 else
         "TRUNG BÃŒNH" if p >= threshold else
         "THáº¤P" if p >= threshold * 0.5 else "Ráº¤T THáº¤P"
         for p in proba]
    )
    risk_breakdown = {}
    for level in ["CAO", "TRUNG BÃŒNH", "THáº¤P", "Ráº¤T THáº¤P"]:
        mask = risk_levels == level
        n = int(mask.sum())
        n_pos = int(y_true[mask.values].sum()) if n > 0 else 0
        risk_breakdown[level] = {
            "n_signals": n,
            "n_actual_distribution": n_pos,
            "precision": float(n_pos / n) if n > 0 else 0.0,
        }

    n_total = len(work)
    n_positive = int(y_true.sum())
    n_predicted_positive = int(y_pred.sum())

    # Compare with training stats
    train_stats = info.training_stats
    train_precision = train_stats.get("precision", 0.0)
    train_recall = train_stats.get("recall", 0.0)

    return {
        "status": "ok",
        "model_id": model_id,
        "train_cutoff": info.train_cutoff,
        "threshold": threshold,
        "n_forward_rows": n_total,
        "n_positive_labels": n_positive,
        "n_predicted_positive": n_predicted_positive,
        "metrics": {
            "precision": precision,
            "recall": recall,
            "brier": brier,
        },
        "training_metrics": {
            "precision": train_precision,
            "recall": train_recall,
        },
        "risk_breakdown": risk_breakdown,
        "drift_check": {
            "precision_delta": precision - train_precision,
            "recall_delta": recall - train_recall,
            "precision_drift": abs(precision - train_precision) > 0.1,
        },
        "summary": (
            f"Forward test: {n_total} rows after {info.train_cutoff[:10]}, "
            f"{n_positive} actual distributions, {n_predicted_positive} predicted. "
            f"Precision {precision:.4f} (train: {train_precision:.4f}, "
            f"drift: {precision - train_precision:+.4f}). "
            f"Recall {recall:.4f} (train: {train_recall:.4f})."
        ),
    }
