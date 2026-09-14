import duckdb
import pandas as pd
import pytest

from dao_vang.labels.engine_v2 import DistributionLabelEngineV2
from dao_vang.labels.specs.distribution_short_v2 import (
    DistributionShortV2Spec,
    specs,
)


def _timeline(future_low: float, future_high: float = 100.0) -> pd.DataFrame:
    base = pd.Timestamp("2026-01-01 00:00:00")
    rows = [{
        "symbol": "TESTUSDT", "close_time": base, "open": 100.0,
        "high": 100.0, "low": 100.0, "close": 100.0,
        "quality_status": "valid",
    }]
    for index in range(1, 289):
        rows.append({
            "symbol": "TESTUSDT",
            "close_time": base + pd.Timedelta(minutes=5 * index),
            "open": 100.0,
            "high": future_high if index == 6 else 100.0,
            "low": future_low if index == 12 else 100.0,
            "close": 100.0, "quality_status": "valid",
        })
    return pd.DataFrame(rows)


@pytest.mark.parametrize(("future_low", "expected"), [(80.0, 1), (80.0001, 0)])
def test_v2_uses_exact_twenty_percent_boundary(future_low: float, expected: int):
    conn = duckdb.connect(":memory:")
    conn.register("timeline", _timeline(future_low))
    DistributionLabelEngineV2(specs[24]).compute_all_to_table(
        conn, "timeline", "labels"
    )
    row = conn.execute(
        "SELECT label_value, label_version, horizon_hours FROM labels "
        "WHERE signal_time = TIMESTAMP '2026-01-01 00:00:00'"
    ).fetchone()
    assert row == (expected, "distribution_short_v2", 24)


def test_v2_rejects_non_24h_contract():
    with pytest.raises(ValueError, match="only the 24h horizon"):
        DistributionLabelEngineV2(DistributionShortV2Spec(horizon_hours=12))

@pytest.mark.parametrize(
    ("future_high", "expected"),
    [(115.9999, 1), (116.0, 0)],
)
def test_v2_uses_exact_sixteen_percent_mae_boundary(
    future_high: float,
    expected: int,
):
    conn = duckdb.connect(":memory:")
    conn.register("timeline", _timeline(80.0, future_high=future_high))
    DistributionLabelEngineV2(specs[24]).compute_all_to_table(
        conn, "timeline", "labels"
    )

    label = conn.execute(
        "SELECT label_value FROM labels "
        "WHERE signal_time = TIMESTAMP '2026-01-01 00:00:00'"
    ).fetchone()[0]

    assert label == expected
