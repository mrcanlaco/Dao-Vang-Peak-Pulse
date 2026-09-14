from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.forward48_execution_risk_search import Variant, simulate
from scripts.forward48_true_funding_transition import (
    settlement_audit,
    strict_transition_mask,
    transition_table,
)


def test_strict_transition_requires_change_and_rate_rollover():
    frame = pd.DataFrame(
        {
            "funding_change_8h": [-0.1, 0.1, -0.1],
            "funding_rate_raw": [0.4, 0.4, 0.6],
            "entry_funding_rate": [0.5, 0.5, 0.5],
        }
    )
    assert strict_transition_mask(frame).tolist() == [True, False, False]


def test_transition_table_uses_only_later_observed_rows_and_does_not_synthesize():
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    signals = pd.DataFrame(
        {
            "signal_id": ["a", "b"],
            "feature_time": [start, start],
            "funding_rate_raw": [0.5, 0.5],
        }
    )
    updates = pd.DataFrame(
        {
            "signal_id": ["a", "a", "b"],
            "entry_time": [start, start, start],
            "entry_funding_rate": [0.5, 0.5, 0.5],
            "update_time": [
                start + pd.Timedelta(hours=5),
                start + pd.Timedelta(hours=8),
                pd.NaT,
            ],
            "funding_rate_raw": [0.4, 0.3, None],
            "funding_change_8h": [-0.1, -0.2, None],
        }
    )
    result, audit = transition_table(signals, updates)
    assert result.loc[0, "transition_time_6h"] == start + pd.Timedelta(hours=5)
    assert pd.isna(result.loc[1, "transition_time_12h"])
    assert audit["6h"]["observation_coverage"] == 0.5


def test_true_transition_gate_waits_for_later_timestamp_and_price_reversal():
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    signal = SimpleNamespace(
        signal_id="s",
        symbol="TESTUSDT",
        feature_time=start,
        entry_price=100.0,
        fold=1,
        price_ret_24h=0.35,
        price_volatility_24h=0.01,
        funding_change_8h=0.01,
        momentum_deceleration_4h=-0.01,
        transition_time=start + pd.Timedelta(hours=2),
    )
    bars = [
        (start + pd.Timedelta(hours=1), 104.0, 102.0, 102.0),
        (start + pd.Timedelta(hours=2), 104.0, 101.0, 103.0),
        (start + pd.Timedelta(hours=2, minutes=5), 103.0, 101.0, 102.0),
        (start + pd.Timedelta(hours=48), 102.0, 101.0, 102.0),
    ]
    outcome = simulate(
        Variant(
            "true_transition_6h",
            "true_funding_transition",
            window_hours=6,
            offset_mode="volatility",
            add_gate="true_transition",
        ),
        signal,
        bars,
        [],
        {"median_volatility": 0.01, "volatility_q75": 0.02},
    )
    assert outcome["filled_legs"] == 2
    assert outcome["capital_deployed"] == pytest.approx(0.5)


def test_true_transition_without_observation_never_adds():
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    signal = SimpleNamespace(
        signal_id="s",
        symbol="TESTUSDT",
        feature_time=start,
        entry_price=100.0,
        fold=1,
        price_ret_24h=0.35,
        price_volatility_24h=0.01,
        funding_change_8h=0.01,
        momentum_deceleration_4h=-0.01,
        transition_time=pd.NaT,
    )
    bars = [
        (start + pd.Timedelta(hours=1), 107.0, 101.0, 102.0),
        (start + pd.Timedelta(hours=48), 102.0, 101.0, 102.0),
    ]
    outcome = simulate(
        Variant(
            "true_transition_6h",
            "true_funding_transition",
            add_gate="true_transition",
        ),
        signal,
        bars,
        [],
        {"median_volatility": 0.01, "volatility_q75": 0.02},
    )
    assert outcome["filled_legs"] == 1


def test_settlement_audit_reports_actual_event_coverage():
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    signals = pd.DataFrame(
        {"signal_id": ["a", "b"], "feature_time": [start, start]}
    )
    funding = {
        "a": [(start + pd.Timedelta(hours=4), 0.001)],
        "b": [(start + pd.Timedelta(hours=8), 0.001)],
    }
    report = settlement_audit(signals, funding)
    assert report["6h"]["settlement_coverage"] == 0.5
    assert report["12h"]["settlement_coverage"] == 1.0
