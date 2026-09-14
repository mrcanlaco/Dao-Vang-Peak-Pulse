"""Research-only short simulator, with strict coverage and auditable cash flows.

Bars describe (previous close time, close_time]. Entry1 is at the signal close;
the signal candle is never replayed. Fill/exit times are candle-resolution bounds,
not claimed tick timestamps. Stop-first refers to the stop active BEFORE adds.
Old target precedes adds; a rebased target on a fill candle requires its CLOSE
to cross the target. This convention avoids reusing a pre-fill low as a win.

Returns are fractions of a unit planned notional budget, not leveraged ROE.
Funding coverage is an explicit provider attestation [entry1, through]; an empty
funding list without that attestation is not zero funding.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from math import isfinite

from dao_vang.labels.specs.distribution_short_v3 import SPEC


def aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")


def positive(*values: float) -> None:
    if any(not isfinite(x) or x <= 0 for x in values):
        raise ValueError("prices must be finite and positive")


@dataclass(frozen=True)
class Bar:
    close_time: datetime
    open: float
    high: float
    low: float
    close: float

    def validate(self) -> None:
        aware(self.close_time)
        positive(self.open, self.high, self.low, self.close)
        if (
            not self.low
            <= min(self.open, self.close)
            <= max(self.open, self.close)
            <= self.high
        ):
            raise ValueError("invalid OHLC")


@dataclass(frozen=True)
class Funding:
    timestamp: datetime
    rate: float
    mark_price: float


@dataclass(frozen=True)
class Fill:
    leg: int
    timestamp: datetime
    price: float
    notional: float
    quantity: float
    average_entry: float
    target_price: float
    stop_price: float


@dataclass(frozen=True)
class FundingPayment:
    timestamp: datetime
    rate: float
    mark_price: float
    quantity: float
    cash_flow: float


@dataclass(frozen=True)
class Outcome:
    contract: str
    contract_checksum: str
    mode: str
    status: str
    exclusion_reason: str | None
    fills: tuple[Fill, ...]
    funding_payments: tuple[FundingPayment, ...]
    exit_time: datetime | None
    exit_price: float | None
    deployed_notional: float
    gross_return_planned: float | None
    costs_planned: float | None
    funding_planned: float | None
    net_return_planned: float | None
    net_return_deployed: float | None

    @property
    def eligible(self) -> bool:
        return self.exclusion_reason is None and self.status != "incomplete"

    @property
    def label(self) -> int | None:
        return int(self.status == "target") if self.eligible else None

    def to_dict(self) -> dict:
        result = asdict(self)
        result.update(eligible=self.eligible, label=self.label)
        return result


def evaluate(
    *,
    signal_time: datetime,
    signal_price: float,
    bars: list[Bar],
    funding: list[Funding],
    funding_coverage_through: datetime | None,
    entry1_only: bool = False,
) -> Outcome:
    """Evaluate the frozen contract; reject malformed data, exclude missing data.

    Funding timestamps must lie on bar boundaries. Settlements at entry time are
    excluded; later bar-open settlements precede exit/add orders. Horizon-end
    settlement is included for a timeout, before its closing mark.
    """
    aware(signal_time)
    positive(signal_price)
    step = timedelta(minutes=SPEC.bar_minutes)
    if signal_time.timestamp() % step.total_seconds():
        raise ValueError("signal_time must be aligned to a 5-minute close")
    horizon = signal_time + timedelta(hours=SPEC.horizon_hours)
    scale_end = signal_time + timedelta(hours=SPEC.scale_in_hours)
    if funding_coverage_through is not None:
        aware(funding_coverage_through)
        if funding_coverage_through < signal_time:
            raise ValueError("funding coverage precedes entry")
    previous = signal_time
    for bar in bars:
        bar.validate()
        if bar.close_time <= previous:
            raise ValueError("bars must be unique and strictly after signal")
        if (bar.close_time - signal_time) % step:
            raise ValueError("bars must lie on the 5-minute grid")
        previous = bar.close_time
    funding_by_time: dict[datetime, Funding] = {}
    for event in funding:
        aware(event.timestamp)
        positive(event.mark_price)
        if not isfinite(event.rate):
            raise ValueError("funding rate must be finite")
        step_seconds = step.total_seconds()
        rem = (event.timestamp - signal_time).total_seconds() % step_seconds
        jitter = min(rem, step_seconds - rem)
        if jitter > 0.05:
            raise ValueError("funding must be aligned to bar boundaries")
        nominal = event.timestamp - timedelta(
            seconds=rem if rem <= step_seconds / 2 else rem - step_seconds
        )
        if nominal in funding_by_time:
            raise ValueError("duplicate funding settlement")
        funding_by_time[nominal] = event

    fills: list[Fill] = []
    payments: list[FundingPayment] = []
    notional = quantity = 0.0

    def add(leg: int, timestamp: datetime, price: float, weight: float) -> None:
        nonlocal notional, quantity
        notional += weight
        qty = weight / price
        quantity += qty
        avg = notional / quantity
        fills.append(
            Fill(
                leg,
                timestamp,
                price,
                weight,
                qty,
                avg,
                avg * (1 - SPEC.target),
                avg * (1 + SPEC.stop),
            )
        )

    def settle(timestamp: datetime) -> None:
        event = funding_by_time.get(timestamp)
        if timestamp > signal_time and event is not None:
            payments.append(
                FundingPayment(
                    event.timestamp,
                    event.rate,
                    event.mark_price,
                    quantity,
                    quantity * event.mark_price * event.rate,
                )
            )

    add(1, signal_time, signal_price, 1.0 if entry1_only else SPEC.notional_weights[0])
    status, reason = "incomplete", "price_path_incomplete"
    exit_time = exit_price = None
    previous = signal_time
    for bar in bars:
        if bar.close_time > horizon:
            break
        if bar.close_time != previous + step:
            reason = "price_path_gap"
            break
        settle(previous)
        active = fills[-1]
        # Known open gaps precede unknown high/low order. Do not grant favorable
        # target price improvement or add-limit improvement in a gap.
        if bar.open >= active.stop_price:
            status, exit_price, exit_time = "stop", bar.open, previous
        elif bar.open <= active.target_price:
            status, exit_price, exit_time = "target", active.target_price, previous
        elif bar.high >= active.stop_price:
            status = "stop_ambiguous" if bar.low <= active.target_price else "stop"
            exit_price, exit_time = active.stop_price, bar.close_time
        elif bar.low <= active.target_price:
            status, exit_price, exit_time = (
                "target",
                active.target_price,
                bar.close_time,
            )
        else:
            if not entry1_only and bar.close_time <= scale_end:
                while len(fills) < len(SPEC.offsets):
                    index = len(fills)
                    limit = signal_price * (1 + SPEC.offsets[index])
                    if bar.high < limit:
                        break
                    add(index + 1, bar.close_time, limit, SPEC.notional_weights[index])
            # A close below the new target is known to occur after the high.
            if bar.close <= fills[-1].target_price:
                status, exit_price, exit_time = (
                    "target",
                    fills[-1].target_price,
                    bar.close_time,
                )
            elif bar.close_time == horizon:
                settle(horizon)
                status, exit_price, exit_time = "timeout", bar.close, horizon
        if exit_time is not None:
            reason = None
            break
        previous = bar.close_time

    gross = costs = net = funding_cash = None
    if exit_time is not None:
        assert exit_price is not None
        gross = notional - quantity * exit_price
        costs = SPEC.cost_per_side * (notional + quantity * exit_price)
        if funding_coverage_through is None or funding_coverage_through < exit_time:
            reason = "funding_coverage_incomplete"
        else:
            funding_cash = sum(payment.cash_flow for payment in payments)
            net = gross - costs + funding_cash
    return Outcome(
        SPEC.version,
        SPEC.checksum,
        "entry1_diagnostic" if entry1_only else "compact_policy",
        status,
        reason,
        tuple(fills),
        tuple(payments),
        exit_time,
        exit_price,
        notional,
        gross,
        costs,
        funding_cash,
        net,
        None if net is None else net / notional,
    )
