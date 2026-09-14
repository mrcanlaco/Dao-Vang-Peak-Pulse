from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from dao_vang.config.settings import ExecutionPolicyRouterConfig
from dao_vang.execution.policy_evaluator import PriceBar, evaluate_price_path


def _balanced():
    return next(
        item for item in ExecutionPolicyRouterConfig().templates
        if item.policy_id == "scale_in_balanced"
    )


def test_evaluator_fills_three_legs_and_targets_from_weighted_average():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcome = evaluate_price_path(
        _balanced(),
        signal_time=start,
        signal_price=100.0,
        bars=[
            PriceBar(start, high=100.0, low=99.0),
            PriceBar(start + timedelta(hours=1), high=106.0, low=103.0),
            PriceBar(start + timedelta(hours=2), high=111.0, low=105.0),
            PriceBar(start + timedelta(hours=8), high=107.0, low=85.0),
        ],
    )

    assert outcome.status == "target"
    assert len(outcome.filled_legs) == 3
    assert outcome.average_entry == pytest.approx(106.5)
    assert outcome.target_price == pytest.approx(85.2)
    assert outcome.realized_return == 0.20


def test_evaluator_recomputes_target_when_only_first_leg_fills():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcome = evaluate_price_path(
        _balanced(),
        signal_time=start,
        signal_price=100.0,
        bars=[
            PriceBar(start, high=100.0, low=99.0),
            PriceBar(start + timedelta(hours=7), high=101.0, low=79.0),
        ],
    )

    assert len(outcome.filled_legs) == 1
    assert outcome.average_entry == 100.0
    assert outcome.target_price == 80.0
    assert outcome.status == "target"


def test_same_bar_stop_and_target_is_conservative():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcome = evaluate_price_path(
        _balanced(),
        signal_time=start,
        signal_price=100.0,
        bars=[PriceBar(start, high=120.0, low=70.0)],
    )

    assert outcome.status == "stop_ambiguous"
    assert outcome.target_hit is False
    assert outcome.realized_return is not None
    assert outcome.realized_return < 0


def test_orders_do_not_fill_after_scale_in_window():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcome = evaluate_price_path(
        _balanced(),
        signal_time=start,
        signal_price=100.0,
        bars=[
            PriceBar(start, high=100.0, low=99.0),
            PriceBar(start + timedelta(hours=7), high=111.0, low=95.0),
        ],
    )

    assert len(outcome.filled_legs) == 1


def test_invalid_bar_is_rejected():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="bar high"):
        evaluate_price_path(
            _balanced(),
            signal_time=start,
            signal_price=100.0,
            bars=[PriceBar(start, high=90.0, low=100.0)],
        )

def test_timeout_is_marked_to_market_at_last_close():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    outcome = evaluate_price_path(
        _balanced(),
        signal_time=start,
        signal_price=100.0,
        bars=[
            PriceBar(start, high=100.0, low=99.0, close=99.5),
            PriceBar(
                start + timedelta(hours=24),
                high=101.0,
                low=89.0,
                close=90.0,
            ),
        ],
    )

    assert outcome.status == "timeout"
    assert outcome.realized_return == pytest.approx(0.10)
