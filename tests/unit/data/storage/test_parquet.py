import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq  # type: ignore
import pytest

from dao_vang.data.schemas import NormalizedFunding, QualityStatus
from dao_vang.data.storage.parquet import write_normalized_to_parquet


def test_write_normalized_to_parquet_success():
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

        checksum = write_normalized_to_parquet(target_path, items)

        assert target_path.exists()
        assert checksum is not None
        assert len(checksum) == 64

        # Read back to verify
        table = pq.read_table(target_path)  # type: ignore
        assert table.num_rows == 1  # type: ignore

        pydict = table.to_pydict()  # type: ignore
        assert pydict["symbol"][0] == "BTCUSDT"  # type: ignore
        assert pydict["quality_status"][0] == "valid"  # type: ignore
        assert Decimal(pydict["funding_rate"][0]) == Decimal("0.0001")  # type: ignore


def test_write_normalized_to_parquet_empty_list():
    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / "test.parquet"
        with pytest.raises(ValueError, match="Cannot write an empty list"):
            write_normalized_to_parquet(target_path, [])
