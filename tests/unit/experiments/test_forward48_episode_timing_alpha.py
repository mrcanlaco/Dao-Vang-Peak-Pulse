from __future__ import annotations

from dataclasses import replace

import pandas as pd

from scripts.forward48_episode_timing_alpha import (
    TimingRule,
    _episode_ids,
    metrics,
    rule_catalog,
    select_signals,
)


def _rows() -> pd.DataFrame:
    times = pd.date_range("2026-01-01", periods=7, freq="h", tz="UTC")
    frame = pd.DataFrame(
        {
            "symbol": ["XUSDT"] * 7,
            "feature_time": times,
            "fold": [1] * 7,
            "label_value": [0, 0, 1, 1, 1, 1, 1],
            "price_ret_24h": [0.16, 0.25, 0.31, 0.35, 0.34, 0.32, 0.29],
            "distance_from_high_24h": [-0.01, -0.01, -0.01, -0.01, -0.02, -0.04, -0.07],
            "probability": [0.2, 0.4, 0.42, 0.44, 0.41, 0.37, 0.32],
            "threshold": [0.39] * 7,
            "momentum_deceleration_4h": [0.03, 0.02, 0.01, 0.0, -0.01, -0.03, -0.05],
            "funding_rate_raw": [0.0006] * 7,
            "funding_percentile_30d": [0.9] * 7,
            "funding_change_8h": [0.0001, 0.0002, 0.0003, 0.0002, 0.0, -0.0001, -0.0002],
            "funding_persistence_7d": [0.0001] * 7,
            "top_ls_ratio": [1.2] * 7,
            "global_ls_ratio": [1.0] * 7,
            "entry_price": [1.0] * 7,
        }
    )
    frame["episode_id"] = _episode_ids(frame, 6)
    return frame


def test_baseline_and_pullback_are_causal_and_pick_different_rows() -> None:
    frame = _rows()
    baseline = TimingRule("base", "test", "test")
    pullback = replace(baseline, rule_id="pullback", min_distance_from_high=0.04)
    assert select_signals(frame, baseline)["feature_time"].iloc[0] == frame["feature_time"].iloc[4]
    assert select_signals(frame, pullback)["feature_time"].iloc[0] == frame["feature_time"].iloc[5]


def test_probability_peak_drop_waits_for_transition() -> None:
    frame = _rows()
    rule = TimingRule(
        "prob-drop", "test", "test", min_probability_peak_drop=0.06
    )
    assert select_signals(frame, rule)["feature_time"].iloc[0] == frame["feature_time"].iloc[5]


def test_metrics_uses_canonical_episode_denominator() -> None:
    frame = _rows()
    result = metrics(frame, TimingRule("base", "test", "test"))
    assert result["signals"] == 1
    assert result["true_positives"] == 1
    assert result["episode_recall"] == 1.0


def test_negative_controls_cannot_be_selected() -> None:
    controls = [rule for rule in rule_catalog() if rule.family == "negative_control"]
    assert controls
    assert all(not rule.selection_eligible for rule in controls)


def test_episode_ids_reset_only_after_strict_gap() -> None:
    frame = _rows().iloc[[0, 1, 6]].copy()
    ids = _episode_ids(frame, 3)
    assert ids.nunique() == 2
