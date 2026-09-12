from __future__ import annotations

import pytest

from dao_vang.config.settings import ScoringConfig
from dao_vang.scoring.engine_comparison import (
    _calculate_summary,
    _unavailable_engine_comparison,
    evaluate_scoring_engines_comparison,
)


class _BrokenConnection:
    def execute(self, *_args, **_kwargs):
        raise RuntimeError("no comparison tables")


def test_query_failure_returns_unavailable_without_synthetic_metrics() -> None:
    result = evaluate_scoring_engines_comparison(
        _BrokenConnection(),
        ScoringConfig(),
    )

    assert result["status"] == "unavailable"
    assert result["sample_count"] == 0
    assert result["comparison"] == {}
    assert result["verdict"] is None


def test_summary_uses_observed_lead_times() -> None:
    signals = [
        {
            "hit_tp1": True,
            "hit_tp2": False,
            "breach_sl": False,
            "mae": 0.01,
            "mfe": 0.05,
            "lead_time_min": 10.0,
        },
        {
            "hit_tp1": True,
            "hit_tp2": True,
            "breach_sl": False,
            "mae": 0.02,
            "mfe": 0.09,
            "lead_time_min": 30.0,
        },
    ]

    summary = _calculate_summary(signals, "engine", "version")

    assert summary.mean_lead_time_min == pytest.approx(20.0)


def test_empty_summary_does_not_invent_baseline_metrics() -> None:
    summary = _calculate_summary([], "engine", "version").to_dict()
    unavailable = _unavailable_engine_comparison("no_rows")

    assert summary["total_signals"] == 0
    assert summary["mean_lead_time_min"] is None
    assert summary["precision_score"] == 0.0
    assert unavailable["comparison"] == {}
