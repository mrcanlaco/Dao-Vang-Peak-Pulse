import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import duckdb

from dao_vang.data.dataset import DatasetBuilder
from dao_vang.data.schemas import (
    NormalizedFunding,
    NormalizedKline,
    QualityStatus,
)
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.data.storage.parquet import write_normalized_to_parquet


def test_build_dataset():
    dt_1200 = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    dt_1205 = datetime(2020, 1, 1, 12, 5, tzinfo=timezone.utc)
    dt_120501 = datetime(2020, 1, 1, 12, 5, 1, tzinfo=timezone.utc)

    kline1 = NormalizedKline(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="kline",
        interval="5m",
        event_time=dt_1205,
        available_time=dt_120501,
        collected_at=dt_120501,
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        open_time=dt_1200,
        close_time=dt_1205,
        open=Decimal("100"),
        high=Decimal("120"),
        low=Decimal("90"),
        close=Decimal("110"),
        volume_base=Decimal("1000"),
        volume_quote=Decimal("100000"),
        trade_count=500,
        taker_buy_base=Decimal("600"),
        taker_buy_quote=Decimal("60000"),
    )

    funding1 = NormalizedFunding(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="funding",
        interval="8h",
        event_time=dt_1200,
        available_time=dt_1200,
        collected_at=dt_1200,
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        funding_time=dt_1200,
        funding_rate=Decimal("0.0001"),
        mark_price=Decimal("110.0"),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        kline_path = tmp / "kline.parquet"
        oi_path = tmp / "oi.parquet"
        tv_path = tmp / "tv.parquet"
        gr_path = tmp / "gr.parquet"
        tr_path = tmp / "tr.parquet"
        funding_path = tmp / "funding.parquet"
        out_path = tmp / "final.parquet"

        # Write actual data for kline and funding
        write_normalized_to_parquet(kline_path, [kline1])
        write_normalized_to_parquet(funding_path, [funding1])

        # Write empty valid parquets for others to avoid SQL schema errors
        # In actual usage, they will be empty if no data, or populated.
        # But wait! Parquet requires a schema.
        # Let's just create empty tables using duckdb and export them.
        dummy = duckdb.connect(":memory:")
        dummy.execute(
            f"COPY (SELECT 'BTCUSDT' AS symbol, CAST(NULL AS TIMESTAMP) AS period_end, CAST(NULL AS TIMESTAMP) AS available_time, 'valid' AS quality_status, 0.0 AS open_interest_contracts, 0.0 AS open_interest_value WHERE FALSE) TO '{oi_path}' (FORMAT PARQUET)"
        )
        dummy.execute(
            f"COPY (SELECT 'BTCUSDT' AS symbol, CAST(NULL AS TIMESTAMP) AS period_end, CAST(NULL AS TIMESTAMP) AS available_time, 'valid' AS quality_status, 0.0 AS buy_volume, 0.0 AS sell_volume, 0.0 AS buy_sell_ratio WHERE FALSE) TO '{tv_path}' (FORMAT PARQUET)"
        )
        dummy.execute(
            f"COPY (SELECT 'BTCUSDT' AS symbol, CAST(NULL AS TIMESTAMP) AS period_end, CAST(NULL AS TIMESTAMP) AS available_time, 'valid' AS quality_status, 0.0 AS long_account, 0.0 AS short_account, 0.0 AS long_short_ratio WHERE FALSE) TO '{gr_path}' (FORMAT PARQUET)"
        )
        dummy.execute(
            f"COPY (SELECT 'BTCUSDT' AS symbol, CAST(NULL AS TIMESTAMP) AS period_end, CAST(NULL AS TIMESTAMP) AS available_time, 'valid' AS quality_status, 0.0 AS long_account, 0.0 AS short_account, 0.0 AS long_short_ratio WHERE FALSE) TO '{tr_path}' (FORMAT PARQUET)"
        )
        dummy.close()

        db = DuckDBQueryLayer()
        try:
            builder = DatasetBuilder(db)
            manifest = builder.build_dataset(
                output_path=out_path,
                kline_path=kline_path,
                oi_path=oi_path,
                taker_path=tv_path,
                global_ratio_path=gr_path,
                top_ratio_path=tr_path,
                funding_path=funding_path,
                dataset_version="1.0",
            )

            assert out_path.exists()
            assert manifest["rows"] == 1
            assert "fingerprint" in manifest

            # Verify the exported parquet content
            check = duckdb.connect(":memory:")
            res = check.execute(
                f"SELECT feature_time, close, funding_rate_last_known FROM read_parquet('{out_path}')"
            ).fetchall()
            assert len(res) == 1
            assert res[0][1] == 110.0
            assert res[0][2] == Decimal("0.0001")
            check.close()

        finally:
            db.close()
