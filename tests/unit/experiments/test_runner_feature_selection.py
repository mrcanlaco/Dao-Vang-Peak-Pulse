"""Tests for the runner: feature selection (null-heavy drop) and model
selection (LogReg vs LightGBM based on baseline_model config).

These tests use a temporary DuckDB file with synthetic data so the full
run_experiment pipeline is exercised end-to-end.
"""

import duckdb
import numpy as np
import pandas as pd

from dao_vang.experiments.runner import ExperimentConfig, run_experiment


def _create_synthetic_db(db_path: str, n_rows: int = 600, seed: int = 42) -> None:
    """Create a DuckDB file with feature_results + labels tables containing
    synthetic data, including some null-heavy columns that should be dropped.
    """
    rng = np.random.default_rng(seed)
    times = pd.date_range("2026-01-01", periods=n_rows, freq="5min", tz="UTC")

    # Signal feature (label depends on this)
    signal_feature = rng.standard_normal(n_rows)
    # Noise features
    noise_a = rng.standard_normal(n_rows)
    noise_b = rng.standard_normal(n_rows)
    # Null-heavy feature (>50% null — should be dropped by feature selection)
    null_heavy = np.where(rng.random(n_rows) < 0.7, np.nan, rng.standard_normal(n_rows))
    # Fully-null feature (should definitely be dropped)
    all_null = np.full(n_rows, np.nan)

    # Label: depends on signal_feature
    prob = 1 / (1 + np.exp(-(signal_feature * 2 - 0.3)))
    labels = (rng.random(n_rows) < prob).astype(int)

    feature_df = pd.DataFrame(
        {
            "feature_time": times,
            "symbol": "TESTUSDT",
            "signal_feature": signal_feature,
            "noise_a": noise_a,
            "noise_b": noise_b,
            "null_heavy_col": null_heavy,
            "all_null_col": all_null,
        }
    )
    label_df = pd.DataFrame(
        {
            "signal_time": times,
            "symbol": "TESTUSDT",
            "label_value": labels.astype(int),
            "lead_time_minutes": np.full(n_rows, 120.0),
            "invalidation_time": times + pd.Timedelta(minutes=1440),
        }
    )

    conn = duckdb.connect(db_path)
    conn.execute("DROP TABLE IF EXISTS feature_results")
    conn.execute("DROP TABLE IF EXISTS labels")
    conn.register("feature_df", feature_df)
    conn.execute("CREATE TABLE feature_results AS SELECT * FROM feature_df")
    conn.register("label_df", label_df)
    conn.execute("CREATE TABLE labels AS SELECT * FROM label_df")
    conn.close()


class TestFeatureSelectionNullHeavy:
    """Tests for the null-heavy feature selection in run_experiment."""

    def test_null_heavy_features_dropped(self, tmp_path):
        """Features with >50% nulls should be dropped and reported."""
        db_path = str(tmp_path / "test.duckdb")
        _create_synthetic_db(db_path, n_rows=600, seed=42)

        config = ExperimentConfig(
            hypothesis_id="test_null_heavy",
            baseline_model="logreg_walkforward",
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=42,
            metrics=["precision", "recall"],
            db_path=db_path,
        )
        result = run_experiment(config)
        results = result["results"]
        fsel = results.get("feature_selection", {})

        assert fsel["n_candidate_features"] == 5  # 5 non-excluded columns
        # null_heavy_col (>50% null) and all_null_col (100% null) should be dropped
        assert "null_heavy_col" in fsel["dropped_null_heavy"]
        assert "all_null_col" in fsel["dropped_null_heavy"]
        assert fsel["n_selected_features"] == 3  # signal, noise_a, noise_b
        assert fsel["null_threshold"] == 0.50

    def test_feature_selection_in_results_output(self, tmp_path):
        """feature_selection key should be present in results output."""
        db_path = str(tmp_path / "test.duckdb")
        _create_synthetic_db(db_path, n_rows=600, seed=42)

        config = ExperimentConfig(
            hypothesis_id="test_fsel_output",
            baseline_model="logreg_walkforward",
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=42,
            metrics=["precision", "recall"],
            db_path=db_path,
        )
        result = run_experiment(config)
        assert "feature_selection" in result["results"]

    def test_no_null_heavy_features_all_kept(self, tmp_path):
        """When all features have sufficient coverage, none are dropped."""
        db_path = str(tmp_path / "test.duckdb")
        # Create data with no nulls
        rng = np.random.default_rng(42)
        n = 600
        times = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
        signal = rng.standard_normal(n)
        noise = rng.standard_normal(n)
        prob = 1 / (1 + np.exp(-(signal * 2 - 0.3)))
        labels = (rng.random(n) < prob).astype(int)

        feature_df = pd.DataFrame(
            {
                "feature_time": times,
                "symbol": "TESTUSDT",
                "signal_feature": signal,
                "noise_feature": noise,
            }
        )
        label_df = pd.DataFrame(
            {
                "signal_time": times,
                "symbol": "TESTUSDT",
                "label_value": labels.astype(int),
                "lead_time_minutes": np.full(n, 120.0),
                "invalidation_time": times + pd.Timedelta(minutes=1440),
            }
        )
        conn = duckdb.connect(db_path)
        conn.register("fdf", feature_df)
        conn.execute("CREATE TABLE feature_results AS SELECT * FROM fdf")
        conn.register("ldf", label_df)
        conn.execute("CREATE TABLE labels AS SELECT * FROM ldf")
        conn.close()

        config = ExperimentConfig(
            hypothesis_id="test_no_nulls",
            baseline_model="logreg_walkforward",
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=42,
            metrics=["precision", "recall"],
            db_path=db_path,
        )
        result = run_experiment(config)
        fsel = result["results"]["feature_selection"]
        assert fsel["n_candidate_features"] == 2
        assert fsel["n_selected_features"] == 2
        assert fsel["dropped_null_heavy"] == []


class TestModelSelection:
    """Tests for LogReg vs LightGBM model selection based on baseline_model."""

    def test_lightgbm_config_runs_successfully(self, tmp_path):
        """baseline_model='lightgbm_isotonic' should run LightGBM path and
        return valid results."""
        db_path = str(tmp_path / "test.duckdb")
        _create_synthetic_db(db_path, n_rows=800, seed=42)

        config = ExperimentConfig(
            hypothesis_id="test_lgbm",
            baseline_model="lightgbm_isotonic",
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=42,
            metrics=["precision", "recall", "brier"],
            db_path=db_path,
        )
        result = run_experiment(config)
        assert result["status"] == "completed"
        agg = result["results"]["aggregate"]
        assert "precision_mean" in agg
        assert "recall_mean" in agg
        assert agg["n_valid_folds"] >= 1

    def test_logreg_config_still_works(self, tmp_path):
        """baseline_model='logreg_walkforward' should use LogReg path."""
        db_path = str(tmp_path / "test.duckdb")
        _create_synthetic_db(db_path, n_rows=800, seed=42)

        config = ExperimentConfig(
            hypothesis_id="test_logreg",
            baseline_model="logreg_walkforward",
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=42,
            metrics=["precision", "recall", "brier"],
            db_path=db_path,
        )
        result = run_experiment(config)
        assert result["status"] == "completed"
        agg = result["results"]["aggregate"]
        assert "precision_mean" in agg

    def test_lightgbm_prefix_case_insensitive(self, tmp_path):
        """baseline_model='LightGBM_anything' should also trigger LightGBM."""
        db_path = str(tmp_path / "test.duckdb")
        _create_synthetic_db(db_path, n_rows=800, seed=42)

        config = ExperimentConfig(
            hypothesis_id="test_lgbm_case",
            baseline_model="LightGBM_custom_variant",
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=42,
            metrics=["precision", "recall"],
            db_path=db_path,
        )
        # Should not crash — LightGBM path is selected
        result = run_experiment(config)
        assert result["status"] == "completed"


class TestRunnerEdgeCases:
    """Edge cases for run_experiment."""

    def test_missing_db_returns_mock(self, tmp_path):
        """When DB file doesn't exist, mock results are returned."""
        config = ExperimentConfig(
            hypothesis_id="test_missing",
            baseline_model="logreg_walkforward",
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=42,
            metrics=["precision", "recall"],
            db_path=str(tmp_path / "nonexistent.duckdb"),
        )
        result = run_experiment(config)
        # Mock results have specific structure
        assert result["status"] == "completed"
        assert "per_fold" in result["results"]

    def test_empty_labels_table_returns_mock(self, tmp_path):
        """When labels table exists but is empty, mock results are returned."""
        db_path = str(tmp_path / "test.duckdb")
        conn = duckdb.connect(db_path)
        conn.execute(
            "CREATE TABLE feature_results "
            "(feature_time TIMESTAMP, symbol VARCHAR, f1 DOUBLE)"
        )
        conn.execute(
            "CREATE TABLE labels "
            "(signal_time TIMESTAMP, symbol VARCHAR, label_value INTEGER, "
            "lead_time_minutes DOUBLE, invalidation_time TIMESTAMP)"
        )
        conn.close()

        config = ExperimentConfig(
            hypothesis_id="test_empty",
            baseline_model="logreg_walkforward",
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=42,
            metrics=["precision", "recall"],
            db_path=db_path,
        )
        result = run_experiment(config)
        # Empty data → mock results
        assert result["status"] == "completed"
