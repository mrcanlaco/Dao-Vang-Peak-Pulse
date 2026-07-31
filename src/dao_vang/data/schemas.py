from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _ms_to_datetime(v: Any) -> datetime:
    """Convert integer milliseconds to UTC datetime."""
    if isinstance(v, int):
        return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc)
    if isinstance(v, str) and v.isdigit():
        return datetime.fromtimestamp(int(v) / 1000.0, tz=timezone.utc)
    if isinstance(v, datetime):
        return v
    raise ValueError(f"Cannot parse datetime from {v}")


class KlineData(BaseModel):
    open_time: datetime = Field(alias="open_time")
    open_price: float = Field(alias="open")
    high_price: float = Field(alias="high")
    low_price: float = Field(alias="low")
    close_price: float = Field(alias="close")
    volume: float = Field(alias="volume")
    close_time: datetime = Field(alias="close_time")
    quote_volume: float = Field(alias="quote_volume")
    trades: int = Field(alias="trades")
    taker_buy_volume: float = Field(alias="taker_buy_volume")
    taker_buy_quote_volume: float = Field(alias="taker_buy_quote_volume")

    @classmethod
    def from_raw_list(cls, raw: list[Any]) -> "KlineData":
        """Parse from Binance raw list format."""
        return cls(
            open_time=_ms_to_datetime(raw[0]),
            open=float(raw[1]),
            high=float(raw[2]),
            low=float(raw[3]),
            close=float(raw[4]),
            volume=float(raw[5]),
            close_time=_ms_to_datetime(raw[6]),
            quote_volume=float(raw[7]),
            trades=int(raw[8]),
            taker_buy_volume=float(raw[9]),
            taker_buy_quote_volume=float(raw[10]),
        )


class FundingRateData(BaseModel):
    symbol: str
    funding_time: datetime = Field(alias="fundingTime")
    funding_rate: float = Field(alias="fundingRate")
    mark_price: float | None = Field(default=None, alias="markPrice")

    @field_validator("funding_time", mode="before")
    def parse_funding_time(cls, v: Any) -> Any:
        return _ms_to_datetime(v)


class OpenInterestData(BaseModel):
    symbol: str
    sum_open_interest: float = Field(alias="sumOpenInterest")
    sum_open_interest_value: float = Field(alias="sumOpenInterestValue")
    timestamp: datetime

    @field_validator("timestamp", mode="before")
    def parse_timestamp(cls, v: Any) -> Any:
        return _ms_to_datetime(v)


class TakerRatioData(BaseModel):
    buy_sell_ratio: float = Field(alias="buySellRatio")
    buy_vol: float = Field(alias="buyVol")
    sell_vol: float = Field(alias="sellVol")
    timestamp: datetime

    @field_validator("timestamp", mode="before")
    def parse_timestamp(cls, v: Any) -> Any:
        return _ms_to_datetime(v)


class AccountRatioData(BaseModel):
    symbol: str
    long_short_ratio: float = Field(alias="longShortRatio")
    long_account: float = Field(alias="longAccount")
    short_account: float = Field(alias="shortAccount")
    timestamp: datetime

    @field_validator("timestamp", mode="before")
    def parse_timestamp(cls, v: Any) -> Any:
        return _ms_to_datetime(v)
