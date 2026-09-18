"""Dual V3 outcome labels.

The production-like label is the existing policy outcome: target reached before
the active stop is a win and a stop reached first is a loss.  Research also
needs a *separate* price-path diagnostic for a stopped position.  That
diagnostic freezes the weighted average at the stop, does not add any further
entries, and observes only until the original Entry-1 + 48 hour horizon.

The post-stop diagnostic must never be used to turn a stopped trade into a
winning trade.  It is intentionally represented as a nested result so callers
cannot accidentally pool it with the actual policy label.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from dao_vang.labels.engine_v3 import Bar, Funding, Outcome, evaluate
from dao_vang.labels.specs.distribution_short_v3 import SPEC

POST_STOP_VERSION = "post_stop_frozen_average_v1"


@dataclass(frozen=True)
class PostStopOutcome:
    """Price-path result after a real policy stop.

    ``target_after_stop`` is descriptive only.  It is deliberately not a
    second success label for the simulated trade.  ``status`` is one of
    ``not_applicable``, ``target_after_stop``, ``timeout_after_stop``,
    ``incomplete_after_stop`` or ``price_path_gap_after_stop``.
    """

    version: str
    contract: str
    contract_checksum: str
    status: str
    exclusion_reason: str | None
    stop_time: datetime | None
    frozen_average_entry: float | None
    frozen_target_price: float | None
    target_time: datetime | None
    target_price: float | None
    horizon_time: datetime
    observed_bars: int

    @property
    def target_after_stop(self) -> bool | None:
        if self.status == "target_after_stop":
            return True
        if self.status in {
            "timeout_after_stop",
            "not_applicable",
            "incomplete_after_stop",
            "price_path_gap_after_stop",
        }:
            return False if self.status == "timeout_after_stop" else None
        return None

    def to_dict(self) -> dict:
        result = asdict(self)
        result["target_after_stop"] = self.target_after_stop
        return result


@dataclass(frozen=True)
class DualOutcome:
    """Actual policy outcome plus an independent post-stop diagnostic."""

    actual: Outcome
    post_stop: PostStopOutcome

    @property
    def actual_win(self) -> bool | None:
        """Whether the simulated policy actually won (never post-stop)."""

        return None if self.actual.label is None else bool(self.actual.label)

    @property
    def paired_evidence_eligible(self) -> bool:
        """Whether actual and post-stop rows share a complete valid path."""

        return self.actual.eligible and self.post_stop.status in {
            "target_after_stop",
            "timeout_after_stop",
        }

    def to_dict(self) -> dict:
        result = self.actual.to_dict()
        result["actual_win"] = self.actual_win
        result["post_stop"] = self.post_stop.to_dict()
        result["paired_evidence_eligible"] = self.paired_evidence_eligible
        # Keep the outcome contract explicit for downstream APIs and reports.
        result["outcome_contract"] = {
            "actual": "target_before_stop",
            "post_stop": POST_STOP_VERSION,
            "post_stop_changes_actual_win": False,
        }
        return result


def _post_stop_path(
    *,
    signal_time: datetime,
    actual: Outcome,
    bars: list[Bar],
) -> PostStopOutcome:
    horizon = signal_time + timedelta(hours=SPEC.horizon_hours)
    if actual.status not in {"stop", "stop_ambiguous"}:
        return PostStopOutcome(
            version=POST_STOP_VERSION,
            contract=SPEC.version,
            contract_checksum=SPEC.checksum,
            status="not_applicable",
            exclusion_reason=None,
            stop_time=None,
            frozen_average_entry=None,
            frozen_target_price=None,
            target_time=None,
            target_price=None,
            horizon_time=horizon,
            observed_bars=0,
        )

    if not actual.fills or actual.exit_time is None:
        return PostStopOutcome(
            version=POST_STOP_VERSION,
            contract=SPEC.version,
            contract_checksum=SPEC.checksum,
            status="incomplete_after_stop",
            exclusion_reason="missing_stop_fill",
            stop_time=actual.exit_time,
            frozen_average_entry=None,
            frozen_target_price=None,
            target_time=None,
            target_price=None,
            horizon_time=horizon,
            observed_bars=0,
        )

    frozen_average = actual.fills[-1].average_entry
    frozen_target = actual.fills[-1].target_price

    # The stop candle has already been consumed by the actual evaluator.  Its
    # low may have happened before the stop, so using it would be look-ahead
    # and would turn an ambiguous intrabar candle into false post-stop alpha.
    # If the stop is reached on the horizon bar, no post-stop interval exists;
    # report a completed timeout rather than pretending the path is missing.
    if actual.exit_time >= horizon:
        return PostStopOutcome(
            version=POST_STOP_VERSION,
            contract=SPEC.version,
            contract_checksum=SPEC.checksum,
            status="timeout_after_stop",
            exclusion_reason=None,
            stop_time=actual.exit_time,
            frozen_average_entry=frozen_average,
            frozen_target_price=frozen_target,
            target_time=None,
            target_price=None,
            horizon_time=horizon,
            observed_bars=0,
        )

    after_stop = [
        bar for bar in bars if actual.exit_time < bar.close_time <= horizon
    ]
    previous = actual.exit_time
    observed = 0
    for bar in after_stop:
        bar.validate()
        expected = previous + timedelta(minutes=SPEC.bar_minutes)
        if bar.close_time != expected:
            return PostStopOutcome(
                version=POST_STOP_VERSION,
                contract=SPEC.version,
                contract_checksum=SPEC.checksum,
                status="price_path_gap_after_stop",
                exclusion_reason="price_path_gap_after_stop",
                stop_time=actual.exit_time,
                frozen_average_entry=frozen_average,
                frozen_target_price=frozen_target,
                target_time=None,
                target_price=None,
                horizon_time=horizon,
                observed_bars=observed,
            )
        observed += 1
        # Once stopped, no new stop/entry state exists.  A gap through the
        # target receives the target price, never an invented better fill.
        if bar.open <= frozen_target:
            return PostStopOutcome(
                version=POST_STOP_VERSION,
                contract=SPEC.version,
                contract_checksum=SPEC.checksum,
                status="target_after_stop",
                exclusion_reason=None,
                stop_time=actual.exit_time,
                frozen_average_entry=frozen_average,
                frozen_target_price=frozen_target,
                target_time=previous,
                target_price=frozen_target,
                horizon_time=horizon,
                observed_bars=observed,
            )
        if bar.low <= frozen_target:
            return PostStopOutcome(
                version=POST_STOP_VERSION,
                contract=SPEC.version,
                contract_checksum=SPEC.checksum,
                status="target_after_stop",
                exclusion_reason=None,
                stop_time=actual.exit_time,
                frozen_average_entry=frozen_average,
                frozen_target_price=frozen_target,
                target_time=bar.close_time,
                target_price=frozen_target,
                horizon_time=horizon,
                observed_bars=observed,
            )
        previous = bar.close_time
        if bar.close_time == horizon:
            return PostStopOutcome(
                version=POST_STOP_VERSION,
                contract=SPEC.version,
                contract_checksum=SPEC.checksum,
                status="timeout_after_stop",
                exclusion_reason=None,
                stop_time=actual.exit_time,
                frozen_average_entry=frozen_average,
                frozen_target_price=frozen_target,
                target_time=None,
                target_price=None,
                horizon_time=horizon,
                observed_bars=observed,
            )

    return PostStopOutcome(
        version=POST_STOP_VERSION,
        contract=SPEC.version,
        contract_checksum=SPEC.checksum,
        status="incomplete_after_stop",
        exclusion_reason="price_path_incomplete_after_stop",
        stop_time=actual.exit_time,
        frozen_average_entry=frozen_average,
        frozen_target_price=frozen_target,
        target_time=None,
        target_price=None,
        horizon_time=horizon,
        observed_bars=observed,
    )


def evaluate_dual(
    *,
    signal_time: datetime,
    signal_price: float,
    bars: list[Bar],
    funding: list[Funding],
    funding_coverage_through: datetime | None,
    entry1_only: bool = False,
) -> DualOutcome:
    """Evaluate actual V3 policy and the independent post-stop path.

    The dual contract is always the compact weighted-average policy.  The
    ``entry1_only`` argument is retained only for source compatibility and is
    rejected so an Entry-1 diagnostic cannot be mislabeled as a policy result.
    """

    if entry1_only:
        raise ValueError(
            "evaluate_dual is compact-only; call engine_v3.evaluate(entry1_only=True) "
            "for the separate Entry-1 diagnostic"
        )
    actual = evaluate(
        signal_time=signal_time,
        signal_price=signal_price,
        bars=bars,
        funding=funding,
        funding_coverage_through=funding_coverage_through,
        entry1_only=False,
    )
    post_stop = _post_stop_path(
        signal_time=signal_time,
        actual=actual,
        bars=bars,
    )
    return DualOutcome(actual=actual, post_stop=post_stop)


__all__ = [
    "POST_STOP_VERSION",
    "PostStopOutcome",
    "DualOutcome",
    "evaluate_dual",
]
