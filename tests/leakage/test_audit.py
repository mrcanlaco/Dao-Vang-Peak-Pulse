from datetime import datetime, timedelta

import pytest

from dao_vang.domain.errors import PointInTimeViolation
from dao_vang.validation.leakage import audit_forbidden_columns, audit_split_overlap
from dao_vang.validation.splits import SplitBounds, WalkForwardFold


def test_audit_split_overlap_pass():
    base = datetime(2023, 1, 1)
    fold = WalkForwardFold(
        fold_idx=0,
        train=SplitBounds(start_time=base, end_time=base + timedelta(days=1)),
        validation=SplitBounds(
            start_time=base + timedelta(days=2), end_time=base + timedelta(days=3)
        ),
        test=SplitBounds(
            start_time=base + timedelta(days=4), end_time=base + timedelta(days=5)
        ),
    )
    # Embargo of 24h = 1 day, so this should pass exactly
    audit_split_overlap([fold], min_embargo_hours=24)


def test_audit_split_overlap_fail_train_val():
    base = datetime(2023, 1, 1)
    fold = WalkForwardFold(
        fold_idx=0,
        train=SplitBounds(start_time=base, end_time=base + timedelta(days=1)),
        validation=SplitBounds(
            start_time=base + timedelta(hours=12), end_time=base + timedelta(days=3)
        ),
        test=SplitBounds(
            start_time=base + timedelta(days=4), end_time=base + timedelta(days=5)
        ),
    )
    with pytest.raises(PointInTimeViolation, match="violate 24h embargo"):
        audit_split_overlap([fold], min_embargo_hours=24)


def test_audit_split_overlap_fail_val_test():
    base = datetime(2023, 1, 1)
    fold = WalkForwardFold(
        fold_idx=0,
        train=SplitBounds(start_time=base, end_time=base + timedelta(days=1)),
        validation=SplitBounds(
            start_time=base + timedelta(days=2), end_time=base + timedelta(days=3)
        ),
        test=SplitBounds(
            start_time=base + timedelta(days=3, hours=12),
            end_time=base + timedelta(days=5),
        ),
    )
    with pytest.raises(PointInTimeViolation, match="violate 24h embargo"):
        audit_split_overlap([fold], min_embargo_hours=24)


def test_audit_forbidden_columns():
    schema = ["price", "volume", "label_distribution"]
    with pytest.raises(
        PointInTimeViolation, match="violates forbidden prefix 'label_'"
    ):
        audit_forbidden_columns(schema, ["label_"])

    schema2 = ["price", "volume"]
    audit_forbidden_columns(schema2, ["label_"])  # Should pass
