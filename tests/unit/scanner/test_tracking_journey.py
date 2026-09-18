from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from dao_vang.scanner.tracking_market import checkpoint, funding_cashflow
from dao_vang.scanner.tracking_monitor import refresh_tracking
from dao_vang.scanner.tracking_watchlist import TrackingWatchlistStore

NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)


def quote(price=100, at=NOW):
    return {'current_price': price, 'last_market_update': at.isoformat(), 'market_data_status': 'FRESH'}


def candles(hours):
    start = int(NOW.timestamp() * 1000)
    return [[start + i * 300_000, '100', '110', '85', '90', 0, start + (i + 1) * 300_000 - 1] for i in range(hours * 12)]


@pytest.mark.parametrize('hours', [24, 48])
def test_checkpoint_requires_full_path_including_losing_movements(hours):
    entry = {'source_price': 100, 'source_price_time': (NOW - timedelta(milliseconds=1)).isoformat(), 'source_price_evidence': 'binance_closed_5m'}
    later = NOW + timedelta(hours=hours)
    result = checkpoint(entry, hours, candles(hours), later)
    assert result['status'] == 'READY'
    assert result['return_pct'] == pytest.approx(-10)
    assert result['max_drop_pct'] == pytest.approx(15)
    assert result['max_rise_pct'] == pytest.approx(10)
    assert checkpoint(entry, hours, candles(hours)[:-1], later)['status'] == 'MISSING'
    assert checkpoint(entry, hours, candles(hours), NOW)['status'] == 'PENDING'


def test_conflicting_candle_and_unverified_reference_are_not_evidence():
    entry = {'source_price': 100, 'source_price_time': (NOW - timedelta(milliseconds=1)).isoformat(), 'source_price_evidence': 'binance_closed_5m'}
    rows = candles(24)
    duplicate = list(rows[0])
    duplicate[4] = '99'
    assert checkpoint(entry, 24, rows + [duplicate], NOW + timedelta(days=1))['reason'] == 'conflicting_candles'
    entry['source_price_evidence'] = 'unverified_saved_observation'
    assert checkpoint(entry, 24, rows, NOW + timedelta(days=1))['status'] == 'MISSING'


@pytest.mark.parametrize('side,expected', [('LONG', -2), ('SHORT', 2)])
def test_funding_uses_actual_notional_and_settlement_boundaries(side, expected):
    trade = {'opened_at': NOW.isoformat(), 'side': side, 'quantity': 10}
    rows = [{'fundingTime': int((NOW + timedelta(hours=h)).timestamp() * 1000), 'fundingRate': '.001', 'markPrice': '200'} for h in (0, 8, 16)]
    result = funding_cashflow(trade, rows + [rows[1]], NOW + timedelta(hours=16))
    assert result['cashflow'] == expected  # entry and exit settlements excluded; duplicates not paid twice
    assert result['settlements'] == 1
    rows[1]['markPrice'] = 'NaN'
    assert funding_cashflow(trade, rows, NOW + timedelta(hours=16))['status'] == 'MISSING'


@pytest.mark.parametrize('side,exit_price', [('LONG', 110), ('SHORT', 90)])
def test_paper_round_trip_locks_costs_and_never_rewrites_closed_trade(tmp_path, side, exit_price):
    store = TrackingWatchlistStore(tmp_path / 'tracking.json')
    entry, _ = store.add({'symbol': 'BTC'})
    first = store.paper(entry['id'], action='open', quote=quote(), now=NOW, side=side, notional=1000, fee_bps=10, slippage_bps=0)
    assert first['paper_trade']['quantity'] == 10
    # An accidental retry cannot change size or side.
    assert store.paper(entry['id'], action='open', quote={}, now=NOW, notional=3000)['paper_trade'] == first['paper_trade']
    later = NOW + timedelta(hours=1)
    closed = store.paper(entry['id'], action='close', quote=quote(exit_price, later), now=later, funding={'status': 'VERIFIED', 'cashflow': -1})
    trade = closed['paper_trade']
    assert trade['gross_pnl'] == 100
    assert trade['fees'] == pytest.approx(1 + exit_price * .01)
    assert trade['net_pnl'] == pytest.approx(100 - trade['fees'] - 1)
    assert store.paper(entry['id'], action='close', quote=quote(500), now=later)['paper_trade'] == trade


def test_paper_fails_on_stale_price_and_withholds_net_until_funding_verified(tmp_path):
    store = TrackingWatchlistStore(tmp_path / 'tracking.json')
    entry, _ = store.add({'symbol': 'ETH'})
    with pytest.raises(ValueError, match='two minutes'):
        store.paper(entry['id'], action='open', quote=quote(), now=NOW + timedelta(minutes=3))
    store.paper(entry['id'], action='open', quote=quote(), now=NOW, slippage_bps=10)
    with pytest.raises(ValueError, match='Close the paper'):
        store.remove(entry['id'])
    later = NOW + timedelta(hours=1)
    closed = store.paper(entry['id'], action='close', quote=quote(100, later), now=later)
    assert closed['paper_trade']['gross_pnl'] < 0  # adverse slippage on both sides
    assert closed['paper_trade']['net_pnl'] is None
    reconciled = store.reconcile_funding(entry['id'], {'status': 'VERIFIED', 'cashflow': 0}, now=later)
    assert reconciled['paper_trade']['net_pnl'] < 0
    assert store.reconcile_funding(entry['id'], {'status': 'VERIFIED', 'cashflow': 9999}, now=later)['paper_trade']['net_pnl'] == reconciled['paper_trade']['net_pnl']


def test_notifications_are_deduplicated_mutable_read_state_and_muted(tmp_path):
    store = TrackingWatchlistStore(tmp_path / 'tracking.json')
    entry, _ = store.add({'symbol': 'BTC'})
    store.monitor(entry['id'], quote(), {}, now=NOW)
    store.monitor(entry['id'], quote(106), {'24': {'status': 'READY', 'return_pct': 6}}, now=NOW + timedelta(minutes=1))
    first = store.get(entry['id'])
    assert len(first['notifications']) == 2
    store.monitor(entry['id'], quote(120), {'24': {'status': 'MISSING'}}, now=NOW + timedelta(minutes=2))
    assert len(store.get(entry['id'])['notifications']) == 2
    assert store.get(entry['id'])['checkpoints']['24']['status'] == 'READY'
    store.update(entry['id'], {'read_notifications': True, 'notifications_enabled': False, 'feedback': 'NOISY'})
    store.monitor(entry['id'], quote(130), {}, now=NOW + timedelta(hours=3))
    assert len(store.get(entry['id'])['notifications']) == 2
    assert all(n['read'] for n in store.get(entry['id'])['notifications'])


def test_monitor_refreshes_offline_followups_without_a_page_request(tmp_path):
    store = TrackingWatchlistStore(tmp_path / 'tracking.json')
    entry, _ = store.add({'symbol': 'BTC'})
    with patch('dao_vang.scanner.tracking_monitor.fetch_all_tickers', return_value=[{'symbol': 'BTCUSDT', 'lastPrice': '100', 'closeTime': NOW.timestamp() * 1000}]), patch('dao_vang.scanner.tracking_monitor.fetch_checkpoint', return_value={'status': 'READY', 'return_pct': -5}) as fetch:
        assert refresh_tracking(store, now=NOW) == 1
        assert fetch.call_count == 2
        assert store.get(entry['id'])['checkpoints']['48']['return_pct'] == -5
        assert refresh_tracking(store, now=NOW + timedelta(seconds=10)) == 0


def test_corrupt_journal_is_preserved_instead_of_silently_replaced(tmp_path):
    path = tmp_path / 'tracking.json'
    path.write_text('broken', encoding='utf-8')
    with pytest.raises(ValueError, match='preserved'):
        TrackingWatchlistStore(path).add({'symbol': 'BTC'})
    assert path.read_text() == 'broken'
