"""Unit tests for Drift Guardian and Calibration Monitor."""

import numpy as np
import pandas as pd

from dao_vang.alpha_lab.drift_guardian import (
    DriftGuardian,
    DriftStatus,
    calculate_brier_score,
    calculate_ece,
    calculate_psi,
)


def test_calculate_psi_stable() -> None:
    np.random.seed(42)
    expected = np.random.normal(100, 15, 1000)
    actual = np.random.normal(100, 15, 1000)  # Identical distribution

    psi = calculate_psi(expected, actual)
    assert psi < 0.10  # Must be healthy / stable


def test_calculate_psi_shifted() -> None:
    np.random.seed(42)
    expected = np.random.normal(100, 15, 1000)
    actual = np.random.normal(130, 25, 1000)  # Heavily shifted distribution

    psi = calculate_psi(expected, actual)
    assert psi >= 0.20  # Significant drift detected


def test_calculate_brier_and_ece() -> None:
    y_true = np.array([1, 1, 0, 0])
    y_prob = np.array([0.9, 0.8, 0.1, 0.2])

    brier = calculate_brier_score(y_true, y_prob)
    ece = calculate_ece(y_true, y_prob)

    assert 0.0 <= brier <= 0.1  # Very well calibrated predictions
    assert 0.0 <= ece <= 0.3


def test_drift_guardian_workflow() -> None:
    np.random.seed(42)
    baseline_df = pd.DataFrame(
        {
            "feat_a": np.random.normal(0, 1, 500),
            "feat_b": np.random.uniform(10, 20, 500),
        }
    )

    guardian = DriftGuardian(psi_warning_thresh=0.10, psi_critical_thresh=0.20)
    guardian.set_baseline(baseline_df)

    # 1. Healthy live stream
    live_healthy = pd.DataFrame(
        {
            "feat_a": np.random.normal(0, 1, 200),
            "feat_b": np.random.uniform(10, 20, 200),
        }
    )
    report_healthy = guardian.evaluate_health(live_healthy)
    assert report_healthy.status == DriftStatus.HEALTHY

    # 2. Drifting live stream
    live_drifted = pd.DataFrame(
        {
            "feat_a": np.random.normal(5, 2, 200),  # Mean shifted significantly
            "feat_b": np.random.uniform(10, 20, 200),
        }
    )
    report_drifted = guardian.evaluate_health(live_drifted)
    assert report_drifted.status in (DriftStatus.WARNING, DriftStatus.CRITICAL)
    assert len(report_drifted.alert_messages) > 0
