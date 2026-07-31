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
    test: SplitBounds


def generate_walk_forward_splits(
    dataset_start: datetime,
    dataset_end: datetime,
    train_days: int = 90,
    val_days: int = 30,
    test_days: int = 30,
    step_days: int = 30,
    embargo_hours: int = 24,
) -> List[WalkForwardFold]:
    """
    Generates chronological walk-forward folds without shuffling.
    Applies strict embargo gaps between train/val and val/test to prevent leakage.

    Returns an empty list if the dataset is too small for even one full fold.

    Bounds are typically used as:
    `feature_time >= start_time AND feature_time < end_time`.
    """
    folds: List[WalkForwardFold] = []

    current_train_start = dataset_start
    fold_idx = 0

    embargo_delta = timedelta(hours=embargo_hours)

    while True:
        # Calculate boundaries for the current fold
        train_end = current_train_start + timedelta(days=train_days)

        val_start = train_end + embargo_delta
        val_end = val_start + timedelta(days=val_days)

        test_start = val_end + embargo_delta
        test_end = test_start + timedelta(days=test_days)

        # If the test_end goes beyond the dataset_end, we cannot form a full fold
        if test_end > dataset_end:
            break

        folds.append(
            WalkForwardFold(
                fold_idx=fold_idx,
                train=SplitBounds(start_time=current_train_start, end_time=train_end),
                validation=SplitBounds(start_time=val_start, end_time=val_end),
                test=SplitBounds(start_time=test_start, end_time=test_end),
            )
        )

        # Step forward for the next fold
        current_train_start += timedelta(days=step_days)
        fold_idx += 1

    return folds
