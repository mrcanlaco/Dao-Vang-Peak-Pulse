from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dao_vang.experiments.train_distribution_v2 import (
    V2TrainingConfig,
    _partition_history,
    _threshold_metrics,
    promotion_gate,
    select_threshold,
)


def test_v2_contract_is_fixed_to_24_hours() -> None:
    with pytest.raises(ValueError, match="fixed at 24 hours"):
        V2TrainingConfig(horizon_hours=12).validate()


def test_history_partitions_have_full_label_embargo() -> None:
    times = pd.date_range("2026-01-01", periods=240, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {
            "feature_time": times,
            "label_value": np.resize(np.array([0, 1]), len(times)),
        }
    )

    fit, calibration, policy = _partition_history(frame, pd.Timedelta(hours=24))

    assert fit["feature_time"].max() + pd.Timedelta(hours=24) <= calibration["feature_time"].min()
    assert calibration["feature_time"].max() + pd.Timedelta(hours=24) <= policy["feature_time"].min()


def test_threshold_is_selected_from_policy_payoff() -> None:
    config = V2TrainingConfig(
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


def test_promotion_gate_fails_closed_when_ev_is_negative() -> None:
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
    }
    baseline = {"average_precision": 0.25}

    gate = promotion_gate(
        {"summary": {"lightgbm": challenger, "logistic_regression": baseline}}
    )

    assert gate["passed"] is False
    assert gate["checks"]["positive_conservative_ev"] is False


def test_threshold_counts_one_episode_per_symbol_per_24_hours() -> None:
    config = V2TrainingConfig(
        min_policy_signals=1,
        min_recall_for_threshold=0.0,
    )
    identities = pd.DataFrame(
        {
            "symbol": ["ABCUSDT", "ABCUSDT", "ABCUSDT"],
            "feature_time": pd.to_datetime(
                [
                    "2026-01-01T00:00Z",
                    "2026-01-01T01:00Z",
                    "2026-01-02T00:00Z",
                ]
            ),
        }
    )

    metrics = _threshold_metrics(
        np.array([1, 1, 0]),
        np.array([0.9, 0.8, 0.7]),
        0.70,
        config.target_drawdown,
        config.max_adverse_excursion,
        config.round_trip_cost,
        identities,
    )

    assert metrics["signals"] == 2
