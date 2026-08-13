"""Leakage-safe probability calibration adapters.

Calibration is a second fit, not a metric calculated on the test fold.  The
public helpers accept probabilities from an already-fitted estimator and a
dedicated calibration set.  This makes the train/calibration/test boundary
explicit and keeps the serialized artifact small and inspectable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

CALIBRATION_METHODS: tuple[str, ...] = ("isotonic", "platt", "sigmoid")


def _normalise_method(method: str) -> str:
    normalized = method.strip().lower().replace("-", "_")
    if normalized == "sigmoid":
        return "platt"
    if normalized not in {"isotonic", "platt"}:
        raise ValueError(
            f"Unsupported calibration method={method!r}; expected 'isotonic' or 'platt'"
        )
    return normalized


def _validate_calibration_data(
    probabilities: Iterable[float], labels: Iterable[int | bool]
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(list(probabilities), dtype=float)
    target = np.asarray(list(labels), dtype=float)
    if values.ndim != 1 or target.ndim != 1 or len(values) != len(target):
        raise ValueError("calibration probabilities and labels must be 1-D and aligned")
    if len(values) < 2:
        raise ValueError("at least two calibration rows are required")
    if not np.isfinite(values).all() or ((values < 0.0) | (values > 1.0)).any():
        raise ValueError("calibration probabilities must be finite and in [0, 1]")
    if not np.isfinite(target).all() or not np.isin(target, [0.0, 1.0]).all():
        raise ValueError("calibration labels must be binary")
    if np.unique(target).size < 2:
        raise ValueError("calibration labels must contain both classes")
    return values, target.astype(int)


@dataclass
class ProbabilityCalibrator:
    """Serializable calibrator mapping raw probabilities to calibrated values."""

    method: str
    fitted: Any
    calibrator_id: str
    n_rows: int
    positive_rows: int

    def transform(self, probabilities: Iterable[float] | float) -> np.ndarray:
        values = np.asarray(
            [probabilities] if np.isscalar(probabilities) else list(probabilities),
            dtype=float,
        )
        if values.ndim != 1 or not np.isfinite(values).all():
            raise ValueError("probabilities must be finite")
        values = np.clip(values, 0.0, 1.0)
        if self.method == "isotonic":
            calibrated = np.asarray(self.fitted.predict(values), dtype=float)
        else:
            calibrated = np.asarray(
                self.fitted.predict_proba(values.reshape(-1, 1))[:, 1], dtype=float
            )
        return np.clip(calibrated, 0.0, 1.0)

    def predict(self, probabilities: Iterable[float] | float) -> np.ndarray:
        """Alias understood by common sklearn-style serving code."""

        return self.transform(probabilities)

    def predict_proba(self, probabilities: Iterable[float] | float) -> np.ndarray:
        """Return a two-column sklearn-compatible probability matrix."""

        values = self.transform(probabilities)
        return np.column_stack([1.0 - values, values])


def fit_probability_calibrator(
    raw_probabilities: Iterable[float],
    y_calibration: Iterable[int | bool],
    *,
    method: str = "isotonic",
    calibrator_id: str | None = None,
) -> ProbabilityCalibrator:
    """Fit isotonic or Platt calibration on a dedicated calibration set."""

    normalized = _normalise_method(method)
    values, target = _validate_calibration_data(raw_probabilities, y_calibration)
    if normalized == "isotonic":
        fitted: Any = IsotonicRegression(
            y_min=0.0, y_max=1.0, out_of_bounds="clip"
        ).fit(values, target)
    else:
        fitted = LogisticRegression(solver="lbfgs", max_iter=1000, random_state=0).fit(
            values.reshape(-1, 1), target
        )
    return ProbabilityCalibrator(
        method=normalized,
        fitted=fitted,
        calibrator_id=calibrator_id or f"{normalized}_v1",
        n_rows=len(values),
        positive_rows=int(target.sum()),
    )


class CalibratedModel:
    """Estimator wrapper that exposes calibrated ``predict_proba``."""

    def __init__(self, estimator: Any, calibrator: ProbabilityCalibrator) -> None:
        self.estimator = estimator
        self.calibrator = calibrator
        self.method = calibrator.method
        self.calibrator_id = calibrator.calibrator_id
        self.classes_ = np.asarray([0, 1])

    def raw_predict_proba(self, X: Any) -> np.ndarray:
        if hasattr(self.estimator, "predict_proba"):
            matrix = np.asarray(self.estimator.predict_proba(X))
            if matrix.ndim == 2 and matrix.shape[1] >= 2:
                return np.clip(matrix[:, 1].astype(float), 0.0, 1.0)
        values = np.asarray(self.estimator.predict(X), dtype=float)
        return np.clip(values, 0.0, 1.0)

    def predict_proba(self, X: Any) -> np.ndarray:
        positive = self.calibrator.transform(self.raw_predict_proba(X))
        return np.column_stack([1.0 - positive, positive])

    def transform(self, probabilities: Any) -> np.ndarray:
        """Transform already-computed raw probabilities.

        This small adapter lets a ``HorizonModelBundle`` keep the complete
        calibrated model while serving either rows or cached raw scores.
        """

        return self.calibrator.transform(probabilities)

    def predict(self, X: Any) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


def calibrate_model(
    model: Any,
    X_cal: Any,
    y_cal: Iterable[int | bool],
    method: str = "isotonic",
    *,
    raw_probabilities: Iterable[float] | None = None,
    calibrator_id: str | None = None,
) -> CalibratedModel:
    """Fit and return a calibrated wrapper around a fitted estimator.

    ``model`` must already be fitted on the training partition.  Supplying
    ``raw_probabilities`` is useful when the caller has cached predictions;
    otherwise this function obtains probabilities from ``model`` on
    ``X_calibration``.  The test partition must never be passed here.
    """

    if raw_probabilities is None:
        if not hasattr(model, "predict_proba"):
            raise ValueError(
                "model must expose predict_proba or raw_probabilities "
                "must be supplied"
            )
        matrix = np.asarray(model.predict_proba(X_cal))
        if matrix.ndim != 2 or matrix.shape[1] < 2:
            raise ValueError("model.predict_proba must return two classes")
        raw_probabilities = matrix[:, 1]
    calibrator = fit_probability_calibrator(
        raw_probabilities,
        y_cal,
        method=method,
        calibrator_id=calibrator_id,
    )
    return CalibratedModel(model, calibrator)


def calibration_report(
    y_true: Iterable[int | bool],
    raw_probabilities: Iterable[float],
    calibrated_probabilities: Iterable[float],
    *,
    n_bins: int = 10,
) -> dict[str, Any]:
    """Return calibration-only metrics and a reliability table.

    The function is descriptive: it does not choose a method or threshold and
    therefore cannot accidentally turn a test fold into a tuning set.
    """

    target = np.asarray(list(y_true), dtype=float)
    raw = np.asarray(list(raw_probabilities), dtype=float)
    calibrated = np.asarray(list(calibrated_probabilities), dtype=float)
    if not (len(target) == len(raw) == len(calibrated)) or len(target) == 0:
        raise ValueError("calibration report inputs must be non-empty and aligned")
    if not np.isfinite(target).all() or not np.isin(target, [0.0, 1.0]).all():
        raise ValueError("calibration report labels must be binary")
    if not np.isfinite(raw).all() or not np.isfinite(calibrated).all():
        raise ValueError("calibration report probabilities must be finite")
    if ((raw < 0.0) | (raw > 1.0)).any() or (
        (calibrated < 0.0) | (calibrated > 1.0)
    ).any():
        raise ValueError("calibration report probabilities must be in [0, 1]")
    target = target.astype(int)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    rows: list[dict[str, float | int]] = []
    for index in range(n_bins):
        left, right = bins[index], bins[index + 1]
        mask = (calibrated >= left) & (
            calibrated <= right if index == n_bins - 1 else calibrated < right
        )
        if not mask.any():
            continue
        rows.append(
            {
                "bin_left": float(left),
                "bin_right": float(right),
                "count": int(mask.sum()),
                "mean_probability": float(calibrated[mask].mean()),
                "observed_rate": float(target[mask].mean()),
            }
        )
    ece = sum(
        row["count"] / len(target) * abs(row["mean_probability"] - row["observed_rate"])
        for row in rows
    )
    return {
        "n_rows": len(target),
        "raw_brier": float(brier_score_loss(target, np.clip(raw, 0.0, 1.0))),
        "calibrated_brier": float(
            brier_score_loss(target, np.clip(calibrated, 0.0, 1.0))
        ),
        "ece": float(ece),
        "reliability": rows,
    }
