"""Meta-Labeling and Secondary Execution Filter Engine.

Implements the secondary machine learning layer (Meta-Model) to filter out false
signals from the primary model by evaluating market microstructure, volatility,
regime context, and primary signal confidence before allowing execution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier


@dataclass(frozen=True)
class MetaFilterDecision:
    """Decision output from the Meta-Labeling filter."""

    should_execute: bool
    meta_probability: float
    primary_probability: float
    market_regime: str
    risk_scaling: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetaLabelingModel:
    """Secondary execution filter model trained on Triple-Barrier outcomes."""

    def __init__(
        self,
        threshold: float = 0.65,
        min_samples_split: int = 10,
        max_iter: int = 100,
        random_state: int = 42,
    ) -> None:
        self.threshold = threshold
        self.feature_names: list[str] = []
        self.is_fitted = False
        self._model = HistGradientBoostingClassifier(
            max_iter=max_iter,
            min_samples_leaf=min_samples_split,
            random_state=random_state,
        )

    def prepare_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize and encode input feature matrix."""
        feat_df = df.copy()

        # One-hot or categorical encoding for regime if present
        if "regime" in feat_df.columns:
            regime_mapping = {
                "TRENDING_BULL": 0,
                "TRENDING_BEAR": 1,
                "HIGH_VOLATILITY_CHOP": 2,
                "SIDEWAY_DISTRIBUTION": 3,
            }
            feat_df["regime_encoded"] = feat_df["regime"].map(regime_mapping).fillna(3)
            feat_df = feat_df.drop(columns=["regime"])

        # Drop non-feature columns if present
        cols_to_drop = [
            "timestamp",
            "entry_time",
            "exit_time",
            "exit_price",
            "touch_type",
            "raw_return",
            "label",
            "target",
        ]
        for col in cols_to_drop:
            if col in feat_df.columns:
                feat_df = feat_df.drop(columns=[col])

        # Fill any remaining NaNs
        feat_df = feat_df.fillna(0.0)
        return feat_df

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray) -> MetaLabelingModel:
        """Train the meta-labeling model on features and binary triple-barrier outcomes.

        Parameters
        ----------
        X : pd.DataFrame
            Feature matrix at signal entry time (volatility, taker, OI, prob).
        y : pd.Series or np.ndarray
            Binary target: 1 = profitable signal (TP), 0 = false signal (SL/loss).
        """
        X_proc = self.prepare_features(X)
        self.feature_names = list(X_proc.columns)

        y_arr = np.asarray(y)
        # Convert -1/0/1 triple barrier labels to binary 0/1 if needed
        if set(np.unique(y_arr)).issubset({-1, 0, 1}):
            y_arr = np.where(y_arr == 1, 1, 0)

        # Ensure at least two classes
        if len(np.unique(y_arr)) < 2:
            # Fallback if all 1s or all 0s
            self.is_fitted = False
            return self

        self._model.fit(X_proc, y_arr)
        self.is_fitted = True
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Predict execution success probability for each candidate signal."""
        if not self.is_fitted:
            # Fallback: pass-through primary probability or neutral 0.5
            if "primary_probability" in X.columns:
                return X["primary_probability"].to_numpy()
            return np.full(len(X), 0.5)

        X_proc = self.prepare_features(X)
        # Ensure column alignment
        for col in self.feature_names:
            if col not in X_proc.columns:
                X_proc[col] = 0.0
        X_proc = X_proc[self.feature_names]

        probs = self._model.predict_proba(X_proc)
        # Return probability of class 1
        return probs[:, 1]

    def filter_signal(
        self,
        features: dict[str, Any] | pd.Series,
        primary_prob: float = 0.70,
        regime: str = "SIDEWAY_DISTRIBUTION",
        threshold_override: float | None = None,
    ) -> MetaFilterDecision:
        """Evaluate a single real-time signal and decide whether to execute.

        Parameters
        ----------
        features : dict or pd.Series
            Market microstructure and technical metrics at signal generation.
        primary_prob : float
            Calibrated probability from the primary PeakPulse radar model.
        regime : str
            Current market regime from RegimeClassifier.
        threshold_override : float, optional
            Custom probability threshold for execution.

        Returns
        -------
        MetaFilterDecision
            Execution recommendation with meta-probability, risk scaling, and reason.
        """
        thresh = (
            threshold_override if threshold_override is not None else self.threshold
        )

        row_dict = dict(features) if isinstance(features, pd.Series) else dict(features)
        row_dict["primary_probability"] = primary_prob
        row_dict["regime"] = regime

        row_df = pd.DataFrame([row_dict])
        meta_prob = float(self.predict_proba(row_df)[0])

        # Regime-based guardrails
        if regime == "TRENDING_BULL" and row_dict.get("side", -1) == -1:
            return MetaFilterDecision(
                should_execute=False,
                meta_probability=meta_prob,
                primary_probability=primary_prob,
                market_regime=regime,
                risk_scaling=0.0,
                reason="Rejected: Counter-trend Short in Bull Trend regime.",
            )

        if meta_prob >= thresh:
            risk_scaling = 1.0 if regime != "HIGH_VOLATILITY_CHOP" else 0.5
            return MetaFilterDecision(
                should_execute=True,
                meta_probability=meta_prob,
                primary_probability=primary_prob,
                market_regime=regime,
                risk_scaling=risk_scaling,
                reason=f"Approved: Confidence ({meta_prob:.1%}) >= ({thresh:.1%}).",
            )
        else:
            return MetaFilterDecision(
                should_execute=False,
                meta_probability=meta_prob,
                primary_probability=primary_prob,
                market_regime=regime,
                risk_scaling=0.0,
                reason=f"Dropped: Confidence ({meta_prob:.1%}) < ({thresh:.1%}).",
            )

    def save(self, filepath: str | Path) -> None:
        """Save model configuration and feature metadata."""
        import pickle

        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(
                {
                    "threshold": self.threshold,
                    "feature_names": self.feature_names,
                    "is_fitted": self.is_fitted,
                    "model": self._model,
                },
                f,
            )

    @classmethod
    def load(cls, filepath: str | Path) -> MetaLabelingModel:
        """Load trained model from disk."""
        import pickle

        with open(filepath, "rb") as f:
            data = pickle.load(f)

        instance = cls(threshold=data["threshold"])
        instance.feature_names = data["feature_names"]
        instance.is_fitted = data["is_fitted"]
        instance._model = data["model"]
        return instance
