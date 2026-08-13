from datetime import datetime, timedelta
from typing import List

from pydantic import BaseModel


class SplitBounds(BaseModel):
    """Represents the start and end times for a data split."""

    start_time: datetime
    end_time: datetime


class WalkForwardFold(BaseModel):
    """Represents a single fold in a walk-forward validation setup."""

    fold_idx: int
    train: SplitBounds
    validation: SplitBounds
    calibration: SplitBounds | None = None
    test: SplitBounds
    # Populated only by the strict planner.  The holdout is never returned as
    # a training/validation/test interval and must be evaluated once at the
    # very end of research decisions.
    final_holdout: SplitBounds | None = None


class WalkForwardPlan(BaseModel):
    """A strict fold plan plus a permanently untouched final holdout."""

    folds: List[WalkForwardFold]
    final_holdout: SplitBounds | None = None
    embargo_hours: int = 24
    split_version: str = "walk_forward_v1"


def generate_walk_forward_splits(
    dataset_start: datetime,
    dataset_end: datetime,
    train_days: int = 90,
    val_days: int = 30,
    cal_days: int = 0,
    test_days: int = 30,
    step_days: int = 30,
    embargo_hours: int = 24,
    final_holdout_days: int = 0,
) -> List[WalkForwardFold]:
    """
    Generates chronological walk-forward folds without shuffling.
    Applies strict embargo gaps between splits to prevent leakage.
    """
    if train_days <= 0 or val_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("window and step days must be positive")
    if cal_days < 0 or final_holdout_days < 0 or embargo_hours < 0:
        raise ValueError("calibration, holdout and embargo values cannot be negative")
    if dataset_end <= dataset_start:
        raise ValueError("dataset_end must be after dataset_start")
    folds: List[WalkForwardFold] = []

    holdout: SplitBounds | None = None
    effective_end = dataset_end
    if final_holdout_days:
        holdout_start = dataset_end - timedelta(days=final_holdout_days)
        if holdout_start <= dataset_start:
            raise ValueError("final holdout leaves no room for a training fold")
        holdout = SplitBounds(start_time=holdout_start, end_time=dataset_end)
        effective_end = holdout_start - timedelta(hours=embargo_hours)

    current_train_start = dataset_start
    fold_idx = 0

    embargo_delta = timedelta(hours=embargo_hours)

    while True:
        train_end = current_train_start + timedelta(days=train_days)

        val_start = train_end + embargo_delta
        val_end = val_start + timedelta(days=val_days)

        if cal_days > 0:
            cal_start = val_end + embargo_delta
            cal_end = cal_start + timedelta(days=cal_days)
            test_start = cal_end + embargo_delta
        else:
            cal_start = None
            cal_end = None
            test_start = val_end + embargo_delta

        test_end = test_start + timedelta(days=test_days)

        if test_end > effective_end:
            break

        folds.append(
            WalkForwardFold(
                fold_idx=fold_idx,
                train=SplitBounds(start_time=current_train_start, end_time=train_end),
                validation=SplitBounds(start_time=val_start, end_time=val_end),
                calibration=SplitBounds(start_time=cal_start, end_time=cal_end)
                if cal_days > 0
                else None,
                test=SplitBounds(start_time=test_start, end_time=test_end),
                final_holdout=holdout,
            )
        )

        current_train_start += timedelta(days=step_days)
        fold_idx += 1

    return folds


def generate_strict_walk_forward_plan(
    dataset_start: datetime,
    dataset_end: datetime,
    *,
    train_days: int = 90,
    val_days: int = 30,
    cal_days: int = 0,
    test_days: int = 30,
    step_days: int = 30,
    embargo_hours: int = 24,
    final_holdout_days: int = 30,
    split_version: str = "walk_forward_strict_v1",
) -> WalkForwardPlan:
    """Create a chronological plan with an untouched final holdout.

    The returned plan is explicit about the holdout so a release command can
    reject predictions generated from it before model/threshold decisions are
    frozen.  ``generate_walk_forward_splits`` remains available for callers
    that only need ordinary folds.
    """

    folds = generate_walk_forward_splits(
        dataset_start,
        dataset_end,
        train_days=train_days,
        val_days=val_days,
        cal_days=cal_days,
        test_days=test_days,
        step_days=step_days,
        embargo_hours=embargo_hours,
        final_holdout_days=final_holdout_days,
    )
    holdout = (
        SplitBounds(
            start_time=dataset_end - timedelta(days=final_holdout_days),
            end_time=dataset_end,
        )
        if final_holdout_days
        else None
    )
    if not folds:
        raise ValueError("dataset does not contain a complete strict walk-forward fold")
    return WalkForwardPlan(
        folds=folds,
        final_holdout=holdout,
        embargo_hours=embargo_hours,
        split_version=split_version,
    )


def audit_walk_forward_plan(plan: WalkForwardPlan) -> None:
    """Fail closed on overlap, chronology or holdout contamination."""

    embargo = timedelta(hours=plan.embargo_hours)
    if not plan.folds:
        raise ValueError("walk-forward plan must contain at least one fold")
    previous_test_end: datetime | None = None
    for fold in plan.folds:
        if fold.train.end_time + embargo > fold.validation.start_time:
            raise ValueError(f"fold {fold.fold_idx} violates train/validation embargo")
        previous_end = fold.validation.end_time
        if fold.calibration is not None:
            if previous_end + embargo > fold.calibration.start_time:
                raise ValueError(
                    f"fold {fold.fold_idx} violates validation/calibration embargo"
                )
            previous_end = fold.calibration.end_time
        if previous_end + embargo > fold.test.start_time:
            raise ValueError(f"fold {fold.fold_idx} violates test embargo")
        if previous_test_end is not None and fold.test.start_time < previous_test_end:
            raise ValueError("test windows overlap across folds")
        previous_test_end = fold.test.end_time
        if (
            plan.final_holdout is not None
            and fold.test.end_time > plan.final_holdout.start_time - embargo
        ):
            raise ValueError("test window overlaps the final holdout")
