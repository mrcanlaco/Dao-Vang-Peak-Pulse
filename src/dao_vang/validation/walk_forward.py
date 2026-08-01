from typing import Any, Callable, Dict, List, Tuple

from dao_vang.baselines.logistic import LogisticRegressionSGD, StandardScaler
from dao_vang.validation.calibration import brier_score, expected_calibration_error
from dao_vang.validation.metrics import calculate_row_metrics
from dao_vang.validation.splits import SplitBounds, WalkForwardFold

# fetch_data_fn(bounds) -> X, y
FetchDataFn = Callable[[SplitBounds], Tuple[List[List[float]], List[bool]]]


def run_walk_forward_logistic(
    folds: List[WalkForwardFold],
    fetch_data_fn: FetchDataFn,
    threshold: float = 0.5,
    lr: float = 0.01,
    epochs: int = 100,
    l2_lambda: float = 0.0,
) -> Dict[str, Any]:
    """
    Run Logistic Regression across walk-forward folds.

    For each fold:
    1. Fetches Train data, fits Scaler, fits LogisticRegressionSGD.
    2. Fetches Test data, transforms via Scaler, predicts probabilities.
    3. Calculates per-fold metrics.

    Aggregates all Test predictions across folds to calculate aggregate metrics.
    """
    per_fold_results: List[Dict[str, Any]] = []

    all_test_true: List[bool] = []
    all_test_prob: List[float] = []
    all_test_pred: List[bool] = []

    for fold in folds:
        # Fetch train data
        X_train, y_train = fetch_data_fn(fold.train)

        if not X_train:
            continue

        # Fit scaler
        scaler = StandardScaler()
        scaler.fit(X_train)
        X_train_scaled = scaler.transform(X_train)

        # Fit model
        model = LogisticRegressionSGD(
            learning_rate=lr, epochs=epochs, l2_lambda=l2_lambda
        )
        model.fit(X_train_scaled, y_train)

        # Fetch test data
        X_test, y_test = fetch_data_fn(fold.test)

        if not X_test:
            # Skip evaluation if test set is empty
            continue

        X_test_scaled = scaler.transform(X_test)

        # Predict on test
        y_prob = model.predict_proba(X_test_scaled)
        y_pred = [p > threshold for p in y_prob]

        # Collect for aggregate
        all_test_true.extend(y_test)
        all_test_prob.extend(y_prob)
        all_test_pred.extend(y_pred)

        # Calculate per-fold metrics
        fold_row_metrics = calculate_row_metrics(y_true=y_test, y_pred=y_pred)
        fold_brier = brier_score(y_true=y_test, y_prob=y_prob)
        fold_ece = expected_calibration_error(y_true=y_test, y_prob=y_prob)

        per_fold_results.append(
            {
                "fold_idx": fold.fold_idx,
                "metrics": {
                    "precision": fold_row_metrics.precision,
                    "recall": fold_row_metrics.recall,
                    "false_positive_rate": fold_row_metrics.fpr,
                    "brier_score": fold_brier,
                    "expected_calibration_error": fold_ece,
                },
            }
        )

    aggregate_metrics: Dict[str, float] = {}
    if all_test_true:
        agg_row = calculate_row_metrics(y_true=all_test_true, y_pred=all_test_pred)
        agg_brier = brier_score(y_true=all_test_true, y_prob=all_test_prob)
        agg_ece = expected_calibration_error(y_true=all_test_true, y_prob=all_test_prob)

        aggregate_metrics = {
            "precision": agg_row.precision,
            "recall": agg_row.recall,
            "false_positive_rate": agg_row.fpr,
            "brier_score": agg_brier,
            "expected_calibration_error": agg_ece,
        }

    return {"per_fold": per_fold_results, "aggregate": aggregate_metrics}
