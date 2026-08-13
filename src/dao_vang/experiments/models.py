"""Model adapters used by the two-stage distribution pipeline.

The project deliberately keeps model construction in one small module.  The
helpers below do not select a model from the test set and they never fit an
imputer on data outside the set supplied by the caller.  A horizon is part of
the model identity: a 6h model is not silently reused for a 12h or 24h label.

The original ``get_*`` and ``build_model`` functions are kept for backwards
compatibility with the experiment UI.  New code should use
``fit_model_for_horizon`` or ``fit_models_by_horizon``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.base import ClassifierMixin
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from dao_vang.experiments.calibration import CalibratedModel, calibrate_model

SUPPORTED_HORIZONS: tuple[int, ...] = (6, 12, 24)
SUPPORTED_MODEL_NAMES: tuple[str, ...] = ("logistic_regression", "lightgbm")


def get_logistic_regression(random_state: int = 42) -> LogisticRegression:
    """Return the reproducible baseline classifier.

    Class balancing is intentionally not enabled here.  It changes the prior
    probability and makes calibration unnecessarily difficult.  If a study
    needs class weighting it must be recorded in the experiment config.
    """

    return LogisticRegression(
        random_state=random_state,
        max_iter=1000,
    )


def get_lightgbm(random_state: int = 42) -> lgb.LGBMClassifier:
    """Return the deterministic challenger classifier."""

    return lgb.LGBMClassifier(
        random_state=random_state,
        n_estimators=200,
        learning_rate=0.05,
        max_depth=5,
        num_leaves=31,
        subsample=0.8,
        colsample_bytree=0.8,
        deterministic=True,
        force_col_wise=True,
        verbosity=-1,
    )


def build_model(model_name: str, random_state: int = 42) -> Any:
    """Build a supported estimator by stable name."""

    normalized = model_name.strip().lower().replace("-", "_")
    if normalized in {"logreg", "logistic", "logistic_regression"}:
        return get_logistic_regression(random_state)
    if normalized in {"lgbm", "lightgbm"}:
        return get_lightgbm(random_state)
    raise ValueError(
        f"Unknown model_name={model_name!r}; expected one of {SUPPORTED_MODEL_NAMES}"
    )


def _horizon_key(value: int | str) -> int:
    """Normalize ``6``, ``"6h"`` and ``"horizon_6"`` to an integer."""

    text = str(value).strip().lower().replace("horizon_", "").rstrip("h")
    try:
        horizon = int(text)
    except ValueError as exc:
        raise ValueError(f"Invalid horizon {value!r}") from exc
    if horizon not in SUPPORTED_HORIZONS:
        raise ValueError(
            f"Unsupported horizon {horizon}h; expected {SUPPORTED_HORIZONS}"
        )
    return horizon


@dataclass
class HorizonModelBundle:
    """Estimator and optional calibration artifact for one horizon.

    ``estimator`` includes the fitted imputer.  ``calibrator`` consumes the
    estimator's positive-class probabilities and is fit only when the caller
    supplies a separate calibration set.
    """

    horizon_hours: int
    model_name: str
    estimator: ClassifierMixin
    feature_cols: tuple[str, ...]
    training_rows: int
    positive_rows: int
    calibrator: CalibratedModel | None = None
    calibration_method: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def model_id_suffix(self) -> str:
        return f"{self.model_name}_h{self.horizon_hours}"

    def predict_raw_proba(self, features: pd.DataFrame) -> np.ndarray:
        """Predict the estimator probability without calibration."""

        if not isinstance(features, pd.DataFrame):
            raise TypeError("features must be a pandas DataFrame")
        missing_columns = [
            column
            for column in self.feature_cols
            if column not in features.columns or features[column].isna().any()
        ]
        if missing_columns:
            raise ValueError(
                "missing required serving features: " + ", ".join(missing_columns)
            )
        features = features.loc[:, list(self.feature_cols)]
        if not hasattr(self.estimator, "predict_proba"):
            predictions = np.asarray(self.estimator.predict(features), dtype=float)
            return np.clip(predictions, 0.0, 1.0)
        values = np.asarray(self.estimator.predict_proba(features))
        if values.ndim != 2 or values.shape[1] < 2:
            raise ValueError("estimator.predict_proba must return two classes")
        return np.clip(values[:, 1].astype(float), 0.0, 1.0)

    def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
        """Predict calibrated probabilities when a calibrator is present."""

        raw = self.predict_raw_proba(features)
        if self.calibrator is None:
            return raw
        return self.calibrator.transform(raw)

    def to_metadata(self) -> dict[str, Any]:
        """Return JSON-serializable provenance for a frozen bundle."""

        return {
            "horizon_hours": self.horizon_hours,
            "model_name": self.model_name,
            "feature_cols": list(self.feature_cols),
            "training_rows": self.training_rows,
            "positive_rows": self.positive_rows,
            "calibration_method": self.calibration_method,
            "calibrator_id": (
                self.calibrator.calibrator_id if self.calibrator is not None else None
            ),
            "preprocessing": {
                "type": "median_imputer",
                "fit_scope": "train_only",
                "missing_policy": "reject_at_serving",
            },
            **self.metadata,
        }


def _prepare_estimator(
    model_name: str,
    random_state: int,
    *,
    preprocess: bool,
) -> ClassifierMixin:
    estimator = build_model(model_name, random_state)
    if preprocess:
        # ``add_indicator`` preserves the fact that a value was missing while
        # keeping the imputer fit strictly inside the training pipeline.
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                ("estimator", estimator),
            ]
        )  # type: ignore[return-value]
    return estimator


def fit_model_for_horizon(
    X_train: pd.DataFrame,
    y_train: pd.Series | Sequence[int],
    horizon_hours: int,
    *,
    model_name: str = "logistic_regression",
    feature_cols: Sequence[str] | None = None,
    random_state: int = 42,
    X_calibration: pd.DataFrame | None = None,
    y_calibration: pd.Series | Sequence[int] | None = None,
    calibration_method: str | None = None,
    preprocess: bool = True,
) -> HorizonModelBundle:
    """Fit exactly one model for one horizon.

    ``X_calibration``/``y_calibration`` are optional so baseline training can
    be used independently.  If supplied, calibration is fit after estimator
    training and never sees test rows.  Empty or single-class calibration data
    is rejected instead of silently returning an identity probability.
    """

    horizon = _horizon_key(horizon_hours)
    normalized_model = model_name.strip().lower().replace("-", "_")
    if normalized_model not in SUPPORTED_MODEL_NAMES:
        normalized_model = (
            "logistic_regression"
            if normalized_model in {"logreg", "logistic"}
            else "lightgbm"
            if normalized_model in {"lgbm"}
            else normalized_model
        )
    if normalized_model not in SUPPORTED_MODEL_NAMES:
        raise ValueError(f"Unsupported model_name={model_name!r}")

    if not isinstance(X_train, pd.DataFrame) or X_train.empty:
        raise ValueError("X_train must be a non-empty DataFrame")
    y = pd.Series(np.asarray(y_train), index=X_train.index)
    if len(y) != len(X_train):
        raise ValueError("X_train and y_train length mismatch")
    y = pd.to_numeric(y, errors="coerce")
    valid = y.notna()
    X_fit = X_train.loc[valid].copy()
    y_fit = y.loc[valid]
    if not y_fit.isin([0, 1]).all():
        raise ValueError("Training labels must be binary")
    y_fit = y_fit.astype("int64")
    if y_fit.nunique() < 2:
        raise ValueError("Training labels must contain both classes")
    cols = tuple(feature_cols or list(X_fit.columns))
    missing = [column for column in cols if column not in X_fit.columns]
    if missing:
        raise ValueError(f"Missing training features: {missing}")
    X_fit = X_fit.loc[:, list(cols)]

    estimator = _prepare_estimator(
        normalized_model, random_state, preprocess=preprocess
    )
    estimator.fit(X_fit, y_fit)

    calibrator: CalibratedModel | None = None
    resolved_method: str | None = None
    if (X_calibration is None) != (y_calibration is None):
        raise ValueError("X_calibration and y_calibration must be supplied together")
    if X_calibration is not None and y_calibration is not None:
        X_cal = X_calibration.loc[:, list(cols)]
        y_cal = pd.Series(np.asarray(y_calibration), index=X_cal.index)
        if len(X_cal) != len(y_cal):
            raise ValueError("X_calibration and y_calibration length mismatch")
        if y_cal.isna().any():
            raise ValueError("Calibration labels must not contain missing values")
        y_cal = pd.to_numeric(y_cal, errors="raise")
        if not y_cal.isin([0, 1]).all():
            raise ValueError("Calibration labels must be binary")
        y_cal = y_cal.astype("int64")
        raw = _predict_positive_probability(estimator, X_cal)
        calibrator = calibrate_model(
            estimator,
            X_cal,
            y_cal,
            method=calibration_method or "isotonic",
            raw_probabilities=raw,
        )
        resolved_method = calibrator.method

    return HorizonModelBundle(
        horizon_hours=horizon,
        model_name=normalized_model,
        estimator=estimator,
        feature_cols=cols,
        training_rows=len(X_fit),
        positive_rows=int(y_fit.sum()),
        calibrator=calibrator,
        calibration_method=resolved_method,
        metadata={"random_state": random_state},
    )


def _predict_positive_probability(estimator: Any, X: pd.DataFrame) -> np.ndarray:
    if hasattr(estimator, "predict_proba"):
        values = np.asarray(estimator.predict_proba(X))
        if values.ndim == 2 and values.shape[1] >= 2:
            return np.clip(values[:, 1].astype(float), 0.0, 1.0)
    predictions = np.asarray(estimator.predict(X), dtype=float)
    return np.clip(predictions, 0.0, 1.0)


def fit_models_by_horizon(
    X_train: pd.DataFrame,
    labels_by_horizon: Mapping[int | str, pd.Series | Sequence[int]],
    *,
    model_name: str = "logistic_regression",
    feature_cols: Sequence[str] | None = None,
    random_state: int = 42,
    calibration_features: pd.DataFrame | None = None,
    calibration_labels_by_horizon: Mapping[int | str, pd.Series | Sequence[int]]
    | None = None,
    calibration_method: str | Mapping[int | str, str] | None = None,
    preprocess: bool = True,
) -> dict[int, HorizonModelBundle]:
    """Fit independent estimators for every requested 6/12/24h label."""

    if not labels_by_horizon:
        raise ValueError("labels_by_horizon must not be empty")
    normalized_labels = {
        _horizon_key(key): value for key, value in labels_by_horizon.items()
    }
    normalized_cal = (
        {
            _horizon_key(key): value
            for key, value in calibration_labels_by_horizon.items()
        }
        if calibration_labels_by_horizon is not None
        else {}
    )
    bundles: dict[int, HorizonModelBundle] = {}
    for horizon in sorted(normalized_labels):
        method: str | None
        if isinstance(calibration_method, Mapping):
            method = calibration_method.get(horizon) or calibration_method.get(
                str(horizon)
            )
        else:
            method = calibration_method
        bundles[horizon] = fit_model_for_horizon(
            X_train,
            normalized_labels[horizon],
            horizon,
            model_name=model_name,
            feature_cols=feature_cols,
            random_state=random_state,
            X_calibration=calibration_features,
            y_calibration=normalized_cal.get(horizon),
            calibration_method=method,
            preprocess=preprocess,
        )
    return bundles


# Alias used by a few early experiment notebooks.
train_models_by_horizon = fit_models_by_horizon


def predict_horizon_probabilities(
    models: Mapping[int | str, HorizonModelBundle],
    features: pd.DataFrame,
) -> pd.DataFrame:
    """Return calibrated probabilities with stable ``probability_<h>h`` names."""

    result = pd.DataFrame(index=features.index)
    for key, bundle in sorted(models.items(), key=lambda item: _horizon_key(item[0])):
        horizon = _horizon_key(key)
        result[f"probability_{horizon}h"] = bundle.predict_proba(
            features.loc[:, list(bundle.feature_cols)]
        )
    return result
