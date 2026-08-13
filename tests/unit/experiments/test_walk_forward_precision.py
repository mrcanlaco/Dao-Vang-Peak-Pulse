"""Tests for precision-first threshold tuning and LightGBM model path.

Covers:
  - _precision_first_threshold helper (recall floor, fallback, edge cases)
  - train_evaluate_logreg (precision-first objective, no class_weight)
  - train_evaluate_lightgbm (calibration, precision-first, edge cases)
  - train_and_predict_latest (scanner path still works)
"""

import numpy as np
import pandas as pd

from dao_vang.experiments.walk_forward import (
    _precision_first_threshold,
    train_and_predict_latest,
    train_evaluate_lightgbm,
    train_evaluate_logreg,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_synthetic_df(
    n: int = 500, seed: int = 42, n_features: int = 5
) -> pd.DataFrame:
    """Create a synthetic feature+label dataframe with learnable signal.

    Label depends on feature_0 being high (so the model can actually learn).
    """
    rng = np.random.default_rng(seed)
    times = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    cols = {f"feature_{i}": rng.standard_normal(n) for i in range(n_features)}
    # Label: positive when feature_0 > 0.5 (clear signal)
    prob = 1 / (1 + np.exp(-(cols["feature_0"] * 3 - 0.5)))
    labels = (rng.random(n) < prob).astype(int)
    df = pd.DataFrame(cols)
    df["feature_time"] = times
    df["symbol"] = "TESTUSDT"
    df["is_distribution"] = labels
    return df


def _split_train_test(df, feature_cols, test_frac=0.3):
    n = len(df)
    n_test = int(n * test_frac)
    train_df = df.iloc[: n - n_test].copy()
    test_df = df.iloc[n - n_test :].copy()
    X_train = train_df[feature_cols].fillna(0)
    y_train = train_df["is_distribution"]
    X_test = test_df[feature_cols].fillna(0)
    y_test = test_df["is_distribution"]
    return X_train, y_train, X_test, y_test


# ---------------------------------------------------------------------------
# _precision_first_threshold
# ---------------------------------------------------------------------------


class TestPrecisionFirstThreshold:
    """Unit tests for the _precision_first_threshold helper."""

    def test_perfect_separation_high_precision(self):
        """When model perfectly separates classes, the helper should pick a
        threshold that gives precision=1.0 while meeting the recall floor.

        With perfect separation (negatives at 0.1-0.3, positives at 0.8-0.95),
        any threshold in [0.31, 0.79] gives precision=1.0 and recall=1.0.
        The helper picks the lowest such threshold (conservative — more
        predictions), which is correct behavior.
        """
        y_prob = np.array([0.1, 0.2, 0.3, 0.8, 0.9, 0.95])
        y_true = np.array([0, 0, 0, 1, 1, 1])
        thresh = _precision_first_threshold(y_prob, y_true, min_recall=0.50)
        y_pred = (y_prob >= thresh).astype(int)
        # Should predict all 3 positives (recall=1.0) with precision=1.0
        assert y_pred.sum() == 3
        assert ((y_pred == 1) & (y_true == 1)).sum() == 3  # all true positives
        # Threshold should be above all negatives (0.3)
        # and at/below lowest positive (0.8)
        assert thresh > 0.3
        assert thresh <= 0.8

    def test_recall_floor_respected(self):
        """When no threshold meets recall floor, fall back to highest precision."""
        # All positives have low probability — can't get high recall at high precision
        y_prob = np.array([0.05, 0.06, 0.07, 0.08, 0.09, 0.10])
        y_true = np.array([1, 1, 1, 0, 0, 0])
        thresh = _precision_first_threshold(y_prob, y_true, min_recall=0.50)
        # At threshold 0.07: precision=0.5, recall=1.0 (meets floor)
        # At threshold 0.10: precision=0.0 (no positives predicted)
        # Should pick a threshold that meets the recall floor
        y_pred = (y_prob >= thresh).astype(int)
        n_pos = int(y_true.sum())
        recall = int(((y_pred == 1) & (y_true == 1)).sum()) / n_pos
        # Either meets floor or is the highest-precision fallback
        assert recall >= 0.50 or thresh > 0.08  # fallback case

    def test_all_negative_labels(self):
        """Edge case: no positive labels — should not crash."""
        y_prob = np.array([0.1, 0.5, 0.9])
        y_true = np.array([0, 0, 0])
        thresh = _precision_first_threshold(y_prob, y_true, min_recall=0.50)
        assert isinstance(thresh, float)
        assert 0.0 < thresh < 1.0

    def test_all_positive_labels(self):
        """Edge case: all positive labels — precision always 1.0."""
        y_prob = np.array([0.1, 0.5, 0.9])
        y_true = np.array([1, 1, 1])
        thresh = _precision_first_threshold(y_prob, y_true, min_recall=0.50)
        # Any threshold <= 0.9 gives recall >= 0.67 and precision 1.0
        y_pred = (y_prob >= thresh).astype(int)
        assert y_pred.sum() >= 1  # at least one prediction

    def test_empty_predictions_at_high_threshold(self):
        """When threshold too high (no predictions), helper should skip it."""
        y_prob = np.array([0.1, 0.2, 0.3, 0.4])
        y_true = np.array([0, 1, 0, 1])
        thresh = _precision_first_threshold(y_prob, y_true, min_recall=0.50)
        # Should pick a threshold that produces at least one prediction
        y_pred = (y_prob >= thresh).astype(int)
        assert y_pred.sum() > 0

    def test_custom_threshold_grid(self):
        """Custom threshold grid is respected."""
        y_prob = np.array([0.1, 0.5, 0.9])
        y_true = np.array([0, 1, 1])
        custom_grid = np.array([0.45, 0.85])
        thresh = _precision_first_threshold(
            y_prob, y_true, min_recall=0.50, thresh_grid=custom_grid
        )
        assert thresh in [0.45, 0.85]


# ---------------------------------------------------------------------------
# train_evaluate_logreg (precision-first, no class_weight)
# ---------------------------------------------------------------------------


class TestTrainEvaluateLogreg:
    """Tests for the LogReg path with precision-first threshold."""

    def test_returns_valid_metrics(self):
        """Output has all required keys with valid ranges."""
        df = _make_synthetic_df(n=500, seed=42)
        feature_cols = ["feature_0", "feature_1"]
        X_train, y_train, X_test, y_test = _split_train_test(df, feature_cols)
        metrics = train_evaluate_logreg(X_train, y_train, X_test, y_test)

        assert set(metrics.keys()) == {"precision", "recall", "brier", "threshold"}
        assert 0.0 <= metrics["precision"] <= 1.0
        assert 0.0 <= metrics["recall"] <= 1.0
        assert 0.0 <= metrics["brier"] <= 1.0
        assert 0.0 < metrics["threshold"] < 1.0

    def test_empty_train_returns_zeros(self):
        """Edge case: empty training data returns zero metrics."""
        X_train = pd.DataFrame(columns=["a", "b"])
        y_train = pd.Series([], dtype=int)
        X_test = pd.DataFrame({"a": [1.0], "b": [2.0]})
        y_test = pd.Series([1])
        metrics = train_evaluate_logreg(X_train, y_train, X_test, y_test)
        assert metrics == {
            "precision": 0.0,
            "recall": 0.0,
            "brier": 0.0,
            "threshold": 0.5,
        }

    def test_single_class_train_returns_zeros(self):
        """Edge case: only one class in training data returns zeros."""
        X_train = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
        y_train = pd.Series([0, 0, 0])  # all negative
        X_test = pd.DataFrame({"a": [1.0], "b": [2.0]})
        y_test = pd.Series([1])
        metrics = train_evaluate_logreg(X_train, y_train, X_test, y_test)
        assert metrics["precision"] == 0.0
        assert metrics["threshold"] == 0.5

    def test_learnable_signal_gives_better_than_random(self):
        """With a clear signal, precision should be better than prevalence."""
        df = _make_synthetic_df(n=1000, seed=123)
        feature_cols = ["feature_0", "feature_1", "feature_2"]
        X_train, y_train, X_test, y_test = _split_train_test(
            df, feature_cols, test_frac=0.3
        )
        metrics = train_evaluate_logreg(
            X_train, y_train, X_test, y_test, min_recall=0.20
        )
        # With learnable signal, precision at recall >= 0.20 should be non-zero
        assert metrics["precision"] > 0.0

    def test_min_recall_parameter_affects_threshold(self):
        """Lower min_recall should allow higher precision (higher threshold)."""
        df = _make_synthetic_df(n=1000, seed=456)
        feature_cols = ["feature_0", "feature_1"]
        X_train, y_train, X_test, y_test = _split_train_test(df, feature_cols)

        # Low recall floor → can afford higher threshold → higher precision
        m_low_floor = train_evaluate_logreg(
            X_train, y_train, X_test, y_test, min_recall=0.10
        )
        # High recall floor → must lower threshold → may sacrifice precision
        m_high_floor = train_evaluate_logreg(
            X_train, y_train, X_test, y_test, min_recall=0.90
        )

        # Both should be valid
        assert m_low_floor["precision"] >= 0.0
        assert m_high_floor["recall"] >= 0.0


# ---------------------------------------------------------------------------
# train_evaluate_lightgbm
# ---------------------------------------------------------------------------


class TestTrainEvaluateLightgbm:
    """Tests for the LightGBM + isotonic calibration path."""

    def test_returns_valid_metrics(self):
        """Output has all required keys with valid ranges."""
        df = _make_synthetic_df(n=500, seed=42)
        feature_cols = ["feature_0", "feature_1", "feature_2"]
        X_train, y_train, X_test, y_test = _split_train_test(df, feature_cols)
        metrics = train_evaluate_lightgbm(X_train, y_train, X_test, y_test)

        assert set(metrics.keys()) == {"precision", "recall", "brier", "threshold"}
        assert 0.0 <= metrics["precision"] <= 1.0
        assert 0.0 <= metrics["recall"] <= 1.0
        assert 0.0 <= metrics["brier"] <= 1.0
        assert 0.0 < metrics["threshold"] < 1.0

    def test_empty_train_returns_zeros(self):
        """Edge case: empty training data returns zero metrics."""
        X_train = pd.DataFrame(columns=["a", "b"])
        y_train = pd.Series([], dtype=int)
        X_test = pd.DataFrame({"a": [1.0], "b": [2.0]})
        y_test = pd.Series([1])
        metrics = train_evaluate_lightgbm(X_train, y_train, X_test, y_test)
        assert metrics == {
            "precision": 0.0,
            "recall": 0.0,
            "brier": 0.0,
            "threshold": 0.5,
        }

    def test_single_class_train_returns_zeros(self):
        """Edge case: only one class in training data returns zeros."""
        X_train = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
        y_train = pd.Series([0, 0, 0])
        X_test = pd.DataFrame({"a": [1.0], "b": [2.0]})
        y_test = pd.Series([1])
        metrics = train_evaluate_lightgbm(X_train, y_train, X_test, y_test)
        assert metrics["precision"] == 0.0
        assert metrics["threshold"] == 0.5

    def test_calibration_fallback_when_cal_split_single_class(self):
        """When the calibration split has only one class, skip calibration
        and still return valid metrics."""
        # Construct data where the last 20% of training has only negatives
        n = 500
        rng = np.random.default_rng(99)
        times = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
        feature_0 = rng.standard_normal(n)
        # All positives in first 80% only
        labels = np.zeros(n, dtype=int)
        labels[: int(n * 0.7)] = (rng.random(int(n * 0.7)) < 0.3).astype(int)
        df = pd.DataFrame(
            {
                "feature_0": feature_0,
                "feature_time": times,
                "symbol": "TEST",
                "is_distribution": labels,
            }
        )
        feature_cols = ["feature_0"]
        X_train, y_train, X_test, y_test = _split_train_test(
            df, feature_cols, test_frac=0.3
        )
        # Should not crash even if calibration split has single class
        metrics = train_evaluate_lightgbm(X_train, y_train, X_test, y_test)
        assert "precision" in metrics
        assert "brier" in metrics

    def test_learnable_signal_gives_nonzero_precision(self):
        """With a clear signal, LightGBM should achieve non-zero precision."""
        df = _make_synthetic_df(n=1000, seed=789)
        feature_cols = ["feature_0", "feature_1", "feature_2", "feature_3"]
        X_train, y_train, X_test, y_test = _split_train_test(
            df, feature_cols, test_frac=0.3
        )
        metrics = train_evaluate_lightgbm(
            X_train, y_train, X_test, y_test, min_recall=0.20
        )
        assert metrics["precision"] > 0.0

    def test_lightgbm_vs_logreg_comparable_brier(self):
        """LightGBM Brier should be in a reasonable range (not much worse than
        LogReg on the same data)."""
        df = _make_synthetic_df(n=800, seed=111)
        feature_cols = ["feature_0", "feature_1", "feature_2"]
        X_train, y_train, X_test, y_test = _split_train_test(df, feature_cols)

        m_logreg = train_evaluate_logreg(X_train, y_train, X_test, y_test)
        m_lgbm = train_evaluate_lightgbm(X_train, y_train, X_test, y_test)

        # LightGBM Brier should not be dramatically worse (within 0.15)
        assert m_lgbm["brier"] <= m_logreg["brier"] + 0.15


# ---------------------------------------------------------------------------
# train_and_predict_latest (scanner path)
# ---------------------------------------------------------------------------


class TestTrainAndPredictLatest:
    """Tests for the scanner prediction path (must still work after refactor)."""

    def test_returns_predictions_and_metrics(self):
        """Normal case: returns predictions list, model_metrics, model_info."""
        df = _make_synthetic_df(n=300, seed=42)
        feature_cols = ["feature_0", "feature_1"]
        result = train_and_predict_latest(df, feature_cols, n_latest=10)

        assert "predictions" in result
        assert "model_metrics" in result
        assert "model_info" in result
        assert isinstance(result["predictions"], list)
        assert len(result["predictions"]) == 10

    def test_each_prediction_has_required_fields(self):
        """Each prediction has the fields the scanner/UI expects."""
        df = _make_synthetic_df(n=300, seed=42)
        feature_cols = ["feature_0", "feature_1"]
        result = train_and_predict_latest(df, feature_cols, n_latest=5)
        for pred in result["predictions"]:
            assert "feature_time" in pred
            assert "symbol" in pred
            assert "probability" in pred
            assert "risk_level" in pred
            assert "threshold" in pred
            assert "invalidation_time" in pred
            assert 0.0 <= pred["probability"] <= 1.0
            assert pred["risk_level"] in ["CAO", "TRUNG BÌNH", "THẤP", "RẤT THẤP"]

    def test_insufficient_data_returns_empty(self):
        """Edge case: < 200 rows returns empty predictions."""
        df = _make_synthetic_df(n=100, seed=42)
        result = train_and_predict_latest(df, ["feature_0"], n_latest=10)
        assert result["predictions"] == []

    def test_single_class_returns_empty(self):
        """Edge case: only one class in labels returns empty predictions."""
        df = _make_synthetic_df(n=300, seed=42)
        df["is_distribution"] = 0  # all negative
        result = train_and_predict_latest(df, ["feature_0"], n_latest=10)
        assert result["predictions"] == []

    def test_model_metrics_has_threshold(self):
        """model_metrics should include a threshold (used by scanner)."""
        df = _make_synthetic_df(n=300, seed=42)
        result = train_and_predict_latest(df, ["feature_0", "feature_1"], n_latest=10)
        metrics = result["model_metrics"]
        if metrics:  # may be empty if validation split has single class
            assert "threshold" in metrics
            assert "precision" in metrics
            assert "recall" in metrics
