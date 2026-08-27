from __future__ import annotations

from dao_vang.scanner.anomalies import detect_market_anomalies


def _codes(features: dict[str, float]) -> set[str]:
    return {item.code for item in detect_market_anomalies(features).anomalies}


def test_volume_spike_and_bearish_reversal_are_reported() -> None:
    report = detect_market_anomalies(
        {
            "volume_zscore_24h": 4.2,
            "volume_ratio_1h": 3.0,
            "price_ret_4h": 0.12,
            "price_ret_1h": -0.025,
            "taker_buy_ratio": 0.43,
        }
    )

    assert {item.code for item in report.anomalies} >= {
        "volume_spike",
        "trend_reversal",
        "taker_sell_imbalance",
    }
    assert report.level in {"ELEVATED", "EXTREME"}
    assert report.score > 60.0
    reversal = next(item for item in report.anomalies if item.code == "trend_reversal")
    assert reversal.direction == "bearish"


def test_funding_extreme_and_sign_flip_are_reported() -> None:
    report = detect_market_anomalies(
        {
            "funding_rate_raw": 0.0008,
            "funding_zscore_30d": 3.1,
            "funding_change_8h": 0.0012,
            "funding_age_minutes": 20.0,
        }
    )

    assert _codes(
        {
            "funding_rate_raw": 0.0008,
            "funding_zscore_30d": 3.1,
            "funding_change_8h": 0.0012,
        }
    ) >= {"funding_extreme", "funding_flip"}
    assert report.anomalies[0].category == "funding"
    assert report.anomalies[0].direction == "bearish"


def test_stale_funding_does_not_create_funding_anomalies() -> None:
    report = detect_market_anomalies(
        {
            "funding_rate_raw": 0.001,
            "funding_zscore_30d": 4.0,
            "funding_change_8h": 0.001,
            "funding_age_minutes": 721.0,
        }
    )

    assert not any(item.category == "funding" for item in report.anomalies)


def test_fast_reversal_and_short_crowding_are_reported() -> None:
    features = {
        "price_ret_4h": 0.045,
        "price_ret_1h": 0.004,
        "price_ret_15m": -0.006,
        "global_ls_ratio": 0.58,
    }
    report = detect_market_anomalies(features)

    assert _codes(features) >= {"trend_reversal", "short_crowding"}
    assert report.level == "ELEVATED"


def test_missing_features_do_not_become_zero_based_anomalies() -> None:
    report = detect_market_anomalies({})

    assert report.level == "NORMAL"
    assert report.score == 0.0
    assert report.anomalies == ()


def test_disabled_config_is_explicit() -> None:
    report = detect_market_anomalies({"volume_zscore_24h": 10.0}, {"enabled": False})

    assert report.enabled is False
    assert report.to_dict()["anomalies"] == []
