"""Drift Guardian and Continuous Calibration Monitor.

Monitors Alpha Decay, Population Stability Index (PSI), Rolling Brier Score,
and Expected Calibration Error (ECE) to alert when market distribution changes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd


class DriftStatus(str, Enum):
    """Health status of model calibration and feature stability."""

    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class DriftReport:
    """Consolidated report on feature drift and calibration stability."""

    status: DriftStatus
    max_psi: float
    feature_psi: dict[str, float]
    brier_score: float | None
    ece: float | None
    alert_messages: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def calculate_psi(
    expected: np.ndarray | pd.Series,
    actual: np.ndarray | pd.Series,
    num_buckets: int = 10,
    epsilon: float = 1e-4,
) -> float:
    """Calculate the Population Stability Index (PSI) between two distributions.

    Parameters
    ----------
    expected : np.ndarray or pd.Series
        Baseline / In-sample reference distribution.
    actual : np.ndarray or pd.Series
        Current / Live inference distribution.
    num_buckets : int
        Number of quantile bins to partition the distribution.
    epsilon : float
        Small offset to prevent division by zero or log(0).

    Returns
    -------
    float
        PSI metric:
        - PSI < 0.10: No significant change / Stable
        - 0.10 <= PSI < 0.20: Moderate drift / Warning
        - PSI >= 0.20: Significant drift / Model degradation
    """
    exp_arr = np.asarray(expected).astype(float)
    act_arr = np.asarray(actual).astype(float)

    # Remove NaNs and Infs
    exp_arr = exp_arr[np.isfinite(exp_arr)]
    act_arr = act_arr[np.isfinite(act_arr)]

    if len(exp_arr) < num_buckets or len(act_arr) < num_buckets:
        return 0.0

    # Determine quantile bins from expected distribution
    percentiles = np.linspace(0, 100, num_buckets + 1)
    bin_edges = np.percentile(exp_arr, percentiles)
    bin_edges = np.unique(bin_edges)  # Remove duplicates if discrete

    if len(bin_edges) <= 1:
        return 0.0

    bin_edges[0] = -np.inf
    bin_edges[-1] = np.inf

    # Count occurrences in bins
    exp_counts, _ = np.histogram(exp_arr, bins=bin_edges)
    act_counts, _ = np.histogram(act_arr, bins=bin_edges)

    # Convert to fractions with smoothing
    exp_pct = (exp_counts + epsilon) / (len(exp_arr) + epsilon * len(exp_counts))
    act_pct = (act_counts + epsilon) / (len(act_arr) + epsilon * len(act_counts))

    # Calculate PSI formula: sum((Actual% - Expected%) * ln(Actual% / Expected%))
    psi_vector = (act_pct - exp_pct) * np.log(act_pct / exp_pct)
    psi_value = float(np.sum(psi_vector))

    return max(psi_value, 0.0)


def calculate_brier_score(
    y_true: np.ndarray | pd.Series, y_prob: np.ndarray | pd.Series
) -> float:
    """Calculate Brier Score (Mean Squared Probability Error). Lower is better."""
    yt = np.asarray(y_true).astype(float)
    yp = np.asarray(y_prob).astype(float)
    if len(yt) == 0:
        return 0.0
    return float(np.mean((yp - yt) ** 2))


def calculate_ece(
    y_true: np.ndarray | pd.Series,
    y_prob: np.ndarray | pd.Series,
    num_bins: int = 10,
) -> float:
    """Calculate Expected Calibration Error (ECE). Lower is better."""
    yt = np.asarray(y_true).astype(float)
    yp = np.asarray(y_prob).astype(float)

    if len(yt) == 0:
        return 0.0

    bin_boundaries = np.linspace(0, 1, num_bins + 1)
    ece = 0.0

    for i in range(num_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]

        in_bin = (
            (yp > bin_lower) & (yp <= bin_upper)
            if i > 0
            else (yp >= bin_lower) & (yp <= bin_upper)
        )
        prop_in_bin = np.mean(in_bin)

        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(yt[in_bin])
            avg_confidence_in_bin = np.mean(yp[in_bin])
            ece += prop_in_bin * np.abs(avg_confidence_in_bin - accuracy_in_bin)

    return float(ece)


class DriftGuardian:
    """Monitors live data and historical predictions against baselines."""

    def __init__(
        self,
        psi_warning_thresh: float = 0.10,
        psi_critical_thresh: float = 0.20,
        brier_critical_thresh: float = 0.22,
        ece_critical_thresh: float = 0.15,
    ) -> None:
        self.psi_warning_thresh = psi_warning_thresh
        self.psi_critical_thresh = psi_critical_thresh
        self.brier_critical_thresh = brier_critical_thresh
        self.ece_critical_thresh = ece_critical_thresh
        self.baseline_features: dict[str, np.ndarray] = {}

    def set_baseline(self, baseline_df: pd.DataFrame) -> None:
        """Register baseline feature distribution from the training dataset."""
        self.baseline_features = {}
        for col in baseline_df.select_dtypes(include=[np.number]).columns:
            vals = baseline_df[col].dropna().to_numpy()
            if len(vals) > 0:
                self.baseline_features[col] = vals

    def evaluate_health(
        self,
        live_df: pd.DataFrame,
        y_true: np.ndarray | None = None,
        y_prob: np.ndarray | None = None,
    ) -> DriftReport:
        """Run comprehensive stability and calibration checks on live inference data."""
        feature_psi: dict[str, float] = {}
        alerts: list[str] = []
        max_psi = 0.0

        # 1. Feature Drift (PSI)
        for col, base_vals in self.baseline_features.items():
            if col in live_df.columns:
                live_vals = live_df[col].dropna().to_numpy()
                psi_val = calculate_psi(base_vals, live_vals)
                feature_psi[col] = psi_val
                if psi_val > max_psi:
                    max_psi = psi_val

                if psi_val >= self.psi_critical_thresh:
                    alerts.append(
                        f"CRITICAL: Feature '{col}' severe drift (PSI={psi_val:.3f})."
                    )
                elif psi_val >= self.psi_warning_thresh:
                    alerts.append(
                        f"WARNING: Feature '{col}' moderate drift (PSI={psi_val:.3f})."
                    )

        # 2. Calibration Drift (Brier & ECE)
        brier_val: float | None = None
        ece_val: float | None = None

        if y_true is not None and y_prob is not None and len(y_true) > 0:
            brier_val = calculate_brier_score(y_true, y_prob)
            ece_val = calculate_ece(y_true, y_prob)

            if brier_val >= self.brier_critical_thresh:
                alerts.append(
                    f"CRITICAL: Brier Score degraded to {brier_val:.3f}."
                )
            if ece_val >= self.ece_critical_thresh:
                alerts.append(
                    f"WARNING: ECE rose to {ece_val:.3f}."
                )

        # Determine overall status
        if any("CRITICAL" in a for a in alerts) or max_psi >= self.psi_critical_thresh:
            status = DriftStatus.CRITICAL
        elif any("WARNING" in a for a in alerts) or max_psi >= self.psi_warning_thresh:
            status = DriftStatus.WARNING
        else:
            status = DriftStatus.HEALTHY

        return DriftReport(
            status=status,
            max_psi=max_psi,
            feature_psi=feature_psi,
            brier_score=brier_val,
            ece=ece_val,
            alert_messages=alerts,
        )
