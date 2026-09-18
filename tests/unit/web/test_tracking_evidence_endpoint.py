import json
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import httpx

from dao_vang.scanner.tracking_watchlist import TrackingWatchlistStore
from dao_vang.web.api_server import APIHandler, ReusableThreadingHTTPServer


def test_saved_snapshot_is_preserved_and_missing_prices_are_explicit():
    now = datetime.now(timezone.utc)
    signal_time = (now - timedelta(days=2)).isoformat()
    entry = {
        'id': 'saved', 'symbol': 'BTCUSDT', 'source_signal_time': signal_time,
        'source_price': 100, 'source_probability': .3, 'source_target_price': 92,
        'source_invalidation_time': (now - timedelta(days=1)).isoformat(),
        'status': 'IN_POSITION', 'position_side': 'SHORT', 'entry_price': 100,
        'notional': 1000,
    }
    alert = {'symbol': 'BTCUSDT', 'signal_time': signal_time, 'close_price': 120,
             'probability': .9, 'hit': False}
    handler = MagicMock(spec=APIHandler)
    handler.wfile = MagicMock()
    with patch('dao_vang.web.api_server._tracking_store') as store, \
         patch('dao_vang.web.api_server._alert_store') as alerts, \
         patch('dao_vang.web.api_server._scan_store') as scans, \
         patch('dao_vang.web.api_server.fetch_all_tickers', return_value=[]), \
         patch('dao_vang.web.api_server._current_model_target_drawdown', side_effect=AssertionError('Must not reinterpret historical targets')):
        store.list.return_value = [entry]
        alerts.query.return_value = [alert]
        scans.latest_per_symbol.return_value = []
        APIHandler.get_tracking_watchlist(handler)
    item = json.loads(handler.wfile.write.call_args[0][0])[0]
    assert item['source_price'] == 100
    assert item['source_probability'] == .3
    assert item['source_target_price'] == 92
    assert item['source_invalidation_time'] == entry['source_invalidation_time']
    assert item['signal_status'] == 'MISS'
    assert item['market_data_status'] == 'MISSING'
    assert item['current_price'] is None
    assert item['position_pnl'] is None


def test_http_follow_paper_feedback_archive_roundtrip(tmp_path):
    store = TrackingWatchlistStore(tmp_path / 'tracking.json')
    now = datetime.now(timezone.utc)
    server = ReusableThreadingHTTPServer(('127.0.0.1', 0), APIHandler)
    with patch.object(APIHandler, '_check_auth', return_value=True), \
         patch('dao_vang.web.api_server._tracking_store', store), \
         patch('dao_vang.web.api_server._scan_store') as scans, \
         patch('dao_vang.web.api_server._alert_store') as alerts, \
         patch('dao_vang.web.api_server.reference_price', return_value={'source_price': 100, 'source_price_time': now.isoformat(), 'source_price_evidence': 'binance_closed_5m'}), \
         patch('dao_vang.web.api_server.fetch_all_tickers', return_value=[{'symbol': 'BTCUSDT', 'lastPrice': '100', 'closeTime': now.timestamp() * 1000}]), \
         patch('dao_vang.web.api_server.fetch_funding', return_value={'status': 'VERIFIED', 'cashflow': 0, 'settlements': 0}):
        scans.latest_per_symbol.return_value = []
        alerts.query.return_value = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{server.server_port}') as client:
                response = client.post('/api/tracking-watchlist', json={'symbol': 'BTC', 'source_price': 999})
                assert response.status_code == 201
                item = response.json()['item']
                assert item['source_price'] == 100
                endpoint = f"/api/tracking-watchlist/{item['id']}"
                assert client.post(endpoint + '/paper', json={'action': 'open', 'fee_bps': 5, 'slippage_bps': 5}).status_code == 200
                assert client.delete(endpoint).status_code == 400
                result = client.post(endpoint + '/paper', json={'action': 'close'})
                assert result.status_code == 200
                assert result.json()['item']['paper_trade']['net_pnl'] < 0  # unchanged price still incurs costs
                assert client.patch(endpoint, json={'feedback': 'USEFUL'}).status_code == 200
                assert client.delete(endpoint).status_code == 200
                history = client.get('/api/tracking-watchlist').json()
                assert len(history) == 1
                assert history[0]['archived_at']
                assert history[0]['paper_trade']['status'] == 'CLOSED'
                assert history[0]['feedback'] == 'USEFUL'
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()


def test_tracking_mutations_require_authentication():
    for path in ['/api/tracking-usage', '/api/tracking-watchlist', '/api/tracking-watchlist/id/paper']:
        handler = MagicMock(spec=APIHandler)
        handler.path = path
        handler._check_auth.return_value = False
        APIHandler.do_POST(handler)
        handler._send_unauthorized.assert_called_once()
        handler._read_json_body.assert_not_called()
