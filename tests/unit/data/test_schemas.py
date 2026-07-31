from datetime import datetime, timezone

from dao_vang.data.schemas import (
    AccountRatioData,
    FundingRateData,
    KlineData,
    OpenInterestData,
    TakerRatioData,
)


def test_kline_data_from_raw() -> None:
    raw = [
        1600000000000,
        "10000.0",
        "10100.0",
        "9900.0",
        "10050.0",
        "10.5",
        1600000299999,
        "100500.0",
        150,
        "5.2",
        "50250.0",
        "0",
    ]
    kline = KlineData.from_raw_list(raw)
    assert kline.open_time == datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)
    assert kline.close_time == datetime(
        2020, 9, 13, 12, 31, 39, 999000, tzinfo=timezone.utc
    )
    assert kline.open_price == 10000.0
    assert kline.high_price == 10100.0
    assert kline.low_price == 9900.0
    assert kline.close_price == 10050.0
    assert kline.volume == 10.5
    assert kline.quote_volume == 100500.0
    assert kline.trades == 150
    assert kline.taker_buy_volume == 5.2
    assert kline.taker_buy_quote_volume == 50250.0


def test_funding_rate_data() -> None:
    raw = {
        "symbol": "BTCUSDT",
        "fundingTime": 1600000000000,
        "fundingRate": "0.0001",
        "markPrice": "10000.0",
    }
    funding = FundingRateData.model_validate(raw)
    assert funding.symbol == "BTCUSDT"
    assert funding.funding_time == datetime(
        2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc
    )
    assert funding.funding_rate == 0.0001
    assert funding.mark_price == 10000.0


def test_open_interest_data() -> None:
    raw = {
        "symbol": "BTCUSDT",
        "sumOpenInterest": "1000.5",
        "sumOpenInterestValue": "10005000.0",
        "timestamp": 1600000000000,
    }
    oi = OpenInterestData.model_validate(raw)
    assert oi.symbol == "BTCUSDT"
    assert oi.sum_open_interest == 1000.5
    assert oi.sum_open_interest_value == 10005000.0
    assert oi.timestamp == datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)


def test_taker_ratio_data() -> None:
    raw = {
        "buySellRatio": "1.2",
        "buyVol": "120.5",
        "sellVol": "100.4",
        "timestamp": "1600000000000",
    }
    taker = TakerRatioData.model_validate(raw)
    assert taker.buy_sell_ratio == 1.2
    assert taker.buy_vol == 120.5
    assert taker.sell_vol == 100.4
    assert taker.timestamp == datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)


def test_account_ratio_data() -> None:
    raw = {
        "symbol": "BTCUSDT",
        "longShortRatio": "1.5",
        "longAccount": "0.6",
        "shortAccount": "0.4",
        "timestamp": 1600000000000,
    }
    ratio = AccountRatioData.model_validate(raw)
    assert ratio.symbol == "BTCUSDT"
    assert ratio.long_short_ratio == 1.5
    assert ratio.long_account == 0.6
    assert ratio.short_account == 0.4
    assert ratio.timestamp == datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)
