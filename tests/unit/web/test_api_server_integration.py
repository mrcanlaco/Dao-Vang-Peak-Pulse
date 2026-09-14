import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import duckdb

from dao_vang.alerts.store import AlertStore
from dao_vang.scanner.scan_results_store import ScanResultStore
from dao_vang.web.api_server import APIHandler


def test_api_server_get_signals(tmp_path: Path):
    db_path = str(tmp_path / "test.duckdb")
    
    # Initialize the actual stores with a temporary file DB so schema persists
    scan_store = ScanResultStore(db_path)
    scan_store._init_schema()
    alert_store = AlertStore(db_path)
    # The AlertStore schema is auto-initialized if read_only=False
    
    # Insert a dummy prediction
    with duckdb.connect(db_path) as conn:
        conn.execute("""
            INSERT INTO predictions (
                prediction_id, symbol, signal_time, created_at,
                horizon_hours, target_drawdown, calibrated_probability,
                quality_status, candidate_passed, state, tier, shadow_mode, telegram_sent,
                alert_episode_id, episode_role, episode_transition, model_id
            ) VALUES (
                'test_pred_1', 'BTCUSDT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                4, 0.08, 0.85, 'USABLE', TRUE, 'OPEN', 'HIGH_CONFIDENCE', FALSE, TRUE,
                'ep-123', 'FIRST', 'OPENED', 'model_1'
            )
        """)

    with patch("dao_vang.web.api_server._scan_store", scan_store), \
         patch("dao_vang.web.api_server._alert_store", alert_store), \
         patch("dao_vang.web.api_server._STATUS_CACHE_LOCK", MagicMock()):
         
        # Create mock handler
        handler = MagicMock(spec=APIHandler)
        handler.wfile = MagicMock()
        
        # We need to bind the method to our mock handler
        APIHandler.get_signals(handler)
        
        # Check that wfile.write was called with JSON
        handler.wfile.write.assert_called_once()
        written_data = handler.wfile.write.call_args[0][0]
        payload = json.loads(written_data.decode('utf-8'))
        
        # Verify the episode role is in the payload
        assert isinstance(payload, list)
        if len(payload) > 0:
            assert payload[0].get("episode_role") == "FIRST"
            assert payload[0].get("episode_transition") == "OPENED"

def test_api_server_get_signals_status_filters(tmp_path: Path):
    db_path = str(tmp_path / "test_filter.duckdb")
    scan_store = ScanResultStore(db_path)
    scan_store._init_schema()
    alert_store = AlertStore(db_path)

    with duckdb.connect(db_path) as conn:
        # Insert active prediction (horizon 24h from now)
        conn.execute("""
            INSERT INTO predictions (
                prediction_id, symbol, signal_time, created_at,
                horizon_hours, target_drawdown, calibrated_probability,
                quality_status, candidate_passed, state, tier, shadow_mode, telegram_sent,
                invalidation_time, model_id
            ) VALUES (
                'pred_active', 'ACTUSDT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP,
                24, 0.08, 0.85, 'USABLE', TRUE, 'OPEN', 'HIGH_CONFIDENCE', FALSE, TRUE,
                CURRENT_TIMESTAMP + INTERVAL 24 HOUR, 'model_1'
            )
        """)
        # Insert expired prediction (invalidation passed)
        conn.execute("""
            INSERT INTO predictions (
                prediction_id, symbol, signal_time, created_at,
                horizon_hours, target_drawdown, calibrated_probability,
                quality_status, candidate_passed, state, tier, shadow_mode, telegram_sent,
                invalidation_time, model_id
            ) VALUES (
                'pred_expired', 'EXPUSDT', CURRENT_TIMESTAMP - INTERVAL 48 HOUR, CURRENT_TIMESTAMP - INTERVAL 48 HOUR,
                24, 0.08, 0.80, 'USABLE', TRUE, 'OPEN', 'HIGH_CONFIDENCE', FALSE, TRUE,
                CURRENT_TIMESTAMP - INTERVAL 24 HOUR, 'model_1'
            )
        """)

    with patch("dao_vang.web.api_server._scan_store", scan_store), \
         patch("dao_vang.web.api_server._alert_store", alert_store), \
         patch("dao_vang.web.api_server._STATUS_CACHE_LOCK", MagicMock()), \
         patch("dao_vang.web.api_server._SIGNALS_RESP_CACHE", None):

        # 1. Query with ?status=active
        handler_active = MagicMock(spec=APIHandler)
        handler_active.wfile = MagicMock()
        handler_active.path = "/api/signals?status=active"
        APIHandler.get_signals(handler_active)
        payload_active = json.loads(handler_active.wfile.write.call_args[0][0].decode('utf-8'))
        symbols_active = [s["symbol"] for s in payload_active]
        assert "ACTUSDT" in symbols_active
        assert "EXPUSDT" not in symbols_active

        # Reset cache between tests
        with patch("dao_vang.web.api_server._SIGNALS_RESP_CACHE", None):
            # 2. Query with ?status=expired
            handler_expired = MagicMock(spec=APIHandler)
            handler_expired.wfile = MagicMock()
            handler_expired.path = "/api/signals?status=expired"
            APIHandler.get_signals(handler_expired)
            payload_expired = json.loads(handler_expired.wfile.write.call_args[0][0].decode('utf-8'))
            symbols_expired = [s["symbol"] for s in payload_expired]
            assert "EXPUSDT" in symbols_expired
            assert "ACTUSDT" not in symbols_expired
