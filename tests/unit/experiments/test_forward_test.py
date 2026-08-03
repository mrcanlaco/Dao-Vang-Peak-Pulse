"""Tests for the forward test loop: freeze, score, evaluate."""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

from dao_vang.experiments.forward_test import (
    evaluate_frozen,
    freeze_model,
    list_frozen_models,
    load_frozen_model,
    score_frozen,
)


def _make_synthetic_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Create a synthetic feature+label dataframe for testing."""
    rng = np.random.default_rng(seed)
    times = pd.date_range("2026-01-01", periods=n, freq="5min", tz="UTC")
    feature_a = rng.standard_normal(n)
    feature_b = rng.standard_normal(n)
    # Label depends on feature_a being high
    prob = 1 / (1 + np.exp(-(feature_a * 2 - 1)))
    labels = (rng.random(n) < prob).astype(int)
    return pd.DataFrame({
        "feature_time": times,
        "symbol": "BTCUSDT",
        "feature_a": feature_a,
        "feature_b": feature_b,
        "is_distribution": labels,
    })


def test_freeze_and_load_model(tmp_path: Path):
    """Freeze a model and load its metadata back."""
    df = _make_synthetic_df()
    feature_cols = ["feature_a", "feature_b"]
    model = LogisticRegression(max_iter=100)
    model.fit(df[feature_cols], df["is_distribution"])

    info = freeze_model(
        model=model,
        threshold=0.35,
        feature_cols=feature_cols,
        config={"hypothesis_id": "test", "seed": 42},
        train_cutoff=df["feature_time"].max(),
        training_stats={"precision": 0.6, "recall": 0.5, "train_size": 300},
        artifact_dir=tmp_path,
    )

    assert info.model_id.startswith("frozen_")
    assert info.model_path.exists()
    assert info.metadata_path.exists()
    assert info.threshold == 0.35
    assert info.feature_cols == feature_cols

    # Load back
    loaded = load_frozen_model(info.model_id, artifact_dir=tmp_path)
    assert loaded.model_id == info.model_id
    assert loaded.threshold == 0.35
    assert loaded.feature_cols == feature_cols


def test_list_frozen_models(tmp_path: Path):
    """List frozen models."""
    df = _make_synthetic_df()
    model = LogisticRegression(max_iter=100)
    model.fit(df[["feature_a", "feature_b"]], df["is_distribution"])

    freeze_model(model, 0.3, ["feature_a", "feature_b"], {}, df["feature_time"].max(), artifact_dir=tmp_path)
    freeze_model(model, 0.4, ["feature_a", "feature_b"], {}, df["feature_time"].max(), artifact_dir=tmp_path)

    models = list_frozen_models(tmp_path)
    assert len(models) == 2
    # Newest first
    assert models[0].freeze_time >= models[1].freeze_time


def test_score_frozen_only_after_cutoff(tmp_path: Path):
    """Score only data after train_cutoff."""
    df = _make_synthetic_df(n=300)
    feature_cols = ["feature_a", "feature_b"]
    model = LogisticRegression(max_iter=100)
    model.fit(df[feature_cols], df["is_distribution"])

    # Freeze with cutoff at row 200
    cutoff = df["feature_time"].iloc[200]
    info = freeze_model(
        model=model, threshold=0.3, feature_cols=feature_cols,
        config={}, train_cutoff=cutoff, artifact_dir=tmp_path,
    )

    # Score — only_after_cutoff=True (default)
    preds = score_frozen(info.model_id, df, artifact_dir=tmp_path)
    assert len(preds) == 99  # rows 201..299
    assert "probability" in preds.columns
    assert "risk_level" in preds.columns
    assert "invalidation_time" in preds.columns
    assert all(preds["model_id"] == info.model_id)

    # Score all
    preds_all = score_frozen(info.model_id, df, artifact_dir=tmp_path, only_after_cutoff=False)
    assert len(preds_all) == 300


def test_evaluate_frozen(tmp_path: Path):
    """Evaluate frozen model on forward data with labels."""
    df = _make_synthetic_df(n=400)
    feature_cols = ["feature_a", "feature_b"]

    # Train on first 300, freeze
    train = df.iloc[:300]
    model = LogisticRegression(max_iter=100)
    model.fit(train[feature_cols], train["is_distribution"])
    cutoff = train["feature_time"].max()

    info = freeze_model(
        model=model, threshold=0.3, feature_cols=feature_cols,
        config={"hypothesis_id": "test"},
        train_cutoff=cutoff,
        training_stats={"precision": 0.6, "recall": 0.5},
        artifact_dir=tmp_path,
    )

    # Evaluate on full df (forward = rows after cutoff)
    result = evaluate_frozen(info.model_id, df, artifact_dir=tmp_path)
    assert result["status"] == "ok"
    assert result["n_forward_rows"] == 100  # rows 300..399 (cutoff at index 299)
    assert "metrics" in result
    assert "precision" in result["metrics"]
    assert "risk_breakdown" in result
    assert "drift_check" in result
    assert "summary" in result


def test_evaluate_frozen_no_forward_data(tmp_path: Path):
    """Evaluate returns no_forward_data when no labeled data after cutoff."""
    df = _make_synthetic_df(n=100)
    model = LogisticRegression(max_iter=100)
    model.fit(df[["feature_a", "feature_b"]], df["is_distribution"])

    # Cutoff AFTER all data
    info = freeze_model(
        model=model, threshold=0.3, feature_cols=["feature_a", "feature_b"],
        config={}, train_cutoff=df["feature_time"].max() + pd.Timedelta(hours=1),
        artifact_dir=tmp_path,
    )

    result = evaluate_frozen(info.model_id, df, artifact_dir=tmp_path)
    assert result["status"] == "no_forward_data"
