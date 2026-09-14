from __future__ import annotations

import pandas as pd
import pytest

from scripts.forward48_scalein_timing_compatibility import (
    EXPECTED_TIMING_LOCK_SHA256,
    verify_locked_inputs,
)


def _report(*, lock: str = EXPECTED_TIMING_LOCK_SHA256) -> dict:
    return {
        "immutable_inputs": {
            "policy_lock_sha256": lock,
            "august_labels_used_for_model_or_policy_selection": False,
        },
        "august": {"signals": 2},
    }


def _rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAAUSDT", "BBBUSDT"],
            "feature_time": ["2026-08-01T00:00:00Z", "2026-08-02T00:00:00Z"],
        }
    )


def test_verify_locked_inputs_accepts_exact_signal_keys() -> None:
    rows = _rows()
    verify_locked_inputs(_report(), rows, rows.copy())


def test_verify_locked_inputs_rejects_wrong_lock() -> None:
    with pytest.raises(RuntimeError, match="unexpected timing lock"):
        verify_locked_inputs(_report(lock="wrong"), _rows(), _rows())


def test_verify_locked_inputs_rejects_key_drift() -> None:
    signals = _rows()
    keys = _rows()
    keys.loc[1, "symbol"] = "CHANGEDUSDT"
    with pytest.raises(RuntimeError, match="do not exactly match"):
        verify_locked_inputs(_report(), signals, keys)
