from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.forward48_execution_risk_search import (
    BASELINE_ID,
    HARD_STOP,
    Variant,
    _holm_adjust,
    simulate,
    variants,
)


def _signal(**overrides):
    values = {
        "signal_id": "s1",
        "symbol": "TESTUSDT",
        "feature_time": pd.Timestamp("2026-01-01T00:00:00Z"),
        "entry_price": 100.0,
        "fold": 1,
        "price_ret_24h": 0.35,
        "price_volatility_24h": 0.01,
        "funding_change_8h": -0.001,
        "momentum_deceleration_4h": -0.01,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


DEV_STATS = {"median_volatility": 0.01, "volatility_q75": 0.02}


def test_variant_set_is_small_unique_and_preserves_contract():
    items = variants()
    assert items[0].variant_id == BASELINE_ID
    assert len(items) == 16
    assert len({item.variant_id for item in items}) == len(items)
    assert all(item.time_stop_hours <= 48 for item in items)
    assert all(sum(item.allocations) == pytest.approx(1.0) for item in items)


def test_same_bar_target_and_stop_is_stop_first():
    signal = _signal()
    when = signal.feature_time + pd.Timedelta(minutes=5)
    outcome = simulate(
        Variant(BASELINE_ID, "baseline"),
        signal,
        [(when, 125.0, 75.0, 100.0)],
        [],
        DEV_STATS,
    )
    assert outcome["status"] == "stop_ambiguous"
    assert outcome["target_hit"] is False
    assert outcome["actual_return"] < -HARD_STOP * 0.19


def test_exhaustion_reversal_gate_does_not_add_without_transition():
    signal = _signal(funding_change_8h=0.001)
    bars = [
        (signal.feature_time + pd.Timedelta(minutes=5), 104.0, 102.0, 103.0),
        (signal.feature_time + pd.Timedelta(minutes=10), 103.0, 101.0, 102.0),
        (signal.feature_time + pd.Timedelta(hours=48), 102.0, 101.0, 102.0),
    ]
    outcome = simulate(
        Variant("gate", "conditional_add", add_gate="exhaustion_reversal"),
        signal,
        bars,
        [],
        DEV_STATS,
    )
    assert outcome["filled_legs"] == 1
    assert outcome["capital_deployed"] == pytest.approx(0.20)


def test_reversal_gate_adds_after_touch_then_causal_pullback():
    signal = _signal()
    bars = [
        (signal.feature_time + pd.Timedelta(minutes=5), 104.0, 102.0, 103.5),
        (signal.feature_time + pd.Timedelta(minutes=10), 103.0, 101.0, 102.0),
        (signal.feature_time + pd.Timedelta(hours=48), 102.0, 101.0, 102.0),
    ]
    outcome = simulate(
        Variant("gate", "conditional_add", add_gate="exhaustion_reversal"),
        signal,
        bars,
        [],
        DEV_STATS,
    )
    assert outcome["filled_legs"] == 2
    assert outcome["capital_deployed"] == pytest.approx(0.50)


def test_new_breakeven_trail_cannot_resolve_same_bar_high_low_order():
    signal = _signal()
    bars = [
        (signal.feature_time + pd.Timedelta(minutes=5), 115.0, 89.0, 95.0),
        (signal.feature_time + pd.Timedelta(minutes=10), 105.0, 95.0, 100.0),
        (signal.feature_time + pd.Timedelta(hours=48), 100.0, 99.0, 100.0),
    ]
    outcome = simulate(
        Variant("trail", "exit_management", breakeven_after_10=True),
        signal,
        bars,
        [],
        DEV_STATS,
    )
    assert outcome["status"] == "breakeven_stop"
    assert outcome["exit_time"] == bars[1][0]


def test_holm_adjustment_is_monotone_in_sorted_p_values():
    adjusted = _holm_adjust([("a", 0.01), ("b", 0.04), ("c", 0.03)])
    assert adjusted["a"] == pytest.approx(0.03)
    assert adjusted["c"] >= adjusted["a"]
    assert adjusted["b"] >= adjusted["c"]
