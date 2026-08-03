"""Forward test loop â€” freeze a model, score new data, track predictions vs
materialized labels over time.

This implements ROADMAP Phase 5 (Forward Collection) and Phase 6 (Watchlist)
gating: a model must be frozen (code + config + threshold locked) BEFORE the
forward test period starts. Data arriving after the freeze date is scored
with the frozen model and never used for retraining.

Constitution Â§9: "cháº¡y end-to-end báº±ng má»™t command" + "cÃ³ thá»ƒ tÃ¡i táº¡o cÃ¹ng
káº¿t quáº£ tá»« cÃ¹ng raw snapshot vÃ  config". A frozen model guarantees
reproducibility â€” the same frozen model + same new data = same predictions.

Flow:
    1. freeze_model(model, threshold, feature_cols, config, train_cutoff)
       â†’ saves model.joblib + metadata.json to artifacts/frozen_models/
    2. score_frozen(model_id, df_new)
       â†’ returns predictions for data AFTER train_cutoff
    3. evaluate_frozen(model_id, df_with_materialized_labels)
       â†’ compares predictions vs labels that have now materialized
    4. list_frozen_models() / load_frozen_model(model_id)
       â†’ registry operations
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
import pandas as pd


FROZEN_DIR_NAME = "frozen_models"


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
    model_path: Path
    metadata_path: Path


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
    artifact_dir: Path = Path("artifacts"),
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
    now_utc = datetime.now(timezone.utc)
    timestamp = now_utc.strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    model_id = f"frozen_{timestamp}_{short_uuid}"

    model_dir = _frozen_base_dir(artifact_dir) / model_id
    model_dir.mkdir(parents=True, exist_ok=True)

    model_path = model_dir / "model.joblib"
    metadata_path = model_dir / "metadata.json"

    joblib.dump(model, model_path)

    cutoff_str = (
        train_cutoff.isoformat() if hasattr(train_cutoff, "isoformat")
        else str(train_cutoff)
    )

    metadata = {
        "model_id": model_id,
        "freeze_time": now_utc.isoformat(),
        "train_cutoff": cutoff_str,
        "threshold": float(threshold),
        "feature_cols": list(feature_cols),
        "config": config,
        "training_stats": training_stats or {},
        "label_spec": {
            "horizon_minutes": 1440,
            "target_drawdown": 0.08,
            "max_ae": 0.04,
        },
    }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    return FrozenModelInfo(
        model_id=model_id,
        freeze_time=metadata["freeze_time"],
        train_cutoff=cutoff_str,
        threshold=float(threshold),
        feature_cols=list(feature_cols),
        config=config,
        training_stats=training_stats or {},
        model_path=model_path,
        metadata_path=metadata_path,
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
    return FrozenModelInfo(
        model_id=metadata["model_id"],
        freeze_time=metadata["freeze_time"],
        train_cutoff=metadata["train_cutoff"],
        threshold=metadata["threshold"],
        feature_cols=metadata["feature_cols"],
        config=metadata["config"],
        training_stats=metadata.get("training_stats", {}),
        model_path=model_dir / "model.joblib",
        metadata_path=metadata_path,
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
            models.append(FrozenModelInfo(
                model_id=m["model_id"],
                freeze_time=m["freeze_time"],
                train_cutoff=m["train_cutoff"],
                threshold=m["threshold"],
                feature_cols=m["feature_cols"],
                config=m["config"],
                training_stats=m.get("training_stats", {}),
                model_path=d / "model.joblib",
                metadata_path=meta,
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

    # Ensure all expected feature columns exist; fill missing with 0
    for col in info.feature_cols:
        if col not in work.columns:
            work[col] = 0.0

    X = work[info.feature_cols].fillna(0)

    # Get probabilities
    if hasattr(model, "predict_proba") and len(getattr(model, "classes_", [])) > 1:
        proba = model.predict_proba(X)[:, 1]
    else:
        proba = np.zeros(len(work))

    threshold = info.threshold
    horizon_minutes = 1440

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
    from sklearn.metrics import precision_score, recall_score, brier_score_loss

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

    # Score
    for col in info.feature_cols:
        if col not in work.columns:
            work[col] = 0.0
    X = work[info.feature_cols].fillna(0)

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
