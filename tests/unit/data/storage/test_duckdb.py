import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from dao_vang.data.schemas import NormalizedFunding, QualityStatus
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.data.storage.parquet import write_normalized_to_parquet


def test_duckdb_query_layer():
    items = [
        NormalizedFunding(
            symbol="BTCUSDT",
            market="USD-M Futures",
            data_type="funding_rate",
            interval=None,
            event_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
            available_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
            collected_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            source_version="v1",
            dataset_version="1.0",
            quality_status=QualityStatus.VALID,
            quality_flags=[],
            funding_time=datetime(2020, 1, 1, tzinfo=timezone.utc),
            funding_rate=Decimal("0.0001"),
            mark_price=Decimal("50000.0"),
        )
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / "test.parquet"
        write_normalized_to_parquet(target_path, items)

        db = DuckDBQueryLayer()
        try:
            db.register_parquet_view("funding", target_path)

            sql = "SELECT symbol, funding_rate, quality_status FROM funding"
            res = db.query(sql).fetchall()
            assert len(res) == 1
            assert res[0][0] == "BTCUSDT"
            assert res[0][1] == Decimal("0.0001")
            assert res[0][2] == "valid"
        finally:
            db.close()
