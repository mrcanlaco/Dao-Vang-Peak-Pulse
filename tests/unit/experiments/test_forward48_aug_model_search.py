from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).parents[3] / "scripts" / "forward48_aug_model_search.py"
SPEC = importlib.util.spec_from_file_location("forward48_aug_model_search", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["A", "A", "A", "A"],
            "feature_time": pd.to_datetime(
                [
                    "2026-01-01T00:00Z",
                    "2026-01-01T01:00Z",
                    "2026-01-01T02:00Z",
                    "2026-01-01T05:00Z",
                ]
            ),
            "price_ret_24h": [0.10, 0.16, 0.20, 0.18],
            "price_ret_5m": [0.01, -0.01, -0.02, 0.01],
            "price_ret_1h": [0.02, -0.03, -0.04, 0.01],
            "price_ret_4h": [0.08, 0.12, 0.10, 0.08],
            "distance_from_high_24h": [-0.01, -0.02, -0.05, -0.03],
            "momentum_deceleration_4h": [0.0, -0.01, -0.02, 0.01],
        }
    )


def test_augmentation_uses_past_only_and_resets_after_gap() -> None:
    result = MODULE._augment(_frame(), 0.15)
    assert result["pump_age_hours"].tolist() == [0.0, 1.0, 2.0, 0.0]
    assert result["ret24h_peak_6h"].tolist() == [0.10, 0.16, 0.20, 0.20]
    assert result.loc[2, "reversal_pressure"] > 0


def test_episode_mask_keeps_one_signal_per_24_hours() -> None:
    frame = _frame()
    selected = MODULE._episode_mask(frame, np.ones(4, dtype=bool), 24)
    assert selected.tolist() == [True, False, False, False]


def test_wilson_interval_contains_observed_precision() -> None:
    lower, upper = MODULE._wilson(52, 187)
    assert lower < 52 / 187 < upper
    assert round(lower, 6) == 0.218816
