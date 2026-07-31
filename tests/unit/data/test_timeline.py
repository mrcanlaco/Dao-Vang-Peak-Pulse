import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from dao_vang.data.schemas import (
    NormalizedKline,
    NormalizedTakerVolume,
    QualityStatus,
)
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.data.storage.parquet import write_normalized_to_parquet
from dao_vang.data.timeline import align_exact_5m


def test_align_exact_5m():
    # We will create kline and taker_volume parquets

    dt_1200 = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
    dt_1205 = datetime(2020, 1, 1, 12, 5, tzinfo=timezone.utc)
    dt_120501 = datetime(2020, 1, 1, 12, 5, 1, tzinfo=timezone.utc)
    dt_120506 = datetime(2020, 1, 1, 12, 5, 6, tzinfo=timezone.utc)

    kline1 = NormalizedKline(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="kline",
        interval="5m",
        event_time=dt_1205,
        available_time=dt_120501,  # Good, within 5s lag
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

    tv1 = NormalizedTakerVolume(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="taker_volume",
        interval="5m",
        event_time=dt_1205,
        available_time=dt_120501,  # Good
        collected_at=dt_120501,
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        period_start=dt_1200,
        period_end=dt_1205,
        buy_volume=Decimal("100"),
        sell_volume=Decimal("50"),
        buy_sell_ratio=Decimal("2.0"),
    )

    tv2_late = NormalizedTakerVolume(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="taker_volume",
        interval="5m",
        event_time=dt_1205,
        available_time=dt_120506,  # Too late (6 seconds lag)
        collected_at=dt_120506,
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        period_start=dt_1200,
        period_end=dt_1205,
        buy_volume=Decimal("100"),
        sell_volume=Decimal("50"),
        buy_sell_ratio=Decimal("2.0"),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        kline_path = tmp / "kline.parquet"
        tv_path = tmp / "tv.parquet"
        tv_late_path = tmp / "tv_late.parquet"

        write_normalized_to_parquet(kline_path, [kline1])
        write_normalized_to_parquet(tv_path, [tv1])
        write_normalized_to_parquet(tv_late_path, [tv2_late])

        db = DuckDBQueryLayer()
        try:
            db.register_parquet_view("kline", kline_path)
            db.register_parquet_view("taker_volume", tv_path)
            # Empty views for others to avoid SQL errors
            db.conn.execute(
                "CREATE OR REPLACE VIEW open_interest AS SELECT 'BTCUSDT' AS symbol, NULL AS period_end, NULL AS available_time, 'valid' AS quality_status, NULL AS open_interest_contracts, NULL AS open_interest_value WHERE FALSE"
            )
            db.conn.execute(
                "CREATE OR REPLACE VIEW global_ratio AS SELECT 'BTCUSDT' AS symbol, NULL AS period_end, NULL AS available_time, 'valid' AS quality_status, NULL AS long_account, NULL AS short_account, NULL AS long_short_ratio WHERE FALSE"
            )
            db.conn.execute(
                "CREATE OR REPLACE VIEW top_ratio AS SELECT 'BTCUSDT' AS symbol, NULL AS period_end, NULL AS available_time, 'valid' AS quality_status, NULL AS long_account, NULL AS short_account, NULL AS long_short_ratio WHERE FALSE"
            )

            align_exact_5m(db, "aligned_good")
            res = db.query(
                "SELECT feature_time, close, buy_volume FROM aligned_good"
            ).fetchall()
            assert len(res) == 1
            assert res[0][1] == Decimal("110")
            assert res[0][2] == Decimal("100")  # Should be joined

            # Now test with late data
            db.register_parquet_view("taker_volume", tv_late_path)
            align_exact_5m(db, "aligned_late")
            res = db.query(
                "SELECT feature_time, close, buy_volume FROM aligned_late"
            ).fetchall()
            assert len(res) == 1
            assert res[0][1] == Decimal("110")
            assert res[0][2] is None  # Should NOT be joined because it's too late

        finally:
            db.close()


def test_align_funding_asof():
    from dao_vang.data.schemas import NormalizedFunding
    from dao_vang.data.timeline import align_funding_asof

    dt_0000 = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
    dt_000005 = datetime(2020, 1, 1, 0, 0, 5, tzinfo=timezone.utc)
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

    funding_good = NormalizedFunding(
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

    funding_old = NormalizedFunding(
        symbol="BTCUSDT",
        market="USD-M Futures",
        data_type="funding",
        interval="8h",
        event_time=dt_0000,
        available_time=dt_000005,
        collected_at=dt_000005,
        source_version="v1",
        dataset_version="1.0",
        quality_status=QualityStatus.VALID,
        quality_flags=[],
        funding_time=dt_0000,
        funding_rate=Decimal("0.0002"),
        mark_price=Decimal("100.0"),
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        kline_path = tmp / "kline.parquet"
        funding_path = tmp / "funding.parquet"
        funding_old_path = tmp / "funding_old.parquet"

        write_normalized_to_parquet(kline_path, [kline1])
        write_normalized_to_parquet(funding_path, [funding_good])
        write_normalized_to_parquet(funding_old_path, [funding_old])

        db = DuckDBQueryLayer()
        try:
            db.register_parquet_view("kline", kline_path)
            db.conn.execute(
                "CREATE OR REPLACE VIEW open_interest AS SELECT 'BTCUSDT' AS symbol, NULL AS period_end, NULL AS available_time, 'valid' AS quality_status, NULL AS open_interest_contracts, NULL AS open_interest_value WHERE FALSE"
            )
            db.conn.execute(
                "CREATE OR REPLACE VIEW taker_volume AS SELECT 'BTCUSDT' AS symbol, NULL AS period_end, NULL AS available_time, 'valid' AS quality_status, NULL AS buy_volume, NULL AS sell_volume, NULL AS buy_sell_ratio WHERE FALSE"
            )
            db.conn.execute(
                "CREATE OR REPLACE VIEW global_ratio AS SELECT 'BTCUSDT' AS symbol, NULL AS period_end, NULL AS available_time, 'valid' AS quality_status, NULL AS long_account, NULL AS short_account, NULL AS long_short_ratio WHERE FALSE"
            )
            db.conn.execute(
                "CREATE OR REPLACE VIEW top_ratio AS SELECT 'BTCUSDT' AS symbol, NULL AS period_end, NULL AS available_time, 'valid' AS quality_status, NULL AS long_account, NULL AS short_account, NULL AS long_short_ratio WHERE FALSE"
            )

            align_exact_5m(db, "aligned_5m")

            # 1. Good funding (within 12h)
            db.register_parquet_view("funding", funding_path)
            align_funding_asof(db, "aligned_with_funding")
            res = db.query(
                "SELECT funding_rate_last_known, funding_age_minutes FROM aligned_with_funding"
            ).fetchall()
            assert res[0][0] == Decimal("0.0001")
            assert res[0][1] == 5  # 12:05 - 12:00 = 5 minutes

            # 2. Old funding (> 12h) -> should be null
            db.register_parquet_view("funding", funding_old_path)
            align_funding_asof(db, "aligned_with_old_funding")
            res = db.query(
                "SELECT funding_rate_last_known, funding_age_minutes FROM aligned_with_old_funding"
            ).fetchall()
            assert res[0][0] is None
            assert res[0][1] is None

        finally:
            db.close()
