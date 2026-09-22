from datetime import datetime, timezone
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("value", [float("inf"), -float("inf"), "bad", "nan", "inf"])
def test_quality_gate_rejects_invalid_numeric_features(tmp_path, value):
    quality = assess_snapshot_quality(
        {"feature_a": value, "feature_b": 2.0}, _info(tmp_path),
        require_feature_time=False,
    )
    assert not quality.is_usable
    assert "invalid_required_features" in quality.reason_codes


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf"), -0.1, 1.1])
def test_quality_gate_rejects_invalid_quality_score(tmp_path, value):
    quality = assess_snapshot_quality(
        {"feature_a": 1.0, "feature_b": 2.0, "data_quality_score": value},
        _info(tmp_path), require_feature_time=False,
    )
    assert not quality.is_usable
    assert "quality_score_invalid" in quality.reason_codes


def test_invalid_input_never_reaches_model_or_emits_probability(tmp_path, monkeypatch):
    from unittest.mock import Mock

    from dao_vang.config.settings import ScoringConfig, ThresholdPolicy
    from dao_vang.scoring import frozen_inference
    from dao_vang.scoring.btc_context import BtcContext

    load = Mock()
    monkeypatch.setattr(frozen_inference, "load_verified_bundle", load)
    result = frozen_inference.score_snapshot(
        "TESTUSDT", {"feature_a": float("inf"), "feature_b": 2.0},
        BtcContext(0, 0, 0, "NEUTRAL", 50, "BTC neutral"), _info(tmp_path),
        ScoringConfig(), ThresholdPolicy(),
    )
    load.assert_not_called()
    assert result.risk_tier == "WAIT"
    assert not result.alertable
    assert result.model_probability is result.calibrated_probability is None
