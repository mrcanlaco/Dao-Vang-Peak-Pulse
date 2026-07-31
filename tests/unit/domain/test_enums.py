from dao_vang.domain import QualityStatus, RunStatus


def test_quality_status_values() -> None:
    assert QualityStatus.VALID == "valid"
    assert QualityStatus.WARNING == "warning"
    assert QualityStatus.INVALID == "invalid"
    assert QualityStatus.QUARANTINED == "quarantined"


def test_run_status_values() -> None:
    assert RunStatus.RUNNING == "running"
    assert RunStatus.SUCCEEDED == "succeeded"
    assert RunStatus.PARTIAL == "partial"
    assert RunStatus.FAILED == "failed"
