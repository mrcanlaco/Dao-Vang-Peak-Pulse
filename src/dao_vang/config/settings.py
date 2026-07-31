import typing
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, Field, HttpUrl, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict


class BinanceConfig(BaseModel):
    base_url: HttpUrl = HttpUrl("https://fapi.binance.com")
    symbol: Annotated[str, StringConstraints(pattern=r"^[A-Z0-9]+$")] = "BTCUSDT"
    interval: Literal["5m"] = "5m"
    availability_lag_ms: int = Field(default=1000, ge=0)


class CollectionPolicy(BaseModel):
    timeout_seconds: int = Field(default=15, gt=0)
    max_retries: int = Field(default=5, ge=0)
    max_concurrency: int = Field(default=2, gt=0)


class PathsConfig(BaseModel):
    data_dir: Path = Path("data")
    raw_dir: Path = Path("data/raw")
    normalized_dir: Path = Path("data/normalized")


class AppSettings(BaseSettings):
    binance: BinanceConfig = BinanceConfig()
    collection: CollectionPolicy = CollectionPolicy()
    paths: PathsConfig = PathsConfig()

    api_key: str | None = Field(default=None, exclude=True)
    api_secret: str | None = Field(default=None, exclude=True)

    model_config = SettingsConfigDict(
        env_prefix="DAO_VANG_",
        env_nested_delimiter="__",
        env_file=".env",
    )

    @classmethod
    def from_yaml(cls, yaml_path: Path) -> "AppSettings":
        if not yaml_path.exists():
            return cls()

        with open(yaml_path, "r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f)
            config_dict = typing.cast(dict[str, typing.Any], loaded) if loaded else {}

        return cls(**config_dict)
