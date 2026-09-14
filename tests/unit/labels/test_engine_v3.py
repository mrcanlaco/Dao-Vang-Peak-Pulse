from datetime import datetime, timedelta, timezone

import pytest

from dao_vang.labels.engine_v3 import Bar, Funding, evaluate
from dao_vang.labels.specs.distribution_short_v3 import SPEC

START = datetime(2026, 9, 1, tzinfo=timezone.utc)
STEP = timedelta(minutes=5)


def bar(index=1, *, open=100, high=101, low=99, close=100):
    return Bar(START + STEP * index, open, high, low, close)


def run(bars, **kwargs):
    args = dict(
        signal_time=START,
        signal_price=100,
        bars=bars,
        funding=[],
        funding_coverage_through=START + timedelta(hours=48),
    )
    args.update(kwargs)
    return evaluate(**args)


def test_notional_weights_use_quantity_average_and_rebase_both_limits():
    result = run([bar(high=106, low=90)])
    assert len(result.fills) == 3
    avg = 1 / (0.2 / 100 + 0.3 / 103 + 0.5 / 106)
    last = result.fills[-1]
    assert last.average_entry == pytest.approx(avg)
    assert last.target_price == pytest.approx(avg * 0.8)
    assert last.stop_price == pytest.approx(avg * 1.16)
    assert last.average_entry != pytest.approx(103.9)
    assert result.status == "incomplete"
    assert result.label is None


def test_old_stop_precedes_adds_and_ambiguous_target():
    result = run([bar(high=130, low=70)])
    assert result.status == "stop_ambiguous"
    assert len(result.fills) == 1
    assert result.exit_price == pytest.approx(116)
    assert result.gross_return_planned == pytest.approx(-0.032)
    assert result.costs_planned == pytest.approx(0.000432)
    assert result.label == 0


def test_old_target_precedes_adds_in_ambiguous_fill_candle():
    result = run([bar(high=110, low=75, close=90)])
    assert result.status == "target"
    assert len(result.fills) == 1
    assert result.gross_return_planned == pytest.approx(0.04)
    assert result.net_return_planned == pytest.approx(0.03964)


def test_prefill_low_cannot_claim_rebased_target():
    result = run([bar(high=106, low=82, close=95)])
    assert len(result.fills) == 3
    assert result.status == "incomplete"
    assert result.label is None


def test_fill_bar_close_can_confirm_rebased_target():
    result = run([bar(high=106, low=82, close=82)])
    assert result.status == "target"
    assert result.gross_return_planned == pytest.approx(0.20)
    assert result.costs_planned == pytest.approx(0.0018)


def test_price_gaps_stop_at_worse_open_and_target_without_improvement():
    stopped = run([bar(open=125, high=128, low=120, close=123)])
    assert stopped.exit_price == 125
    assert stopped.exit_time == START
    assert len(stopped.fills) == 1
    target = run([bar(open=75, high=130, low=70, close=100)])
    assert target.status == "target"  # open observed before later stop touch
    assert target.exit_price == 80


def test_rebased_stop_is_used_in_next_bar():
    result = run([bar(high=106), bar(2, high=122)])
    assert result.status == "stop"
    assert result.exit_price == pytest.approx(result.fills[-1].stop_price)
    assert result.gross_return_planned == pytest.approx(-0.16)


def test_timeout_requires_full_48h_and_marks_final_close():
    result = run([bar(i, close=99) for i in range(1, 577)])
    assert result.status == "timeout"
    assert result.exit_time == START + timedelta(hours=48)
    assert result.exit_price == 99
    assert result.gross_return_planned == pytest.approx(0.002)
    assert result.net_return_deployed == pytest.approx(0.00801)
    assert run([bar(i) for i in range(1, 576)]).status == "incomplete"


def test_gap_before_exit_excludes_but_data_after_exit_is_unnecessary():
    assert run([bar(), bar(3, low=70)]).exclusion_reason == "price_path_gap"
    assert run([bar(low=70)]).eligible
    assert run([]).label is None


def test_scale_in_expires_at_6h_without_resetting_horizon():
    at_limit = run([bar(i) for i in range(1, 72)] + [bar(72, high=106)])
    after_limit = run([bar(i) for i in range(1, 73)] + [bar(73, high=106)])
    assert len(at_limit.fills) == 3
    assert len(after_limit.fills) == 1


def test_funding_uses_filled_quantity_and_signed_cash_flow():
    events = [
        Funding(START, 1.0, 100),  # already settled before entry1
        Funding(START + STEP, 0.001, 105),
        Funding(START + STEP * 2, -0.002, 100),
    ]
    result = run([bar(high=103), bar(2, high=106), bar(3, low=80)], funding=events)
    q1 = 0.2 / 100 + 0.3 / 103
    q2 = q1 + 0.5 / 106
    expected = q1 * 105 * 0.001 - q2 * 100 * 0.002
    assert len(result.funding_payments) == 2
    assert result.funding_planned == pytest.approx(expected)
    assert result.net_return_planned == pytest.approx(0.2 - 0.0018 + expected)


def test_timeout_includes_horizon_settlement():
    result = run(
        [bar(i) for i in range(1, 577)],
        funding=[Funding(START + timedelta(hours=48), -0.01, 100)],
    )
    assert result.funding_planned == pytest.approx(-0.002)


@pytest.mark.parametrize("coverage", [None, START])
def test_missing_funding_does_not_silently_become_zero(coverage):
    result = run([bar(low=70)], funding_coverage_through=coverage)
    assert result.status == "target"
    assert not result.eligible
    assert result.label is None
    assert result.net_return_planned is None
    assert result.exclusion_reason == "funding_coverage_incomplete"


def test_entry1_diagnostic_does_not_scale_in():
    result = run([bar(high=106), bar(2, high=120)], entry1_only=True)
    assert result.status == "stop"
    assert len(result.fills) == 1
    assert result.deployed_notional == 1
    assert result.mode == "entry1_diagnostic"


@pytest.mark.parametrize(
    "bad_bars",
    [
        [bar(0)],
        [bar(), bar()],
        [bar(2), bar()],
        [bar(high=float("nan"))],
        [bar(low=0)],
        [bar(high=99)],
        [Bar(START + timedelta(minutes=6), 100, 101, 99, 100)],
        [Bar(START.replace(tzinfo=None) + STEP, 100, 101, 99, 100)],
    ],
)
def test_reject_invalid_paths(bad_bars):
    with pytest.raises(ValueError):
        run(bad_bars)


def test_reject_duplicate_or_unaligned_funding():
    settlement = Funding(START + STEP, 0.001, 100)
    with pytest.raises(ValueError, match="duplicate"):
        run([bar()], funding=[settlement, settlement])
    with pytest.raises(ValueError, match="aligned"):
        run([bar()], funding=[Funding(START + timedelta(seconds=1), 0.01, 100)])


def test_funding_tolerates_exchange_millisecond_jitter_and_retains_timestamp():
    jitter_time = START + STEP + timedelta(milliseconds=11)
    event = Funding(jitter_time, 0.001, 100)
    result = run([bar(), bar(2, low=70)], funding=[event])
    assert len(result.funding_payments) == 1
    assert result.funding_payments[0].timestamp == jitter_time
    assert result.funding_payments[0].rate == 0.001

    with pytest.raises(ValueError, match="aligned"):
        run([bar()], funding=[Funding(START + STEP + timedelta(milliseconds=60), 0.001, 100)])

def test_contract_is_frozen_and_versioned():
    assert len(SPEC.checksum) == 64
    assert SPEC.horizon_hours == 48
    with pytest.raises(AttributeError):
        SPEC.target = 0.08
