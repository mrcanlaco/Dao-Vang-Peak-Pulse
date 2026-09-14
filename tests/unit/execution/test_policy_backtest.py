from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from dao_vang.execution.policy_backtest import (
    PolicyBacktestConfig,
    _event_query,
    _funding_return,
)
from dao_vang.execution.policy_challenger import _metrics, _target_for_event
from dao_vang.execution.policy_evaluator import FilledLeg


def _config(model_id: str | None) -> PolicyBacktestConfig:
    return PolicyBacktestConfig(
        db_path=Path("test.duckdb"),
        output_json=Path("report.json"),
        output_csv=Path("events.csv"),
        model_id=model_id,
        probability_threshold=0.60,
        reset_gap_minutes=30,
    )


@pytest.mark.parametrize("model_id", [None, "frozen-model"])
def test_event_query_parameter_count_matches_placeholders(model_id):
    query, params = _event_query(_config(model_id))

    assert query.count("?") == len(params)
    assert params[:2] == [0.60, 0.60]
    assert params[-1] == 30
    if model_id:
        assert params[2] == model_id


def test_funding_uses_only_allocation_filled_before_settlement():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    legs = (
        FilledLeg(1, start, 100.0, 0.2),
        FilledLeg(2, start + timedelta(hours=5), 105.0, 0.3),
    )

    value = _funding_return(
        [
            (start + timedelta(hours=4), 0.001),
            (start + timedelta(hours=8), 0.002),
            (start + timedelta(hours=16), 0.010),
        ],
        legs,
        start + timedelta(hours=10),
    )

    assert value == pytest.approx(0.0012)


def test_challenger_target_has_explicit_skip_class():
    losing = pd.Series(
        {
            "scale_in_compact": -0.01,
            "scale_in_balanced": -0.02,
            "scale_in_deep_squeeze": -0.005,
        }
    )
    winning = pd.Series(
        {
            "scale_in_compact": -0.01,
            "scale_in_balanced": 0.02,
            "scale_in_deep_squeeze": 0.01,
        }
    )

    assert _target_for_event(losing) == "skip"
    assert _target_for_event(winning) == "scale_in_balanced"


def test_challenger_metrics_are_deterministic():
    metrics = _metrics([0.10, -0.05, 0.0])

    assert metrics["events"] == 3
    assert metrics["mean_return"] == pytest.approx(0.01666667)
    assert metrics["positive_rate"] == pytest.approx(0.3333)
    assert metrics["skip_rate"] == pytest.approx(0.3333)
