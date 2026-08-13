"""Sprint 4 model and calibration contracts."""

import numpy as np
import pandas as pd
import pytest

from dao_vang.experiments.calibration import (
    calibration_report,
    fit_probability_calibrator,
)
from dao_vang.experiments.models import (
    fit_model_for_horizon,
    fit_models_by_horizon,
    predict_horizon_probabilities,
)


def _data(seed: int = 5, n: int = 180) -> tuple[pd.DataFrame, pd.Series]:
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame(
        {"price": rng.normal(size=n), "funding": rng.normal(size=n)}
    )
    labels = pd.Series((frame["price"] + frame["funding"] > 0).astype(int))
    return frame, labels


def test_models_are_independent_per_horizon() -> None:
    X, y = _data()
    models = fit_models_by_horizon(
        X.iloc[:120], {6: y.iloc[:120], "12h": y.iloc[:120], 24: y.iloc[:120]}
    )
    assert tuple(models) == (6, 12, 24)
    assert {bundle.horizon_hours for bundle in models.values()} == {6, 12, 24}
    probabilities = predict_horizon_probabilities(models, X.iloc[120:])
    assert list(probabilities.columns) == [
        "probability_6h",
        "probability_12h",
        "probability_24h",
    ]
    assert probabilities.shape == (60, 3)
    assert ((probabilities.to_numpy() >= 0.0) & (probabilities.to_numpy() <= 1.0)).all()


def test_calibration_uses_separate_set_and_emits_report() -> None:
    X, y = _data()
    bundle = fit_model_for_horizon(
        X.iloc[:100],
        y.iloc[:100],
        6,
        X_calibration=X.iloc[100:140],
        y_calibration=y.iloc[100:140],
        calibration_method="platt",
    )
    assert bundle.calibration_method == "platt"
    assert bundle.calibrator is not None
    raw = bundle.predict_raw_proba(X.iloc[140:])
    calibrated = bundle.predict_proba(X.iloc[140:])
    report = calibration_report(y.iloc[140:], raw, calibrated)
    assert report["n_rows"] == 40
    assert 0.0 <= report["ece"] <= 1.0


@pytest.mark.parametrize("method", ["isotonic", "platt", "sigmoid"])
def test_probability_calibrator_methods_are_bounded(method: str) -> None:
    raw = np.linspace(0.01, 0.99, 40)
    y = (raw > 0.55).astype(int)
    calibrator = fit_probability_calibrator(raw, y, method=method)
    values = calibrator.transform([0.0, 0.5, 1.0])
    assert values.shape == (3,)
    assert np.isfinite(values).all()
    assert ((values >= 0.0) & (values <= 1.0)).all()


def test_calibrator_rejects_single_class_calibration_set() -> None:
    with pytest.raises(ValueError, match="both classes"):
        fit_probability_calibrator([0.1, 0.2], [0, 0])
