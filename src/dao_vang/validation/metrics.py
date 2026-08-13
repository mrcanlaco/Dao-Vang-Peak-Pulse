"""Leakage-safe metrics used by research and release evaluation.

The functions in this module deliberately operate on materialised labels and
out-of-sample predictions.  They do not infer missing outcomes as negatives;
callers must resolve labels before invoking them.  Event metrics collapse all
rows belonging to one event so a long run of candles cannot inflate a score.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

try:  # pandas is a project dependency, but keep the type import optional.
    import pandas as pd
except ImportError:  # pragma: no cover - only useful for minimal tooling.
    pd = None  # type: ignore[assignment]

from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    f1_score,
    precision_score,
    recall_score,
)


def _as_arrays(
    y_true: Sequence[Any], y_prob: Sequence[Any]
) -> tuple[np.ndarray, np.ndarray]:
    """Validate and convert labels/probabilities without silently coercing NaN."""

    actual = np.asarray(y_true, dtype=float)
    probability = np.asarray(y_prob, dtype=float)
    if actual.ndim != 1 or probability.ndim != 1:
        raise ValueError("y_true and y_prob must be one-dimensional")
    if len(actual) == 0:
        raise ValueError("y_true and y_prob cannot be empty")
    if len(actual) != len(probability):
        raise ValueError("y_true and y_prob must have the same length")
    if not np.isfinite(actual).all() or not np.isfinite(probability).all():
        raise ValueError("y_true and y_prob must contain finite values")
    if not np.isin(actual, [0.0, 1.0]).all():
        raise ValueError("y_true must contain only binary 0/1 values")
    if ((probability < 0.0) | (probability > 1.0)).any():
        raise ValueError("y_prob must be between 0 and 1")
    return actual.astype(int), probability


def compute_row_metrics(
    y_true: Sequence[Any],
    y_prob: Sequence[Any],
    threshold: float = 0.5,
) -> dict[str, float]:
    """Return row-level classification and probability metrics.

    ``threshold`` is an input policy.  This function never selects a
    threshold, which is important because selecting one on the test fold is
    leakage.  PR-AUC is reported as ``0`` when the fold has one class rather
    than producing an exception; the caller still gets ``n_positive`` to
    decide whether the fold is usable.
    """

    if not np.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    actual, probability = _as_arrays(y_true, y_prob)
    predicted = (probability >= threshold).astype(int)
    positives = int(actual.sum())
    predicted_positives = int(predicted.sum())
    true_positive = int(((actual == 1) & (predicted == 1)).sum())
    false_positive = int(((actual == 0) & (predicted == 1)).sum())
    true_negative = int(((actual == 0) & (predicted == 0)).sum())
    false_negative = int(((actual == 1) & (predicted == 0)).sum())

    return {
        "n_rows": float(len(actual)),
        "n_positive": float(positives),
        "n_predicted_positive": float(predicted_positives),
        "precision": float(precision_score(actual, predicted, zero_division=0)),
        "recall": float(recall_score(actual, predicted, zero_division=0)),
        "f1": float(f1_score(actual, predicted, zero_division=0)),
        "pr_auc": float(
            average_precision_score(actual, probability)
            if np.unique(actual).size > 1
            else 0.0
        ),
        "brier_score": float(brier_score_loss(actual, probability)),
        "false_positive_rate": float(
            false_positive / (false_positive + true_negative)
            if false_positive + true_negative
            else 0.0
        ),
        "threshold": float(threshold),
        # Counts are useful in reports, but use integer values for JSON
        # consumers even though the metric type is float-compatible.
        "tp": float(true_positive),
        "fp": float(false_positive),
        "fn": float(false_negative),
    }


def compute_expected_calibration_error(
    y_true: Sequence[Any], y_prob: Sequence[Any], n_bins: int = 10
) -> float:
    """Compute uniform-bin expected calibration error (ECE).

    Values equal to ``1.0`` are explicitly assigned to the final bin; the
    previous implementation silently dropped those values.
    """

    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
    actual, probability = _as_arrays(y_true, y_prob)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_ids = np.searchsorted(bins, probability, side="right") - 1
    bin_ids = np.clip(bin_ids, 0, n_bins - 1)
    ece = 0.0
    for index in range(n_bins):
        mask = bin_ids == index
        if mask.any():
            ece += float(mask.mean()) * abs(
                float(probability[mask].mean()) - float(actual[mask].mean())
            )
    return float(ece)


def reliability_table(
    y_true: Sequence[Any], y_prob: Sequence[Any], n_bins: int = 10
) -> list[dict[str, float | int]]:
    """Return a serialisable reliability table for non-empty probability bins."""

    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
    actual, probability = _as_arrays(y_true, y_prob)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_ids = np.searchsorted(bins, probability, side="right") - 1
    bin_ids = np.clip(bin_ids, 0, n_bins - 1)
    rows: list[dict[str, float | int]] = []
    for index in range(n_bins):
        mask = bin_ids == index
        if mask.any():
            rows.append(
                {
                    "bin": index,
                    "lower": float(bins[index]),
                    "upper": float(bins[index + 1]),
                    "count": int(mask.sum()),
                    "mean_predicted": float(probability[mask].mean()),
                    "fraction_positive": float(actual[mask].mean()),
                }
            )
    return rows


def _event_frame(predictions: Any) -> Any:
    """Validate the event columns and return a copy with deterministic order."""

    if pd is None or not isinstance(predictions, pd.DataFrame):
        raise TypeError("predictions must be a pandas DataFrame")
    required = {"event_id", "label_value", "pred_value"}
    missing = sorted(required - set(predictions.columns))
    if missing:
        raise ValueError(f"predictions is missing columns: {', '.join(missing)}")
    frame = predictions.copy()
    frame = frame[frame["label_value"].notna()].copy()
    frame["label_value"] = frame["label_value"].astype(int)
    frame["pred_value"] = frame["pred_value"].astype(int)
    if (~frame["label_value"].isin([0, 1])).any() or (
        ~frame["pred_value"].isin([0, 1])
    ).any():
        raise ValueError("label_value and pred_value must be binary")
    return frame


def compute_event_metrics(predictions_df: Any) -> dict[str, float | int]:
    """Compute event-level precision/recall, duplicates and lead-time quantiles.

    Positive rows with the same ``event_id`` count as one event.  Rows with a
    missing event ID are retained as row-level false alerts but cannot be
    credited as a caught event.  ``signal_time``/``target_time`` are optional;
    if absent, lead-time metrics are reported as ``None`` in the detailed
    fields and ``0`` in the legacy median field.
    """

    frame = _event_frame(predictions_df)
    if frame.empty:
        return {
            "n_events": 0,
            "n_true_events": 0,
            "n_predicted_events": 0,
            "event_precision": 0.0,
            "event_recall": 0.0,
            "false_alerts_per_event": 0.0,
            "duplicate_ratio": 0.0,
            "lead_time_minutes": {"p25": None, "median": None, "p75": None},
            "median_lead_time": 0.0,
        }

    # Null IDs are deliberately assigned a unique synthetic ID per predicted
    # row.  This counts an unassociated alert as a false event instead of
    # dropping it from precision.
    ids = frame["event_id"].astype(object)
    null_counter = 0
    normalized_ids: list[str] = []
    for value in ids:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            normalized_ids.append(f"__unresolved_alert_{null_counter}")
            null_counter += 1
        else:
            normalized_ids.append(str(value))
    frame["_event_key"] = normalized_ids

    events = frame.groupby("_event_key", sort=True).agg(
        label_value=("label_value", "max"),
        pred_value=("pred_value", "max"),
        n_rows=("pred_value", "size"),
    )
    event_actual = events["label_value"].astype(int).to_numpy()
    event_predicted = events["pred_value"].astype(int).to_numpy()
    tp = int(((event_actual == 1) & (event_predicted == 1)).sum())
    fp = int(((event_actual == 0) & (event_predicted == 1)).sum())
    fn = int(((event_actual == 1) & (event_predicted == 0)).sum())
    true_events = int((event_actual == 1).sum())
    predicted_events = int((event_predicted == 1).sum())
    predicted_rows = int(frame["pred_value"].sum())
    duplicate_ratio = (
        float((predicted_rows - predicted_events) / predicted_rows)
        if predicted_rows
        else 0.0
    )

    lead_values: list[float] = []
    if "lead_time_minutes" in frame.columns:
        lead_values = [
            float(v)
            for v in frame.loc[
                (frame["pred_value"] == 1) & (frame["label_value"] == 1),
                "lead_time_minutes",
            ]
            .dropna()
            .tolist()
            if np.isfinite(float(v)) and float(v) >= 0.0
        ]
    if not lead_values and {"signal_time", "target_time"}.issubset(frame.columns):
        signal = pd.to_datetime(frame["signal_time"], errors="coerce", utc=True)
        target = pd.to_datetime(frame["target_time"], errors="coerce", utc=True)
        derived = (target - signal).dt.total_seconds() / 60.0
        lead_values = [
            float(v)
            for v in derived[
                (frame["pred_value"] == 1) & (frame["label_value"] == 1)
            ].dropna()
            if np.isfinite(float(v)) and float(v) >= 0.0
        ]
    lead_stats: dict[str, float | None] = {
        "p25": float(np.percentile(lead_values, 25)) if lead_values else None,
        "median": float(np.percentile(lead_values, 50)) if lead_values else None,
        "p75": float(np.percentile(lead_values, 75)) if lead_values else None,
    }
    return {
        "n_events": int(len(events)),
        "n_true_events": true_events,
        "n_predicted_events": predicted_events,
        "event_precision": float(tp / (tp + fp)) if tp + fp else 0.0,
        "event_recall": float(tp / (tp + fn)) if tp + fn else 0.0,
        "false_alerts_per_event": float(fp / true_events) if true_events else 0.0,
        "duplicate_ratio": duplicate_ratio,
        "lead_time_minutes": lead_stats,
        # Keep this key for existing dashboards/tests.
        "median_lead_time": float(lead_stats["median"] or 0.0),
    }


# Backwards/forwards compatible spelling used by some report consumers.
compute_ece = compute_expected_calibration_error
