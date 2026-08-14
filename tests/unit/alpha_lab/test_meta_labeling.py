"""Unit tests for Meta-Labeling Model."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from dao_vang.alpha_lab.meta_labeling import MetaFilterDecision, MetaLabelingModel


@pytest.fixture
def synthetic_meta_dataset() -> tuple[pd.DataFrame, np.ndarray]:
    """Generate synthetic features and trade outcomes."""
    np.random.seed(42)
    n_samples = 100

    features = pd.DataFrame(
        {
            "atr_pct": np.random.uniform(0.01, 0.05, n_samples),
            "taker_buy_ratio": np.random.uniform(0.4, 0.6, n_samples),
            "oi_change_pct": np.random.normal(0.0, 0.05, n_samples),
            "primary_probability": np.random.uniform(0.6, 0.9, n_samples),
            "regime": ["SIDEWAY_DISTRIBUTION"] * 80 + ["HIGH_VOLATILITY_CHOP"] * 20,
        }
    )

    # Synthetic target: high primary prob + high taker buy ratio
    logits = features["primary_probability"] * 2.0 - features["atr_pct"] * 10.0
    probs = 1.0 / (1.0 + np.exp(-logits))
    labels = (probs > np.median(probs)).astype(int)

    return features, labels


def test_meta_labeling_fit_and_predict(
    synthetic_meta_dataset: tuple[pd.DataFrame, np.ndarray],
) -> None:
    X, y = synthetic_meta_dataset
    model = MetaLabelingModel(threshold=0.60)
    model.fit(X, y)

    assert model.is_fitted
    probs = model.predict_proba(X)
    assert len(probs) == len(X)
    assert (probs >= 0.0).all() and (probs <= 1.0).all()


def test_meta_labeling_filter_decision(
    synthetic_meta_dataset: tuple[pd.DataFrame, np.ndarray],
) -> None:
    X, y = synthetic_meta_dataset
    model = MetaLabelingModel(threshold=0.60)
    model.fit(X, y)

    # Test single signal filtering
    sample_feat = {
        "atr_pct": 0.01,
        "taker_buy_ratio": 0.55,
        "oi_change_pct": 0.02,
        "primary_probability": 0.85,
    }
    decision = model.filter_signal(
        features=sample_feat,
        primary_prob=0.85,
        regime="SIDEWAY_DISTRIBUTION",
    )

    assert isinstance(decision, MetaFilterDecision)
    assert isinstance(decision.should_execute, bool)
    assert 0.0 <= decision.meta_probability <= 1.0


def test_meta_labeling_counter_trend_guardrail() -> None:
    model = MetaLabelingModel(threshold=0.50)
    decision = model.filter_signal(
        features={"side": -1, "atr_pct": 0.02},
        primary_prob=0.90,
        regime="TRENDING_BULL",
    )
    # Counter-trend short in bull regime must be rejected regardless of probability
    assert decision.should_execute is False
    assert "Counter-trend" in decision.reason


def test_meta_labeling_save_load(
    tmp_path: Path, synthetic_meta_dataset: tuple[pd.DataFrame, np.ndarray]
) -> None:
    X, y = synthetic_meta_dataset
    model = MetaLabelingModel(threshold=0.65)
    model.fit(X, y)

    model_path = tmp_path / "meta_model.pkl"
    model.save(model_path)
    assert model_path.exists()

    loaded_model = MetaLabelingModel.load(model_path)
    assert loaded_model.is_fitted
    assert loaded_model.threshold == 0.65

    p1 = model.predict_proba(X)
    p2 = loaded_model.predict_proba(X)
    np.testing.assert_allclose(p1, p2)
