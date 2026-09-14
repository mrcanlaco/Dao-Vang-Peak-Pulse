from types import SimpleNamespace

import pandas as pd
import pytest

from scripts.forward48_execution_risk_search import Variant, simulate
from scripts.forward48_funding_execution_compatibility import (
    BASELINE_ID,
    attach_scout_mask,
    four_cells,
    funding_exhaustion_rising,
)


def test_funding_scout_predicate_is_exact_and_strict_on_positive_fields():
    frame = pd.DataFrame(
        {
            "funding_percentile_30d": [0.80, 0.7999, 0.90, 0.90],
            "funding_persistence_7d": [0.01, 0.01, 0.0, 0.01],
            "funding_change_8h": [0.01, 0.01, 0.01, 0.0],
        }
    )
    assert funding_exhaustion_rising(frame).tolist() == [True, False, False, False]


def test_exact_intersection_preserves_two_execution_rows_per_signal():
    when = pd.Timestamp("2026-01-01T00:00:00Z")
    execution = pd.DataFrame(
        {
            "symbol": [" abcUSDT ", " abcUSDT "],
            "signal_time": [when, when],
            "variant_id": [BASELINE_ID, "vol_offsets_exhaustion_adds"],
        }
    )
    context = pd.DataFrame(
        {
            "symbol": ["ABCUSDT"],
            "signal_time": [when],
            "funding_percentile_30d": [0.9],
            "funding_persistence_7d": [0.1],
            "funding_change_8h": [0.01],
        }
    )
    merged, coverage = attach_scout_mask(execution, context)
    assert len(merged) == 2
    assert merged["in_funding_slice"].all()
    assert coverage["exact_row_coverage"] == 1.0
    assert coverage["unique_signal_keys"] == 1


def test_exact_intersection_rejects_missing_context():
    when = pd.Timestamp("2026-01-01T00:00:00Z")
    execution = pd.DataFrame(
        {"symbol": ["AUSDT"], "signal_time": [when], "variant_id": [BASELINE_ID]}
    )
    context = pd.DataFrame(
        {
            "symbol": ["BUSDT"],
            "signal_time": [when],
            "funding_percentile_30d": [0.9],
            "funding_persistence_7d": [0.1],
            "funding_change_8h": [0.01],
        }
    )
    with pytest.raises(RuntimeError, match="intersection failed"):
        attach_scout_mask(execution, context)


def test_rising_entry_snapshot_structurally_disables_locked_add_gate():
    start = pd.Timestamp("2026-01-01T00:00:00Z")
    signal = SimpleNamespace(
        signal_id="s1",
        symbol="TESTUSDT",
        feature_time=start,
        entry_price=100.0,
        fold=1,
        price_ret_24h=0.35,
        price_volatility_24h=0.01,
        funding_change_8h=0.01,
        momentum_deceleration_4h=-0.01,
    )
    bars = [
        (start + pd.Timedelta(minutes=5), 107.0, 102.0, 106.0),
        (start + pd.Timedelta(minutes=10), 106.0, 101.0, 102.0),
        (start + pd.Timedelta(hours=48), 102.0, 101.0, 102.0),
    ]
    outcome = simulate(
        Variant(
            "vol_offsets_exhaustion_adds",
            "conditional_add",
            offset_mode="volatility",
            add_gate="exhaustion_reversal",
        ),
        signal,
        bars,
        [],
        {"median_volatility": 0.01, "volatility_q75": 0.02},
    )
    assert outcome["filled_legs"] == 1
    assert outcome["capital_deployed"] == pytest.approx(0.20)


def test_four_cells_reports_all_scope_execution_crosses():
    rows = []
    for in_slice in (False, True):
        for variant in (BASELINE_ID, "vol_offsets_exhaustion_adds"):
            rows.append(
                {
                    "variant_id": variant,
                    "family": "x",
                    "signal_time": pd.Timestamp("2026-01-01T00:00:00Z"),
                    "in_funding_slice": in_slice,
                    "complete_path": True,
                    "target_hit": in_slice,
                    "status": "target" if in_slice else "stop",
                    "ambiguous": False,
                    "filled_legs": 1,
                    "capital_deployed": 0.2,
                    "actual_return": 0.04 if in_slice else -0.032,
                    "conservative_return": 0.04 if in_slice else -0.032,
                    "funding_return": 0.0,
                }
            )
    result = four_cells(pd.DataFrame(rows))
    assert len(result) == 4
    assert result[f"funding_slice__{BASELINE_ID}"]["signals"] == 1
    assert result["funding_slice__vol_offsets_exhaustion_adds"]["target_rate"] == 1.0
