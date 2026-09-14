from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dao_vang.experiments.train_distribution_v3 import (
    V3TrainingConfig,
    _partition_history,
    promotion_gate,
    select_threshold,
)
from dao_vang.labels.specs.distribution_short_v3 import SPEC, TIMING


def test_v3_contract_is_fixed_to_48_hours() -> None:
    with pytest.raises(ValueError, match="fixed at 48 hours"):
        V3TrainingConfig(horizon_hours=24).validate()


def test_v3_embargo_is_at_least_48_hours() -> None:
    with pytest.raises(ValueError, match="embargo must be at least 48 hours"):
        V3TrainingConfig(embargo_hours=24).validate()


def test_v3_config_matches_spec() -> None:
    config = V3TrainingConfig()
    config.validate()
    assert config.horizon_hours == SPEC.horizon_hours == 48
    assert config.target_drawdown == SPEC.target == 0.20
    assert config.max_adverse_excursion == SPEC.stop == 0.16
    assert config.offsets == SPEC.offsets == (0.0, 0.03, 0.06)
    assert config.notional_weights == SPEC.notional_weights == (0.20, 0.30, 0.50)
    assert config.pump_threshold_24h == TIMING.min_return_24h == 0.15


def test_history_partitions_have_full_48h_embargo() -> None:
    times = pd.date_range("2026-01-01", periods=1000, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {
            "feature_time": times,
            "label_value": np.resize(np.array([0, 1]), len(times)),
        }
    )

    embargo = pd.Timedelta(hours=48)
    fit, calibration, policy = _partition_history(frame, embargo)

    assert fit["feature_time"].max() + pd.Timedelta(hours=48) <= calibration["feature_time"].min()
    assert calibration["feature_time"].max() + pd.Timedelta(hours=48) <= policy["feature_time"].min()


def test_threshold_is_selected_from_policy_payoff_48h() -> None:
    config = V3TrainingConfig(
        min_policy_signals=2,
        min_recall_for_threshold=0.25,
    )
    y_true = np.array([1, 1, 0, 0, 0, 0])
    probabilities = np.array([0.90, 0.70, 0.60, 0.30, 0.20, 0.10])

    threshold, metrics = select_threshold(y_true, probabilities, config)

    assert 0.60 < threshold <= 0.70
    assert metrics["signals"] == 2
    assert metrics["precision"] == 1.0
    assert metrics["conservative_ev"] == pytest.approx(0.198)


def test_v3_promotion_gate_fails_closed() -> None:
    challenger = {
        "folds": 4,
        "signals": 100,
        "precision": 0.50,
        "recall": 0.20,
        "conservative_ev": -0.001,
        "positive_ev_folds": 3,
        "ap_lift_over_prevalence": 2.0,
        "brier": 0.10,
        "null_brier": 0.12,
        "average_precision": 0.30,
        "ece": 0.03,
    }
    baseline = {"average_precision": 0.25}

    gate = promotion_gate(
        {"summary": {"lightgbm": challenger, "logistic_regression": baseline}}
    )

    assert gate["passed"] is False
    assert gate["checks"]["positive_conservative_ev"] is False
