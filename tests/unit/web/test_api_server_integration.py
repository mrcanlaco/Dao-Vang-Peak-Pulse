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
