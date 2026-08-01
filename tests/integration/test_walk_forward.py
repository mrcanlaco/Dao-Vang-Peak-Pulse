from datetime import datetime, timedelta
from typing import List, Tuple

from dao_vang.validation.splits import SplitBounds, WalkForwardFold
from dao_vang.validation.walk_forward import run_walk_forward_logistic


def dummy_fetch_data_fn(bounds: SplitBounds) -> Tuple[List[List[float]], List[bool]]:
    """
    Mock fetch function.
    Returns dummy features and labels based on the duration of the bounds.
    """
    duration_days = (bounds.end_time - bounds.start_time).days

    # Just generate some dummy data for each day in the bounds
    X: List[List[float]] = []
    y: List[bool] = []

    for i in range(duration_days):
        # Create dummy deterministic data
        feature1 = float(i % 10)
        feature2 = float(i % 5)
        label = (i % 3) == 0  # True every 3rd day

        X.append([feature1, feature2])
        y.append(label)

    return X, y


def test_run_walk_forward_logistic():
    # Construct some dummy folds
    base_time = datetime(2023, 1, 1)

    fold0 = WalkForwardFold(
        fold_idx=0,
        train=SplitBounds(
            start_time=base_time, end_time=base_time + timedelta(days=90)
        ),
        validation=SplitBounds(
            start_time=base_time + timedelta(days=91),
            end_time=base_time + timedelta(days=120),
        ),
        test=SplitBounds(
            start_time=base_time + timedelta(days=121),
            end_time=base_time + timedelta(days=150),
        ),
    )

    fold1 = WalkForwardFold(
        fold_idx=1,
        train=SplitBounds(
            start_time=base_time + timedelta(days=30),
            end_time=base_time + timedelta(days=120),
        ),
        validation=SplitBounds(
            start_time=base_time + timedelta(days=121),
            end_time=base_time + timedelta(days=150),
        ),
        test=SplitBounds(
            start_time=base_time + timedelta(days=151),
            end_time=base_time + timedelta(days=180),
        ),
    )

    folds = [fold0, fold1]

    results = run_walk_forward_logistic(
        folds=folds,
        fetch_data_fn=dummy_fetch_data_fn,
        threshold=0.5,
        lr=0.01,
        epochs=10,
        l2_lambda=0.0,
    )

    # Assert return structure
    assert "per_fold" in results
    assert "aggregate" in results

    per_fold = results["per_fold"]
    assert len(per_fold) == 2

    # Assert fold 0
    assert per_fold[0]["fold_idx"] == 0
    assert "precision" in per_fold[0]["metrics"]
    assert "brier_score" in per_fold[0]["metrics"]

    # Assert fold 1
    assert per_fold[1]["fold_idx"] == 1

    # Assert aggregate
    agg = results["aggregate"]
    assert "precision" in agg
    assert "brier_score" in agg
    assert "expected_calibration_error" in agg


def test_walk_forward_empty_data():
    def empty_fetch(bounds: SplitBounds) -> Tuple[List[List[float]], List[bool]]:
        return [], []

    fold = WalkForwardFold(
        fold_idx=0,
        train=SplitBounds(
            start_time=datetime(2023, 1, 1), end_time=datetime(2023, 2, 1)
        ),
        validation=SplitBounds(
            start_time=datetime(2023, 2, 2), end_time=datetime(2023, 3, 1)
        ),
        test=SplitBounds(
            start_time=datetime(2023, 3, 2), end_time=datetime(2023, 4, 1)
        ),
    )

    results = run_walk_forward_logistic(folds=[fold], fetch_data_fn=empty_fetch)

    # Per fold should be empty since train data is empty (skipped)
    assert len(results["per_fold"]) == 0
    # Aggregate should be empty
    assert results["aggregate"] == {}
