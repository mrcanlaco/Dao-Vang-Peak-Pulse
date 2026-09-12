import os
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dao_vang.config.settings import AppSettings, load_runtime_settings


def test_default_config() -> None:
    settings = AppSettings()
    assert str(settings.binance.base_url) == "https://fapi.binance.com/"
    assert settings.binance.symbol == "BTCUSDT"
    assert settings.binance.interval == "5m"
    assert settings.collection.timeout_seconds == 15
    assert settings.binance_agent_os.enabled is True
    assert settings.binance_agent_os.cache_minutes == 15


def test_invalid_interval() -> None:
    with pytest.raises(ValidationError, match="interval"):
        AppSettings(binance={"interval": "1m"})  # type: ignore


def test_invalid_lag() -> None:
    with pytest.raises(ValidationError, match="availability_lag_ms"):
        AppSettings(binance={"availability_lag_ms": -1})  # type: ignore


def test_env_override() -> None:
    os.environ["DAO_VANG_BINANCE__SYMBOL"] = "ETHUSDT"
    os.environ["DAO_VANG_COLLECTION__MAX_RETRIES"] = "10"

    try:
        settings = AppSettings()
        assert settings.binance.symbol == "ETHUSDT"
        assert settings.collection.max_retries == 10
    finally:
        del os.environ["DAO_VANG_BINANCE__SYMBOL"]
        del os.environ["DAO_VANG_COLLECTION__MAX_RETRIES"]


def test_yaml_load(tmp_path: Path) -> None:
    yaml_file = tmp_path / "config.yaml"
    data = {"binance": {"symbol": "BNBUSDT"}, "collection": {"timeout_seconds": 30}}
    with open(yaml_file, "w", encoding="utf-8") as f:
        yaml.dump(data, f)

    settings = AppSettings.from_yaml(yaml_file)
    assert settings.binance.symbol == "BNBUSDT"
    assert settings.collection.timeout_seconds == 30


def test_runtime_yaml_is_canonical_while_secrets_come_from_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    yaml_file = tmp_path / "live.yaml"
    yaml_file.write_text(
        yaml.safe_dump(
            {
                "scanner": {"frozen_model_id": "frozen_from_versioned_yaml"},
                "updater": {"enabled": False},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DAO_VANG_CONFIG_PATH", str(yaml_file))
    monkeypatch.setenv(
        "DAO_VANG_SCANNER__FROZEN_MODEL_ID",
        "stale_environment_model",
    )
    monkeypatch.setenv("DAO_VANG_WEB__ACCESS_PASSWORD", "runtime-only-secret")

    settings = load_runtime_settings()

    assert settings.scanner.frozen_model_id == "frozen_from_versioned_yaml"
    assert settings.web.access_password == "runtime-only-secret"
    assert settings.updater.enabled is False


def test_runtime_config_path_fails_closed_when_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_path = tmp_path / "missing-live.yaml"
    monkeypatch.setenv("DAO_VANG_CONFIG_PATH", str(missing_path))

    with pytest.raises(FileNotFoundError, match="DAO_VANG_CONFIG_PATH"):
        load_runtime_settings()


def test_candidate_comparison_defaults_are_safe() -> None:
    comparison = AppSettings().candidate_comparison
    assert comparison.enabled is False
    assert comparison.champion_version == "pump_filter_v1"
    assert comparison.challenger_version == "candidate_filter_v2"
    assert comparison.min_positive_events == 50
    assert comparison.min_evaluation_days == 14


def test_candidate_comparison_rejects_same_version_and_invalid_cap() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        AppSettings(
            candidate_comparison={
                "champion_version": "same",
                "challenger_version": "same",
            }
        )
    with pytest.raises(ValidationError, match="must not exceed"):
        AppSettings(
            candidate_comparison={"universe_size": 10, "max_candidates": 11}
        )
