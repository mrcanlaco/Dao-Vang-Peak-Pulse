from datetime import datetime, timezone
from pathlib import Path

from dao_vang.experiments.forward_test import FrozenModelInfo
from dao_vang.scoring.frozen_inference import assess_snapshot_quality


def _info(tmp_path: Path) -> FrozenModelInfo:
    return FrozenModelInfo(
        model_id="test-model",
        freeze_time="2024-01-01T00:00:00+00:00",
        train_cutoff="2023-12-01T00:00:00+00:00",
        threshold=0.6,
        feature_cols=["feature_a", "feature_b"],
        config={},
        training_stats={},
        label_spec={"horizon_hours": 6},
        model_path=tmp_path / "model.joblib",
        metadata_path=tmp_path / "metadata.json",
    )


def test_quality_gate_rejects_stale_snapshot(tmp_path: Path) -> None:
    info = _info(tmp_path)
    quality = assess_snapshot_quality(
        {
            "feature_a": 1.0,
            "feature_b": 2.0,
            "feature_time": datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            "quality_status": "valid",
            "data_quality_score": 1.0,
        },
        info,
        now=datetime(2024, 1, 1, 0, 11, tzinfo=timezone.utc),
        max_feature_age_minutes=10,
    )
    assert quality.status == "invalid"
    assert "feature_stale" in quality.reason_codes


def test_quality_gate_rejects_missing_model_feature(tmp_path: Path) -> None:
    info = _info(tmp_path)
    quality = assess_snapshot_quality(
        {
            "feature_a": 1.0,
            "feature_time": datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            "quality_status": "valid",
        },
        info,
        now=datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc),
        max_feature_age_minutes=10,
    )
    assert quality.status == "invalid"
    assert quality.missing_features == ("feature_b",)
    assert "missing_required_features" in quality.reason_codes


def test_quality_gate_rejects_invalid_source_status(tmp_path: Path) -> None:
    info = _info(tmp_path)
    quality = assess_snapshot_quality(
        {
            "feature_a": 1.0,
            "feature_b": 2.0,
            "feature_time": datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc),
            "quality_status": "invalid",
            "data_quality_score": 1.0,
        },
        info,
        now=datetime(2024, 1, 1, 0, 1, tzinfo=timezone.utc),
        max_feature_age_minutes=10,
    )
    assert quality.status == "invalid"
    assert "quality_status_invalid" in quality.reason_codes
