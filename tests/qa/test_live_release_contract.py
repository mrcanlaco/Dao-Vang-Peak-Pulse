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
LIVE_CONFIG_PATH = ROOT / "configs" / "live.yaml"
SENSITIVE_CONFIG_KEYS = {
    "access_password",
    "api_key",
    "api_secret",
    "bot_token",
    "chat_id",
    "credential",
    "password",
    "secret",
    "token",
}


def _load_live_config() -> dict:
    return yaml.safe_load(LIVE_CONFIG_PATH.read_text(encoding="utf-8"))


def _sensitive_paths(value: object, prefix: str = "") -> list[str]:
    if not isinstance(value, dict):
        return []

    found: list[str] = []
    for raw_key, child in value.items():
        key = str(raw_key)
        path = f"{prefix}.{key}" if prefix else key
        if key.lower() in SENSITIVE_CONFIG_KEYS:
            found.append(path)
        found.extend(_sensitive_paths(child, path))
    return found


def test_live_config_is_safe_to_version_and_disables_self_update():
    config = _load_live_config()

    assert _sensitive_paths(config) == []
    assert config["updater"]["enabled"] is False


def test_live_config_selects_a_complete_checksum_verified_bundle():
    config = _load_live_config()
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
