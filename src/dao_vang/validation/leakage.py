from datetime import timedelta
from typing import List

from dao_vang.domain.errors import PointInTimeViolation
from dao_vang.validation.splits import WalkForwardFold


def audit_split_overlap(folds: List[WalkForwardFold], min_embargo_hours: int = 24):
    """
    Audits that within each fold:
    - Train strictly precedes Validation.
    - Validation strictly precedes Test.
    - Embargo gap is respected between Train/Val and Val/Test.
    """
    embargo = timedelta(hours=min_embargo_hours)
    for fold in folds:
        # Check Train -> Val
        if fold.validation.start_time < fold.train.end_time + embargo:
            raise PointInTimeViolation(
                f"Fold {fold.fold_idx}: Train end {fold.train.end_time} and Val start "
                f"{fold.validation.start_time} violate {min_embargo_hours}h embargo."
            )
        # Check Val -> Test
        if fold.test.start_time < fold.validation.end_time + embargo:
            raise PointInTimeViolation(
                f"Fold {fold.fold_idx}: Val end {fold.validation.end_time} "
                f"and Test start {fold.test.start_time} violate "
                f"{min_embargo_hours}h embargo."
            )


def audit_forbidden_columns(schema_fields: List[str], forbidden_prefixes: List[str]):
    """
    Audits that no feature in the schema matches a forbidden prefix (e.g. 'label_').
    """
    for field in schema_fields:
        for prefix in forbidden_prefixes:
            if field.startswith(prefix):
                raise PointInTimeViolation(
                    f"Field '{field}' violates forbidden prefix '{prefix}'"
                )
