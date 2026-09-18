from datetime import datetime, timedelta, timezone

import pytest

from dao_vang.scanner.tracking_evidence import market_observation, signal_outcome

NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)


def test_missing_quote_never_becomes_a_current_price():
    result = market_observation({}, None, now=NOW)
    assert result['current_price'] is None
    assert result['market_data_status'] == 'MISSING'


def test_cached_ticker_keeps_its_actual_age():
    result = market_observation(
        {'lastPrice': '100', 'closeTime': (NOW - timedelta(hours=2)).timestamp() * 1000},
        None, now=NOW,
    )
    assert result['market_data_status'] == 'STALE'
    assert result['market_data_age_minutes'] == 120


def test_freshest_observation_wins_over_stale_ticker():
    result = market_observation(
        {'lastPrice': '100', 'closeTime': (NOW - timedelta(hours=2)).timestamp() * 1000},
        {'close_price': 95, 'scan_time': NOW.isoformat()}, now=NOW,
    )
    assert result['current_price'] == 95
    assert result['market_data_source'] == 'scan'
    assert result['market_data_status'] == 'FRESH'


@pytest.mark.parametrize('price', ['NaN', 'Infinity', -1, 0, None])
def test_invalid_price_is_missing(price):
    assert market_observation({'lastPrice': price, 'closeTime': NOW.timestamp() * 1000}, None, now=NOW)['current_price'] is None


def test_future_timestamp_is_not_fresh():
    assert market_observation({'lastPrice': 100, 'closeTime': (NOW + timedelta(hours=1)).timestamp() * 1000}, None, now=NOW)['market_data_status'] == 'MISSING'


def test_expired_unresolved_is_distinct_from_failure():
    deadline = NOW - timedelta(hours=1)
    assert signal_outcome(None, deadline, now=NOW) == 'EXPIRED'
    assert signal_outcome(False, deadline, now=NOW) == 'MISS'
    assert signal_outcome(True, deadline, now=NOW) == 'HIT'
    assert signal_outcome(None, NOW + timedelta(hours=1), now=NOW) == 'ACTIVE'
