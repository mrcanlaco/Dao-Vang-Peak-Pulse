"""Bounded tests for the precomputed whole-account simulator."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from dao_vang.experiments.open_profit_account import (
    CandidateTrade,
    simulate_account,
)

UTC = timezone.utc
START = datetime(2026, 1, 1, tzinfo=UTC)


def _trade(
    offset: int,
    net_return: float | None,
    *,
    status: str = "closed",
    duration: int | None = 1,
    symbol: str = "BTCUSDT",
    candidate_id: str = "",
) -> CandidateTrade:
    signal = START + timedelta(hours=offset)
    exit_time = (
        signal + timedelta(hours=duration) if duration is not None else None
    )
    return CandidateTrade(
        signal_time=signal,
        exit_time=exit_time,
        symbol=symbol,
        net_return_on_margin=net_return,
        terminal_status=status,
        candidate_id=candidate_id,
    )


def test_conservation_with_realized_profit_and_json_safe_result() -> None:
    result = simulate_account([_trade(0, 0.10)])

    assert result.vault == 100.0
    assert result.reserve == 9_000.0
    assert result.active_equity == 1_000.0
    assert result.final_profit == 100.0
    assert result.final_wealth == 10_100.0
    assert (
        result.vault + result.reserve + result.active_equity
        == result.external_contributions + result.final_profit
    )
    payload = result.to_dict()
    json.dumps(payload)
    assert payload["rankable"] is True
    assert payload["ending_wealth"] == result.final_wealth
    assert payload["account_events"] == payload["events"]
    assert payload["skipped"] == payload["skipped_trades"]


def test_same_signal_tie_uses_caller_order_not_future_exit_or_symbol() -> None:
    first = _trade(0, 0.10, duration=10, symbol="ZZZ", candidate_id="first")
    second = _trade(0, 9.00, duration=1, symbol="AAA", candidate_id="second")

    result = simulate_account([first, second])

    assert result.executed == 1
    assert result.executed_trades[0] == first
    assert result.skipped_overlap == 1
    assert result.vault == 100.0


def test_skipped_overlap_is_audit_only_and_never_rewinds_event_snapshots() -> None:
    result = simulate_account(
        [
            _trade(0, 0.0, duration=10),
            _trade(1, 0.5, duration=1, symbol="ETHUSDT"),
        ]
    )

    event_times = [
        event.timestamp
        for event in result.events
        if event.timestamp is not None
    ]
    assert event_times == sorted(event_times)
    assert result.skipped_overlap == 1


def test_nine_full_losses_one_winner_use_only_finite_tranches() -> None:
    trades = [
        _trade(index * 2, -1.0, symbol=f"S{index:02d}")
        for index in range(9)
    ]
    trades.append(_trade(18, 1.0, symbol="WIN"))

    result = simulate_account(trades)

    assert result.executed == 10
    assert result.tranches_allocated == 10
    assert result.total_capital_seeded == 10_000.0
    assert result.reserve == 0.0
    assert len(result.tranche_burns) == 9
    assert result.vault == 1_000.0
    assert result.active_equity == 1_000.0
    assert result.final_profit == -8_000.0
    assert len(
        [flow for flow in result.cashflows if flow.flow_type == "external_contribution"]
    ) == 1


def test_loss_shrinks_active_tranche_without_refill_or_rescue() -> None:
    result = simulate_account(
        [
            _trade(0, -0.25),
            _trade(2, 0.50),
        ]
    )

    assert result.tranches_allocated == 1
    assert result.reserve == 9_000.0
    assert result.active_equity == 1_000.0
    assert result.vault == 125.0
    assert result.final_profit == 125.0
    assert len(result.cashflows) == 3
    assert [flow.flow_type for flow in result.cashflows].count(
        "external_contribution"
    ) == 1


def test_withdrawal_and_reinvestment_change_buckets_not_alpha() -> None:
    withdrawn = simulate_account([_trade(0, 0.20)], withdraw_profits=True)
    reinvested = simulate_account([_trade(0, 0.20)], withdraw_profits=False)

    assert withdrawn.final_profit == reinvested.final_profit == 200.0
    assert withdrawn.vault == 200.0
    assert withdrawn.active_equity == 1_000.0
    assert reinvested.vault == 0.0
    assert reinvested.active_equity == 1_200.0
    assert withdrawn.external_contributions == reinvested.external_contributions


def test_mark_to_cutoff_locks_equity_without_unrealized_withdrawal() -> None:
    result = simulate_account(
        [
            _trade(0, 0.20, status="mark_to_cutoff"),
            _trade(2, 0.50, symbol="ETHUSDT"),
        ]
    )

    assert result.locked_mark_to_cutoff is True
    assert result.vault == 0.0
    assert result.active_equity == 1_200.0
    assert result.final_profit == 200.0
    assert result.skipped_blocked == 0
    assert result.skipped_trades[0].reason == "active_mark_to_cutoff_locked"
    assert result.closed_event_drawdown == ()


def test_missing_entry_skips_but_unresolved_selected_path_blocks_rest() -> None:
    missing_entry = CandidateTrade(
        signal_time=None,
        exit_time=None,
        symbol="BTCUSDT",
        net_return_on_margin=None,
        terminal_status="incomplete",
    )
    resolved_after = _trade(2, 0.0)
    result = simulate_account([missing_entry, resolved_after])
    assert result.skipped_incomplete == 1
    assert result.executed == 1
    assert result.final_profit == 0.0

    unresolved = _trade(
        0,
        None,
        status="unresolved",
        duration=4,
        candidate_id="unknown-path",
    )
    later = _trade(5, 1.0, candidate_id="must-not-run")
    unknown_result = simulate_account([unresolved, later])
    assert unknown_result.executed == 1
    assert unknown_result.rankable is False
    assert unknown_result.final_profit is None
    assert unknown_result.capital_occupied_to_cutoff == 1_000.0
    assert unknown_result.skipped_blocked == 1
    assert unknown_result.skipped_incomplete == 0


def test_rejected_at_entry_is_skipped_without_poisoning_account() -> None:
    rejected = _trade(
        0,
        None,
        status="rejected_at_entry",
        duration=None,
        candidate_id="entry-rejected",
    )
    valid = _trade(2, 0.10, candidate_id="valid")

    result = simulate_account([rejected, valid])

    assert result.skipped_incomplete == 1
    assert result.skipped_trades[0].reason == "incomplete_entry"
    assert result.executed == 1
    assert result.rankable is True
    assert result.final_profit == 100.0


def test_invalid_exit_after_known_entry_is_non_rankable() -> None:
    invalid_path = CandidateTrade(
        signal_time=START,
        exit_time=START - timedelta(hours=1),
        symbol="BTCUSDT",
        net_return_on_margin=0.5,
        terminal_status="closed",
    )
    later = _trade(2, 0.5)

    result = simulate_account([invalid_path, later])

    assert result.executed == 1
    assert result.rankable is False
    assert result.final_profit is None
    assert result.skipped_blocked == 1


def test_return_at_or_below_minus_one_is_explicit_full_margin_loss_proxy() -> None:
    result = simulate_account([_trade(0, -1.5)])

    assert result.active_equity == 0.0
    assert result.tranche_burns == (1,)
    assert result.final_profit == -1_000.0
    close_events = [event for event in result.events if event.event_type == "trade_closed"]
    assert close_events[0].reason == "full_margin_loss_proxy"


def test_all_losses_report_operating_and_wealth_ruin_without_refill() -> None:
    result = simulate_account(
        [_trade(index * 2, -1.0, symbol=f"S{index:02d}") for index in range(10)]
    )

    assert result.tranches_allocated == 10
    assert result.reserve == 0.0
    assert result.active_equity == 0.0
    assert result.operating_exhaustion is True
    assert result.wealth_ruin is True
    assert result.final_profit == -10_000.0


def test_closed_event_drawdown_is_absolute_and_excludes_mtm_event() -> None:
    result = simulate_account(
        [
            _trade(0, 0.20),
            _trade(2, -0.50),
            _trade(4, 0.50, status="mark_to_cutoff"),
        ]
    )

    assert result.closed_event_drawdown == (0.0, 500.0)
    assert result.max_closed_event_drawdown == 500.0
    assert "absolute account currency" in result.drawdown_basis
