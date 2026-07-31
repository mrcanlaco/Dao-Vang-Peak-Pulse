import os
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from dao_vang.config.settings import AppSettings


def test_default_config() -> None:
    settings = AppSettings()
    assert str(settings.binance.base_url) == "https://fapi.binance.com/"
    assert settings.binance.symbol == "BTCUSDT"
    assert settings.binance.interval == "5m"
    assert settings.collection.timeout_seconds == 15


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
