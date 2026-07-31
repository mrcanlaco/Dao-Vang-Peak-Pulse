from datetime import datetime, timezone
from decimal import Decimal

from dao_vang.data.quality import (
    assess_funding,
    assess_global_ratio,
    assess_kline,
    assess_open_interest,
    assess_taker_volume,
    assess_top_ratio,
)
from dao_vang.data.schemas import (
    NormalizedFunding,
    NormalizedGlobalRatio,
    NormalizedKline,
    NormalizedOpenInterest,
    NormalizedTakerVolume,
    NormalizedTopRatio,
    QualityStatus,
)


def get_base_kline() -> NormalizedKline:
    return NormalizedKline(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="klines",
        interval="5m",
        event_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        available_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        collected_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        open_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        close_time=datetime(2020, 1, 1, 0, 5, tzinfo=timezone.utc),
        open=Decimal("100"),
        high=Decimal("120"),
        low=Decimal("90"),
        close=Decimal("110"),
        volume_base=Decimal("10"),
        volume_quote=Decimal("1000"),
        trade_count=50,
        taker_buy_base=Decimal("5"),
        taker_buy_quote=Decimal("500"),
    )


def test_assess_kline_valid():
    k = get_base_kline()
    assessed = assess_kline(k)
    assert assessed.quality_status == QualityStatus.VALID
    assert len(assessed.quality_flags) == 0


def test_assess_kline_invalid_high():
    k = get_base_kline()
    k.high = Decimal("80")  # high < low, open, close
    assessed = assess_kline(k)
    assert assessed.quality_status == QualityStatus.INVALID
    assert "invalid_high_price" in assessed.quality_flags


def test_assess_kline_invalid_low():
    k = get_base_kline()
    k.low = Decimal("130")  # low > high, open, close
    assessed = assess_kline(k)
    assert assessed.quality_status == QualityStatus.INVALID
    assert "invalid_low_price" in assessed.quality_flags


def test_assess_kline_negative_volume():
    k = get_base_kline()
    k.volume_base = Decimal("-1")
    assessed = assess_kline(k)
    assert assessed.quality_status == QualityStatus.INVALID
    assert "negative_volume" in assessed.quality_flags


def test_assess_funding():
    f = NormalizedFunding(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="funding",
        interval=None,
        event_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        available_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        collected_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        funding_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        funding_rate=Decimal("0.2"),  # > 10%
        mark_price=Decimal("-100"),
    )
    assessed = assess_funding(f)
    assert assessed.quality_status == QualityStatus.INVALID
    assert "extreme_funding_rate" in assessed.quality_flags
    assert "invalid_mark_price" in assessed.quality_flags


def test_assess_open_interest():
    oi = NormalizedOpenInterest(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="open_interest",
        interval="5m",
        event_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        available_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        collected_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2020, 1, 1, 0, 5, tzinfo=timezone.utc),
        open_interest_contracts=Decimal("-1"),
        open_interest_value=Decimal("100"),
    )
    assessed = assess_open_interest(oi)
    assert assessed.quality_status == QualityStatus.INVALID
    assert "negative_open_interest" in assessed.quality_flags


def test_assess_taker_volume():
    tv = NormalizedTakerVolume(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="taker_volume",
        interval="5m",
        event_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        available_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        collected_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2020, 1, 1, 0, 5, tzinfo=timezone.utc),
        buy_volume=Decimal("100"),
        sell_volume=Decimal("50"),
        buy_sell_ratio=Decimal("0"),
    )
    assessed = assess_taker_volume(tv)
    assert assessed.quality_status == QualityStatus.INVALID
    assert "invalid_buy_sell_ratio" in assessed.quality_flags


def test_assess_global_ratio():
    gr = NormalizedGlobalRatio(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="global_ratio",
        interval="5m",
        event_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        available_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        collected_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2020, 1, 1, 0, 5, tzinfo=timezone.utc),
        long_account=Decimal("-0.1"),
        short_account=Decimal("0.5"),
        long_short_ratio=Decimal("1.5"),
    )
    assessed = assess_global_ratio(gr)
    assert assessed.quality_status == QualityStatus.INVALID
    assert "negative_long_account" in assessed.quality_flags


def test_assess_top_ratio():
    tr = NormalizedTopRatio(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="top_ratio",
        interval="5m",
        event_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        available_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
        collected_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        period_start=datetime(2020, 1, 1, tzinfo=timezone.utc),
        period_end=datetime(2020, 1, 1, 0, 5, tzinfo=timezone.utc),
        long_account=Decimal("0.6"),
        short_account=Decimal("0.4"),
        long_short_ratio=Decimal("-1.5"),
    )
    assessed = assess_top_ratio(tr)
    assert assessed.quality_status == QualityStatus.INVALID
    assert "invalid_long_short_ratio" in assessed.quality_flags
