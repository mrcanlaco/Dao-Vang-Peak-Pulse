import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from dao_vang.data.schemas import (
    AccountRatioData,
    FundingRateData,
    KlineData,
    NormalizedFunding,
    NormalizedGlobalRatio,
    NormalizedKline,
    NormalizedOpenInterest,
    NormalizedTakerVolume,
    NormalizedTopRatio,
    OpenInterestData,
    QualityStatus,
    TakerRatioData,
)


def normalize_kline(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedKline]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedKline] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    symbol = params.get("symbol", "BTCUSDT")
    interval = params.get("period", "5m")

    for item in payload:
        raw = KlineData.from_raw_list(item)
        event_time = raw.close_time
        available_time = event_time + timedelta(milliseconds=1000)

        norm = NormalizedKline(
            symbol=symbol,
            market="USD-M Futures",
            data_type="klines",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            open_time=raw.open_time,
            close_time=raw.close_time,
            open=Decimal(str(raw.open_price)),
            high=Decimal(str(raw.high_price)),
            low=Decimal(str(raw.low_price)),
            close=Decimal(str(raw.close_price)),
            volume_base=Decimal(str(raw.volume)),
            volume_quote=Decimal(str(raw.quote_volume)),
            trade_count=raw.trades,
            taker_buy_base=Decimal(str(raw.taker_buy_volume)),
            taker_buy_quote=Decimal(str(raw.taker_buy_quote_volume)),
        )
        results.append(norm)
    return results


def normalize_funding(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedFunding]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedFunding] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]

    for item in payload:
        raw = FundingRateData.model_validate(item)
        event_time = raw.funding_time
        available_time = max(event_time, collected_at)

        norm = NormalizedFunding(
            symbol=raw.symbol,
            market="USD-M Futures",
            data_type="funding",
            interval=None,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            funding_time=raw.funding_time,
            funding_rate=Decimal(str(raw.funding_rate)),
            mark_price=Decimal(str(raw.mark_price))
            if raw.mark_price is not None
            else None,
        )
        results.append(norm)
    return results


def normalize_open_interest(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedOpenInterest]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedOpenInterest] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    interval = params.get("period", "5m")

    # 5m = 300 seconds
    interval_delta = timedelta(minutes=5)

    for item in payload:
        raw = OpenInterestData.model_validate(item)
        period_start = raw.timestamp
        period_end = period_start + interval_delta
        event_time = period_start
        available_time = period_end + timedelta(milliseconds=1000)

        norm = NormalizedOpenInterest(
            symbol=raw.symbol,
            market="USD-M Futures",
            data_type="open_interest",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            period_start=period_start,
            period_end=period_end,
            open_interest_contracts=Decimal(str(raw.sum_open_interest)),
            open_interest_value=Decimal(str(raw.sum_open_interest_value)),
        )
        results.append(norm)
    return results


def normalize_taker_volume(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedTakerVolume]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedTakerVolume] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    symbol = params.get("symbol", "BTCUSDT")
    interval = params.get("period", "5m")

    interval_delta = timedelta(minutes=5)

    for item in payload:
        raw = TakerRatioData.model_validate(item)
        period_start = raw.timestamp
        period_end = period_start + interval_delta
        event_time = period_start
        available_time = period_end + timedelta(milliseconds=1000)

        norm = NormalizedTakerVolume(
            symbol=symbol,
            market="USD-M Futures",
            data_type="taker_volume",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            period_start=period_start,
            period_end=period_end,
            buy_volume=Decimal(str(raw.buy_vol)),
            sell_volume=Decimal(str(raw.sell_vol)),
            buy_sell_ratio=Decimal(str(raw.buy_sell_ratio)),
        )
        results.append(norm)
    return results


def normalize_global_ratio(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedGlobalRatio]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedGlobalRatio] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    interval = params.get("period", "5m")

    interval_delta = timedelta(minutes=5)

    for item in payload:
        raw = AccountRatioData.model_validate(item)
        period_start = raw.timestamp
        period_end = period_start + interval_delta
        event_time = period_start
        available_time = period_end + timedelta(milliseconds=1000)

        norm = NormalizedGlobalRatio(
            symbol=raw.symbol,
            market="USD-M Futures",
            data_type="global_ratio",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            period_start=period_start,
            period_end=period_end,
            long_account=Decimal(str(raw.long_account)),
            short_account=Decimal(str(raw.short_account)),
            long_short_ratio=Decimal(str(raw.long_short_ratio)),
        )
        results.append(norm)
    return results


def normalize_top_ratio(
    envelope: dict[str, Any], dataset_version: str = "1.0.0"
) -> list[NormalizedTopRatio]:
    payload = json.loads(envelope["payload_json"])
    results: list[NormalizedTopRatio] = []

    collected_at = datetime.fromisoformat(envelope["received_at"])
    source_version = envelope["source_version"]
    params = json.loads(envelope["request_params_json"])
    interval = params.get("period", "5m")

    interval_delta = timedelta(minutes=5)

    for item in payload:
        raw = AccountRatioData.model_validate(item)
        period_start = raw.timestamp
        period_end = period_start + interval_delta
        event_time = period_start
        available_time = period_end + timedelta(milliseconds=1000)

        norm = NormalizedTopRatio(
            symbol=raw.symbol,
            market="USD-M Futures",
            data_type="top_ratio",
            interval=interval,
            event_time=event_time,
            available_time=available_time,
            collected_at=collected_at,
            source_version=source_version,
            dataset_version=dataset_version,
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            period_start=period_start,
            period_end=period_end,
            long_account=Decimal(str(raw.long_account)),
            short_account=Decimal(str(raw.short_account)),
            long_short_ratio=Decimal(str(raw.long_short_ratio)),
        )
        results.append(norm)
    return results
