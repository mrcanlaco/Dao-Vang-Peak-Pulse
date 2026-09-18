from datetime import datetime, timedelta, timezone

import pytest

from dao_vang.labels.dual_outcomes_v3 import evaluate_dual
from dao_vang.labels.engine_v3 import Bar

START = datetime(2026, 9, 1, tzinfo=timezone.utc)
STEP = timedelta(minutes=5)


def bar(index: int, *, open: float = 100, high: float = 101, low: float = 99, close: float = 100) -> Bar:
    return Bar(START + STEP * index, open, high, low, close)


def run(bars: list[Bar], **kwargs):
    args = {
        "signal_time": START,
        "signal_price": 100,
        "bars": bars,
        "funding": [],
        "funding_coverage_through": START + timedelta(hours=48),
    }
    args.update(kwargs)
    return evaluate_dual(**args)


def test_stop_then_recovery_is_separate_from_actual_win():
    result = run([
        bar(1, high=117, low=99, close=115),
        bar(2, high=115, low=79, close=90),
    ])

    assert result.actual.status == "stop"
    assert result.actual_win is False
    assert result.post_stop.status == "target_after_stop"
    assert result.post_stop.frozen_average_entry == pytest.approx(100)
    assert result.post_stop.frozen_target_price == pytest.approx(80)
    assert result.post_stop.target_after_stop is True
    assert result.paired_evidence_eligible
    assert result.to_dict()["actual_win"] is False


def test_ambiguous_stop_candle_low_is_not_post_stop_target():
    result = run([
        bar(1, high=120, low=70, close=100),
        bar(2, high=110, low=79, close=90),
    ])

    assert result.actual.status == "stop_ambiguous"
    assert result.post_stop.status == "target_after_stop"
    assert result.post_stop.target_time == START + STEP * 2


def test_actual_target_has_no_stop_diagnostic():
    result = run([bar(1, high=110, low=75, close=90)])

    assert result.actual.status == "target"
    assert result.post_stop.status == "not_applicable"
    assert result.post_stop.stop_time is None
    assert result.post_stop.target_after_stop is None


def test_stop_on_horizon_is_post_stop_timeout():
    bars = [bar(index) for index in range(1, 576)]
    bars.append(bar(576, high=117, low=100, close=115))
    result = run(bars)

    assert result.actual.status == "stop"
    assert result.actual.exit_time == START + timedelta(hours=48)
    assert result.post_stop.status == "timeout_after_stop"
    assert result.post_stop.observed_bars == 0


def test_post_stop_gap_is_explicit_and_entry1_dual_is_rejected():
    result = run([bar(1, high=117, low=99, close=115), bar(3, low=79)])
    assert result.post_stop.status == "price_path_gap_after_stop"
    assert not result.paired_evidence_eligible

    with pytest.raises(ValueError, match="compact-only"):
        run([bar(1, high=117)], entry1_only=True)
