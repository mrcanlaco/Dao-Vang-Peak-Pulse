from enum import Enum


class QualityStatus(str, Enum):
    """Status of data quality for a specific record or dataset."""

    VALID = "valid"
    WARNING = "warning"
    INVALID = "invalid"
    QUARANTINED = "quarantined"


class RunStatus(str, Enum):
    """Status of a collection run or experiment."""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
