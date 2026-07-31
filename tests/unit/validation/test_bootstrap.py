import pytest

from dao_vang.validation.bootstrap import calculate_bootstrap_ci


def dummy_metric(y_true: list[bool], y_pred: list[float]) -> float:
    # A simple metric: mean of the absolute difference
    # So if true is 1 and pred is 1, diff is 0
    total = 0.0
    for t, p in zip(y_true, y_pred):
        val = 1.0 if t else 0.0
        total += abs(val - p)
    return total / len(y_true)


def test_calculate_bootstrap_ci():
    y_true = [True, False, True, False, True, True, False, False, True, False]
    y_pred = [0.9, 0.1, 0.8, 0.2, 0.95, 0.85, 0.3, 0.4, 0.7, 0.1]

    # Deterministic check
    lower1, upper1 = calculate_bootstrap_ci(
        y_true, y_pred, metric_fn=dummy_metric, seed=42
    )
    lower2, upper2 = calculate_bootstrap_ci(
        y_true, y_pred, metric_fn=dummy_metric, seed=42
    )

    assert lower1 == lower2
    assert upper1 == upper2
    assert lower1 <= upper1

    # Boundary tests
    with pytest.raises(ValueError):
        calculate_bootstrap_ci([True], [0.1, 0.2], metric_fn=dummy_metric)

    with pytest.raises(ValueError):
        calculate_bootstrap_ci([], [], metric_fn=dummy_metric)

    with pytest.raises(ValueError):
        calculate_bootstrap_ci(
            [True], [0.1], metric_fn=dummy_metric, confidence_level=1.5
        )

    with pytest.raises(ValueError):
        calculate_bootstrap_ci([True], [0.1], metric_fn=dummy_metric, n_iterations=-1)


def test_bootstrap_perfect_prediction():
    # If the prediction is perfect, the metric is always 0
    # Thus CI should be [0.0, 0.0]
    y_true = [True, False, True]
    y_pred = [1.0, 0.0, 1.0]

    lower, upper = calculate_bootstrap_ci(y_true, y_pred, metric_fn=dummy_metric)
    assert lower == 0.0
    assert upper == 0.0
