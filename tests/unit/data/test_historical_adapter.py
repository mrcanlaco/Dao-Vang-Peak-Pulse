from pathlib import Path

import pytest

from dao_vang.data.historical_adapter import (
    DEFAULT_MASTER_DUCKDB,
    HistoricalDataAdapter,
)


def test_historical_adapter_summary():
    adapter = HistoricalDataAdapter(master_duckdb_path=DEFAULT_MASTER_DUCKDB)
    if not Path(DEFAULT_MASTER_DUCKDB).exists():
        pytest.skip("Quant master duckdb not found on disk")
    summary = adapter.get_summary()
    assert summary.symbols_count >= 300
    assert summary.klines_count > 50_000_000
    assert summary.metrics_count > 50_000_000
    assert summary.funding_count > 100_000


def test_historical_adapter_load_symbol():
    adapter = HistoricalDataAdapter(master_duckdb_path=DEFAULT_MASTER_DUCKDB)
    if not Path(DEFAULT_MASTER_DUCKDB).exists():
        pytest.skip("Quant master duckdb not found on disk")
    df = adapter.load_symbol_timeline(
        symbol="BTCUSDT",
        start_time="2024-01-01 00:00:00",
        end_time="2024-01-02 00:00:00",
    )
    assert not df.empty
    assert "close" in df.columns
    assert "open_interest_contracts" in df.columns
    assert "funding_rate" in df.columns
