"""Repository-level checks for the exact model selected by live config."""

import json
from pathlib import Path

import yaml

from dao_vang.experiments.forward_test import (
    load_frozen_model,
    load_frozen_model_estimator,
)
from dao_vang.scoring.frozen_inference import _verify_bundle_checksums

ROOT = Path(__file__).resolve().parents[2]


def test_live_config_selects_a_complete_checksum_verified_bundle():
    config = yaml.safe_load(
        (ROOT / "configs" / "live.yaml").read_text(encoding="utf-8")
    )
    scanner = config["scanner"]
    model_id = scanner["frozen_model_id"]
    artifact_dir = ROOT / scanner["artifact_dir"]

    info = load_frozen_model(model_id, artifact_dir)
    metadata = json.loads(info.metadata_path.read_text(encoding="utf-8"))

    assert info.model_id == model_id
    assert info.model_path.is_file()
    assert info.calibrator_path is not None
    assert info.calibrator_path.is_file()
    assert info.train_cutoff
    assert info.threshold_policy
    assert _verify_bundle_checksums(info, metadata) is None

    estimator = load_frozen_model_estimator(model_id, artifact_dir)
    assert callable(getattr(estimator, "predict_proba", None))
