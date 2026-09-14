from pathlib import Path
from unittest.mock import patch

import duckdb

from dao_vang.config.settings import AppSettings, ExecutionConfig
from dao_vang.execution.binance_api import BinanceExecutionClient, format_to_step
from dao_vang.execution.engine import ExecutionEngine


def test_format_to_step():
    assert format_to_step(0.12345, "0.001") == "0.123"
    assert format_to_step(123.456, "0.01") == "123.45"
    assert format_to_step(10.55, "0.05") == "10.55"
    assert format_to_step(10.59, "0.05") == "10.55"
    assert format_to_step(100.99, "1") == "100"


def test_binance_rules_cache():
    config = ExecutionConfig(
        enabled=True,
        paper_trading=True,
        api_key="mock_key",
        api_secret="mock_secret",
    )
    client = BinanceExecutionClient(config)

    fake_exchange_info = {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                    {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                    {"filterType": "MIN_NOTIONAL", "notional": "5.0"},
                ],
            }
        ]
    }

    with patch.object(client, "_request", return_value=fake_exchange_info) as mock_req:
        rules1 = client.get_symbol_rules("BTCUSDT")
        assert rules1["step_size"] == "0.001"
        assert rules1["tick_size"] == "0.1"
        assert rules1["min_notional"] == 5.0
        assert mock_req.call_count == 1

        # Second call should use cache
        rules2 = client.get_symbol_rules("BTCUSDT")
        assert rules2 == rules1
        assert mock_req.call_count == 1


def test_place_bracket_short_batch():
    config = ExecutionConfig(
        enabled=True,
        paper_trading=True,
        api_key="mock_key",
        api_secret="mock_secret",
    )
    client = BinanceExecutionClient(config)
    client._rules_cache["BTCUSDT"] = {
        "step_size": "0.001",
        "tick_size": "0.1",
        "min_qty": 0.001,
        "min_notional": 5.0,
    }

    with patch.object(client, "place_batch_orders", return_value=[{"orderId": 1}, {"orderId": 2}, {"orderId": 3}]) as mock_batch:
        res = client.place_bracket_short(
            symbol="BTCUSDT",
            quantity=0.01234,
            entry_price=60000.0,
            stop_loss_price=63000.0,
            take_profit_price=54000.0,
        )
        assert res["batch"] is True
        assert len(res["results"]) == 3
        mock_batch.assert_called_once()
        orders = mock_batch.call_args[0][0]
        assert len(orders) == 3
        assert orders[0]["side"] == "SELL"
        assert orders[0]["type"] == "MARKET"
        assert orders[0]["quantity"] == "0.012"
        assert orders[1]["side"] == "BUY"
        assert orders[1]["type"] == "STOP_MARKET"
        assert orders[1]["stopPrice"] == "63000.0"
        assert orders[2]["side"] == "BUY"
        assert orders[2]["type"] == "TAKE_PROFIT_MARKET"
        assert orders[2]["stopPrice"] == "54000.0"


def test_execution_engine_dry_run(tmp_path: Path):
    db_path = tmp_path / "dev.duckdb"
    conn = duckdb.connect(str(db_path))
    conn.execute("""
        CREATE TABLE alert_history (
            alert_episode_id VARCHAR,
            symbol VARCHAR,
            probability DOUBLE,
            close_price DOUBLE,
            signal_time TIMESTAMP,
            shadow_mode BOOLEAN
        )
    """)
    conn.execute("""
        INSERT INTO alert_history VALUES
        ('alert_1', 'ETHUSDT', 0.85, 3000.0, CURRENT_TIMESTAMP, FALSE)
    """)
    conn.close()

    settings = AppSettings()
    settings.execution.enabled = True
    settings.execution.paper_trading = True
    settings.execution.api_key = None  # Dry run

    engine = ExecutionEngine(settings, db_path)
    engine.connect()
    engine.poll_signals()

    # Verify executed signals table in separate execution.duckdb
    exec_conn = duckdb.connect(str(tmp_path / "execution.duckdb"))
    executed = exec_conn.execute("SELECT prediction_id FROM executed_signals").fetchall()
    assert len(executed) == 1
    assert executed[0][0] == "alert_1"
    exec_conn.close()

    if engine._db_conn:
        engine._db_conn.close()
    if engine._exec_conn:
        engine._exec_conn.close()
