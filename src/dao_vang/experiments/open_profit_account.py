"""Deterministic whole-account accounting over precomputed trade outcomes.

This module deliberately does not read prices, features, policy decisions, or
live state. A caller supplies already-computed candidate trade paths and their
net return on the margin used by the active isolated tranche. Fees, funding,
slippage, and liquidation effects must already be included in that return.

The baseline is a sequential, isolated-tranche account with three disjoint
asset buckets:

* vault (W): protected realized profit;
* reserve (U): unallocated research cash; and
* active_equity (E): equity in the one active tranche.

Positive excess above a tranche seed is swept from E to W when
withdraw_profits is true. No rescue funding or automatic refill is performed.
Incomplete entry candidates are skipped; an explicitly unresolved future path
after a known entry occupies the selected tranche and makes the account
non-rankable rather than turning missing data into a loss.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Iterable, Mapping

_EPSILON = 1e-9
_UTC = timezone.utc
_MAX_TIME = datetime.max.replace(tzinfo=_UTC)

# A missing entry is not a trading loss and cannot consume a tranche.
_ENTRY_REJECT_STATUSES = frozenset(
    {
        "incomplete",
        "excluded",
        "not_applicable",
        "missing_entry",
        "entry_missing",
        "entry_unavailable",
        "invalid_entry",
        "no_entry",
        "no_signal",
        "unknown_entry",
        "rejected_at_entry",
    }
)

# These statuses mean the entry was selected but the future path is unknown.
# They intentionally block subsequent opportunities: silently skipping them
# would look like favorable capital reuse.
_UNRESOLVED_STATUSES = frozenset(
    {
        "unresolved",
        "unknown_after_entry",
        "incomplete_after_entry",
        "path_incomplete",
        "future_unknown",
        "open_unknown",
        "open",
    }
)

_MARK_TO_CUTOFF_STATUSES = frozenset(
    {
        "mark_to_cutoff",
        "marked_to_cutoff",
        "open_at_cutoff",
        "mtm_at_cutoff",
        "cutoff_mtm",
    }
)


@dataclass(frozen=True, slots=True)
class CandidateTrade:
    """One precomputed candidate path.

    net_return_on_margin is a fractional return on the currently active
    tranche equity: 0.10 means +10% and -1.0 means total margin loss. The
    value already includes fees, funding, slippage, and liquidation effects
    available to the upstream path evaluator.
    """

    signal_time: datetime | str | None
    exit_time: datetime | str | None
    symbol: str
    net_return_on_margin: float | int | None
    terminal_status: str | None
    candidate_id: str = ""


@dataclass(frozen=True, slots=True)
class CashFlow:
    """A disjoint-bucket transfer or external contribution."""

    timestamp: datetime | None
    flow_type: str
    amount: float
    source: str
    destination: str
    candidate_id: str | None = None
    tranche_id: int | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class AccountEvent:
    """A full account snapshot after one ledger event."""

    timestamp: datetime | None
    event_type: str
    vault: float
    reserve: float
    active_equity: float
    wealth: float | None
    profit: float | None
    candidate_id: str | None = None
    symbol: str | None = None
    tranche_id: int | None = None
    terminal_status: str | None = None
    reason: str | None = None
    amount: float | None = None
    realized: bool = False
    locked: bool = False
    active_trade_exit: datetime | None = None


@dataclass(frozen=True, slots=True)
class SkippedTrade:
    """A candidate that did not enter the account path."""

    trade: CandidateTrade
    reason: str


@dataclass(frozen=True, slots=True)
class ExecutedTrade:
    """Execution accounting for one selected trade path."""

    trade: CandidateTrade
    tranche_id: int
    margin_before: float
    net_return_on_margin: float | None
    pnl: float | None
    margin_after: float
    withdrawn_profit: float
    terminal_status: str
    realized: bool
    locked: bool


@dataclass(slots=True)
class AccountSimulationResult:
    """Complete result of simulate_account.

    final_profit and final_wealth are None when an unresolved selected future
    path prevents ranking. Known bucket balances and
    capital_occupied_to_cutoff remain available for audit.
    """

    initial_capital: float
    tranche_count: int
    tranche_seed: float
    withdraw_profits: bool
    external_contributions: float
    vault: float
    reserve: float
    active_equity: float
    final_wealth: float | None
    final_profit: float | None
    opportunities: int
    executed: int
    skipped_overlap: int
    skipped_incomplete: int
    skipped_no_capital: int
    skipped_blocked: int
    executed_trades: tuple[CandidateTrade, ...]
    executed_records: tuple[ExecutedTrade, ...]
    skipped_trades: tuple[SkippedTrade, ...]
    skipped_overlap_trades: tuple[SkippedTrade, ...]
    skipped_incomplete_trades: tuple[SkippedTrade, ...]
    cashflows: tuple[CashFlow, ...]
    events: tuple[AccountEvent, ...]
    tranches_allocated: int
    tranche_burns: tuple[int, ...]
    operating_exhaustion: bool
    wealth_ruin: bool | None
    non_rankable: bool
    unresolved_after_entry: bool
    locked_mark_to_cutoff: bool
    capital_occupied_to_cutoff: float
    closed_event_drawdown: tuple[float, ...]
    max_closed_event_drawdown: float
    drawdown_basis: str = (
        "closed_event_equity_only; absolute account currency; "
        "excludes intratrade path"
    )

    @property
    def snapshots(self) -> tuple[AccountEvent, ...]:
        """Alias emphasizing that every event carries a full account snapshot."""

        return self.events

    @property
    def profit(self) -> float | None:
        """Short alias for the final account profit."""

        return self.final_profit

    @property
    def rankable(self) -> bool:
        """Whether final wealth/profit is fully determined by the paths."""

        return not self.non_rankable

    @property
    def total_capital_seeded(self) -> float:
        """Total tranche seed transferred from reserve, never more than C."""

        return self.tranches_allocated * self.tranche_seed

    @property
    def tranches_remaining(self) -> int:
        return max(self.tranche_count - self.tranches_allocated, 0)

    @property
    def account_ruin(self) -> bool | None:
        """Compatibility alias for wealth ruin; operating exhaustion is separate."""

        return self.wealth_ruin

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly, recursively serialized result."""

        result = _jsonable(self)
        result["rankable"] = self.rankable
        result["ending_wealth"] = result["final_wealth"]
        result["account_events"] = result["events"]
        result["skipped"] = result["skipped_trades"]
        result["burns"] = result["tranche_burns"]
        return result

    as_dict = to_dict

    def __getitem__(self, key: str) -> Any:
        """Allow small consumers to use result["final_profit"] if desired."""

        return getattr(self, key)


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {
            item.name: _jsonable(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def _normalise_time(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        result = datetime.fromisoformat(text)
    else:
        raise TypeError(f"unsupported timestamp type: {type(value).__name__}")
    if result.tzinfo is None:
        result = result.replace(tzinfo=_UTC)
    return result.astimezone(_UTC)


def _safe_time(value: datetime | str | None) -> datetime | None:
    try:
        return _normalise_time(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _normalise_status(value: str | None) -> str:
    if value is None:
        return ""
    return str(value).strip().lower().replace("-", "_").replace(" ", "_")


def _safe_return(value: float | int | None) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(result):
        return None
    # A path loss at or beyond full isolated margin is an explicit
    # full-margin-loss proxy. The account layer cannot represent negative
    # isolated equity, so the caller clamps the equity at zero.
    return -1.0 if result <= -1.0 else result


def _is_full_margin_loss(value: float | int | None) -> bool:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(result) and result <= -1.0


def _clean(value: float) -> float:
    return 0.0 if abs(value) <= _EPSILON else float(value)


def _sort_key(item: tuple[int, CandidateTrade]) -> tuple[Any, ...]:
    index, trade = item
    signal = _safe_time(trade.signal_time)
    return (
        signal is None,
        signal or _MAX_TIME,
        index,
    )


def simulate_account(
    trades: Iterable[CandidateTrade],
    initial_capital: float = 10_000.0,
    tranche_count: int = 10,
    withdraw_profits: bool = True,
) -> AccountSimulationResult:
    """Simulate one sequential isolated-tranche account.

    A tranche is allocated only when no tranche is active and reserve can fund
    the fixed seed. Multiple non-overlapping opportunities can use the same
    surviving tranche; losses shrink that tranche's equity. A zero-margin
    tranche burns, and the next opportunity may allocate a fresh tranche from
    reserve. No automatic refill, rescue funding, or vault reinvestment is
    performed.

    mark_to_cutoff-style statuses apply a known MTM return, keep the equity
    locked, and never sweep unrealized excess to the vault. Explicit
    unresolved-after-entry statuses select the trade but block all later
    opportunities and return a non-rankable result.
    """

    try:
        capital = float(initial_capital)
    except (TypeError, ValueError) as exc:
        raise ValueError("initial_capital must be a positive finite number") from exc
    if not isfinite(capital) or capital <= 0:
        raise ValueError("initial_capital must be a positive finite number")
    if isinstance(tranche_count, bool) or int(tranche_count) != tranche_count:
        raise ValueError("tranche_count must be a positive integer")
    if tranche_count <= 0:
        raise ValueError("tranche_count must be a positive integer")

    source = list(trades)
    if any(not isinstance(trade, CandidateTrade) for trade in source):
        raise TypeError("trades must contain CandidateTrade instances")
    ordered = sorted(enumerate(source), key=_sort_key)

    seed = capital / int(tranche_count)
    vault = 0.0
    reserve = capital
    active_equity = 0.0
    active_tranche_id: int | None = None
    allocated_count = 0
    last_exit: datetime | None = None
    active_locked = False
    locked_mark_to_cutoff = False
    unresolved_after_entry = False
    non_rankable = False
    capital_occupied_to_cutoff = 0.0

    cashflows: list[CashFlow] = [
        CashFlow(
            timestamp=None,
            flow_type="external_contribution",
            amount=capital,
            source="external",
            destination="reserve",
            reason="initial_capital",
        )
    ]
    events: list[AccountEvent] = []
    skipped: list[SkippedTrade] = []
    executed_trades: list[CandidateTrade] = []
    executed_records: list[ExecutedTrade] = []
    tranche_burns: list[int] = []
    closed_drawdowns: list[float] = []
    skipped_overlap_trades: list[SkippedTrade] = []
    skipped_incomplete_trades: list[SkippedTrade] = []
    skipped_no_capital = 0
    skipped_blocked = 0
    peak_closed_wealth = capital

    def current_wealth() -> float | None:
        if non_rankable:
            return None
        return _clean(vault + reserve + active_equity)

    def current_profit() -> float | None:
        wealth = current_wealth()
        if wealth is None:
            return None
        return _clean(wealth - capital)

    def emit(
        event_type: str,
        *,
        timestamp: datetime | None = None,
        trade: CandidateTrade | None = None,
        tranche_id: int | None = None,
        terminal_status: str | None = None,
        reason: str | None = None,
        amount: float | None = None,
        realized: bool = False,
        locked: bool = False,
    ) -> None:
        events.append(
            AccountEvent(
                timestamp=timestamp,
                event_type=event_type,
                vault=_clean(vault),
                reserve=_clean(reserve),
                active_equity=_clean(active_equity),
                wealth=current_wealth(),
                profit=current_profit(),
                candidate_id=trade.candidate_id if trade is not None else None,
                symbol=trade.symbol if trade is not None else None,
                tranche_id=tranche_id,
                terminal_status=terminal_status,
                reason=reason,
                amount=None if amount is None else _clean(amount),
                realized=realized,
                locked=locked,
                active_trade_exit=last_exit,
            )
        )

    cashflows_initial = cashflows[0]
    emit(
        "initial_deposit",
        amount=cashflows_initial.amount,
        reason=cashflows_initial.reason,
    )

    def skip(
        trade: CandidateTrade,
        reason: str,
        *,
        timestamp: datetime | None = None,
    ) -> None:
        nonlocal skipped_no_capital, skipped_blocked
        item = SkippedTrade(trade=trade, reason=reason)
        skipped.append(item)
        if reason == "overlap":
            skipped_overlap_trades.append(item)
        elif reason in {
            "missing_entry_signal",
            "invalid_entry_signal",
            "incomplete_entry",
            "missing_exit_path",
            "invalid_exit_path",
            "missing_net_return",
            "invalid_net_return",
        }:
            skipped_incomplete_trades.append(item)
        elif reason == "tranche_budget_exhausted":
            skipped_no_capital += 1
        elif reason == "blocked_by_unresolved_path":
            skipped_blocked += 1

    def allocate(
        trade: CandidateTrade,
        timestamp: datetime,
    ) -> bool:
        nonlocal active_tranche_id, active_equity, reserve, allocated_count
        if active_tranche_id is not None:
            return True
        if allocated_count >= tranche_count or reserve + _EPSILON < seed:
            return False
        allocated_count += 1
        active_tranche_id = allocated_count
        reserve = _clean(reserve - seed)
        active_equity = _clean(seed)
        cashflows.append(
            CashFlow(
                timestamp=timestamp,
                flow_type="tranche_allocation",
                amount=seed,
                source="reserve",
                destination="active_equity",
                candidate_id=trade.candidate_id,
                tranche_id=active_tranche_id,
                reason="fixed_isolated_seed",
            )
        )
        emit(
            "tranche_allocated",
            timestamp=timestamp,
            trade=trade,
            tranche_id=active_tranche_id,
            amount=seed,
        )
        return True

    def maybe_burn(trade: CandidateTrade, timestamp: datetime) -> None:
        nonlocal active_tranche_id, active_equity
        if active_tranche_id is None or active_equity > _EPSILON:
            return
        burned_id = active_tranche_id
        active_tranche_id = None
        active_equity = 0.0
        tranche_burns.append(burned_id)
        emit(
            "tranche_burned",
            timestamp=timestamp,
            trade=trade,
            tranche_id=burned_id,
            reason="margin_zero",
        )

    for _, trade in ordered:
        if unresolved_after_entry:
            skip(
                trade,
                "blocked_by_unresolved_path",
                timestamp=_safe_time(trade.signal_time),
            )
            continue

        signal_time = _safe_time(trade.signal_time)
        exit_time = _safe_time(trade.exit_time)
        status = _normalise_status(trade.terminal_status)

        if signal_time is None:
            skip(trade, "missing_entry_signal")
            continue
        if status in _ENTRY_REJECT_STATUSES:
            skip(trade, "incomplete_entry", timestamp=signal_time)
            continue

        net_return = _safe_return(trade.net_return_on_margin)
        full_margin_loss_proxy = _is_full_margin_loss(
            trade.net_return_on_margin
        )
        unresolved_path = status in _UNRESOLVED_STATUSES or (
            status not in _ENTRY_REJECT_STATUSES
            and (
                net_return is None
                or exit_time is None
                or exit_time < signal_time
            )
        )

        # An unresolved path is selected after its entry is known. A generic
        # missing return/exit is treated the same way; silently skipping it
        # would create favorable capital reuse.
        if not active_locked and unresolved_path:
            if last_exit is not None and signal_time < last_exit:
                skip(trade, "overlap", timestamp=signal_time)
                continue
            if not allocate(trade, signal_time):
                skip(trade, "tranche_budget_exhausted", timestamp=signal_time)
                continue
            executed_trades.append(trade)
            executed_records.append(
                ExecutedTrade(
                    trade=trade,
                    tranche_id=active_tranche_id or 0,
                    margin_before=_clean(active_equity),
                    net_return_on_margin=None,
                    pnl=None,
                    margin_after=_clean(active_equity),
                    withdrawn_profit=0.0,
                    terminal_status=status,
                    realized=False,
                    locked=True,
                )
            )
            unresolved_after_entry = True
            non_rankable = True
            active_locked = True
            capital_occupied_to_cutoff = _clean(active_equity)
            last_exit = exit_time or signal_time
            emit(
                "unresolved_after_entry",
                timestamp=last_exit,
                trade=trade,
                tranche_id=active_tranche_id,
                terminal_status=status,
                reason="future_path_unknown_after_selected_entry",
                amount=capital_occupied_to_cutoff,
                locked=True,
            )
            continue

        if active_locked:
            skip(
                trade,
                "active_mark_to_cutoff_locked",
                timestamp=signal_time,
            )
            continue
        if last_exit is not None and signal_time < last_exit:
            skip(trade, "overlap", timestamp=signal_time)
            continue

        if net_return is None:
            skip(trade, "missing_net_return", timestamp=signal_time)
            continue
        if exit_time is None:
            skip(trade, "missing_exit_path", timestamp=signal_time)
            continue
        if exit_time < signal_time:
            skip(trade, "invalid_exit_path", timestamp=signal_time)
            continue
        if not allocate(trade, signal_time):
            skip(trade, "tranche_budget_exhausted", timestamp=signal_time)
            continue

        tranche_id = active_tranche_id or 0
        margin_before = _clean(active_equity)
        pnl = _clean(margin_before * net_return)
        active_equity = _clean(max(0.0, margin_before + pnl))
        is_mark_to_cutoff = status in _MARK_TO_CUTOFF_STATUSES
        swept_profit = 0.0

        if not is_mark_to_cutoff and withdraw_profits and active_equity > seed:
            swept_profit = _clean(active_equity - seed)
            active_equity = _clean(seed)
            vault = _clean(vault + swept_profit)
            cashflows.append(
                CashFlow(
                    timestamp=exit_time,
                    flow_type="profit_withdrawal",
                    amount=swept_profit,
                    source="active_equity",
                    destination="vault",
                    candidate_id=trade.candidate_id,
                    tranche_id=tranche_id,
                    reason="realized_excess_above_tranche_seed",
                )
            )

        if is_mark_to_cutoff:
            active_locked = True
            locked_mark_to_cutoff = True
            capital_occupied_to_cutoff = _clean(active_equity)

        executed_trades.append(trade)
        executed_records.append(
            ExecutedTrade(
                trade=trade,
                tranche_id=tranche_id,
                margin_before=margin_before,
                net_return_on_margin=net_return,
                pnl=pnl,
                margin_after=_clean(active_equity),
                withdrawn_profit=swept_profit,
                terminal_status=status,
                realized=not is_mark_to_cutoff,
                locked=is_mark_to_cutoff,
            )
        )
        last_exit = exit_time
        emit(
            "mark_to_cutoff" if is_mark_to_cutoff else "trade_closed",
            timestamp=exit_time,
            trade=trade,
            tranche_id=tranche_id,
            terminal_status=status,
            reason=(
                "full_margin_loss_proxy" if full_margin_loss_proxy else None
            ),
            amount=pnl,
            realized=not is_mark_to_cutoff,
            locked=is_mark_to_cutoff,
        )
        if swept_profit > _EPSILON:
            emit(
                "profit_withdrawal",
                timestamp=exit_time,
                trade=trade,
                tranche_id=tranche_id,
                amount=swept_profit,
                realized=True,
            )

        if not is_mark_to_cutoff:
            wealth = current_wealth()
            if wealth is not None:
                drawdown = _clean(max(0.0, peak_closed_wealth - wealth))
                closed_drawdowns.append(drawdown)
                peak_closed_wealth = max(peak_closed_wealth, wealth)
        maybe_burn(trade, exit_time)

    final_wealth = current_wealth()
    final_profit = current_profit()
    operating_exhaustion = (
        not non_rankable
        and active_tranche_id is None
        and allocated_count >= tranche_count
        and reserve <= _EPSILON
    )
    wealth_ruin: bool | None
    if non_rankable or final_wealth is None:
        wealth_ruin = None
    else:
        wealth_ruin = final_wealth <= _EPSILON

    skipped_overlap = len(skipped_overlap_trades)
    skipped_incomplete = len(skipped_incomplete_trades)
    return AccountSimulationResult(
        initial_capital=capital,
        tranche_count=int(tranche_count),
        tranche_seed=_clean(seed),
        withdraw_profits=withdraw_profits,
        external_contributions=capital,
        vault=_clean(vault),
        reserve=_clean(reserve),
        active_equity=_clean(active_equity),
        final_wealth=final_wealth,
        final_profit=final_profit,
        opportunities=len(source),
        executed=len(executed_trades),
        skipped_overlap=skipped_overlap,
        skipped_incomplete=skipped_incomplete,
        skipped_no_capital=skipped_no_capital,
        skipped_blocked=skipped_blocked,
        executed_trades=tuple(executed_trades),
        executed_records=tuple(executed_records),
        skipped_trades=tuple(skipped),
        skipped_overlap_trades=tuple(skipped_overlap_trades),
        skipped_incomplete_trades=tuple(skipped_incomplete_trades),
        cashflows=tuple(cashflows),
        events=tuple(events),
        tranches_allocated=allocated_count,
        tranche_burns=tuple(tranche_burns),
        operating_exhaustion=operating_exhaustion,
        wealth_ruin=wealth_ruin,
        non_rankable=non_rankable,
        unresolved_after_entry=unresolved_after_entry,
        locked_mark_to_cutoff=locked_mark_to_cutoff,
        capital_occupied_to_cutoff=_clean(capital_occupied_to_cutoff),
        closed_event_drawdown=tuple(closed_drawdowns),
        max_closed_event_drawdown=_clean(max(closed_drawdowns, default=0.0)),
    )


__all__ = [
    "AccountEvent",
    "AccountSimulationResult",
    "CandidateTrade",
    "CashFlow",
    "ExecutedTrade",
    "SkippedTrade",
    "simulate_account",
]
