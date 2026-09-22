import duckdb
import pytest

from dao_vang.features.builders.price import build_price_features_sql


def test_build_price_features():
    db = duckdb.connect(":memory:")
    db.execute(
        """
        CREATE TABLE raw_timeline (
            feature_time TIMESTAMP,
            symbol VARCHAR,
            close DOUBLE,
            high DOUBLE,
            volume_base DOUBLE
        )
        """
    )

    # Insert some dummy rows to test the logic
    for i in range(300):
        db.execute(
            f"INSERT INTO raw_timeline VALUES (epoch_ms({i * 300000}), 'BTCUSDT', {100 + i}, {105 + i}, {1000 + (i % 10) * 100})"
        )

    sql = build_price_features_sql("raw_timeline")
    query = f"""
        WITH {sql}
        SELECT feature_time, price_ret_5m, volume_percentile_24h, fake_breakout_1h FROM price_features ORDER BY feature_time
    """

    res = db.execute(query).fetchall()

    assert len(res) == 300
    # price_ret_5m for i=1 should be (101/100) - 1 = 0.01
    # res[1] is the second row, price_ret_5m is the second column (index 1)
    val = res[1][1]
    assert val is not None and abs(val - 0.01) < 1e-6

    # Check volume percentile
    not_nulls = [r[2] for r in res if r[2] is not None]
    assert len(not_nulls) > 0

    # Check fake_breakout_1h: with monotonically increasing highs (105+i),
    # every candle breaks the prior high, but close (100+i) < prior max high
    # (105+i-1) only when i < 5 (close < prev high). For i >= 5, close >= prev high.
    # fake_breakout_1h is column index 3.
    fake_breaks = [r for r in res if r[3] is not None and r[3] > 0.0]
    assert len(fake_breaks) > 0, "Expected some fake breakout signals"
    # All fake break values should be in [0, 1]
    for r in res:
        if r[3] is not None:
            assert 0.0 <= r[3] <= 1.0


def _price_rows(db, source="prices"):
    return db.execute(
        f"WITH {build_price_features_sql(source)} "
        "SELECT * FROM price_features ORDER BY feature_time, symbol"
    ).fetchdf()


def test_price_features_do_not_change_when_future_rows_are_appended():
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE prices AS
            SELECT epoch_ms(i * 300000) AS feature_time, symbol,
                   100.0 + i + (i % 3) * 2 AS close,
                   105.0 + i + (i % 3) * 2 AS high, 1000.0 + i AS volume_base
            FROM range(400) t(i), (VALUES ('BTCUSDT'), ('ALTUSDT')) s(symbol)
        """)
        db.execute("CREATE VIEW prefix AS SELECT * FROM prices WHERE feature_time < epoch_ms(100 * 300000)")
        prefix = _price_rows(db, "prefix")
        full = _price_rows(db).iloc[:len(prefix)].reset_index(drop=True)
        import pandas as pd

        pd.testing.assert_frame_equal(prefix, full, check_exact=False, atol=1e-12, rtol=1e-12)


@pytest.mark.parametrize("bars, column", [(1, "price_ret_5m"), (3, "price_ret_15m"),
                                         (12, "price_ret_1h"), (48, "price_ret_4h"),
                                         (288, "price_ret_24h")])
def test_return_rejects_wrong_elapsed_time(bars, column):
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE prices AS
            SELECT epoch_ms((CASE WHEN i=300 THEN 301 ELSE i END) * 300000) AS feature_time,
                   'BTCUSDT' AS symbol, 100.0 + i AS close,
                   105.0 + i AS high, 1000.0 AS volume_base
            FROM range(301) t(i)
        """)
        result = _price_rows(db)
        import pandas as pd

        assert pd.isna(result.iloc[-1][column])
        assert result.iloc[-2][column] == pytest.approx(399 / (399 - bars) - 1)


def test_rolling_high_does_not_include_candles_older_than_24h():
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE prices AS
            SELECT epoch_ms(i * 300000) AS feature_time, 'ALTUSDT' AS symbol,
                   100.0 AS close, 1000.0 AS high, 1000.0 AS volume_base
            FROM range(20) t(i)
            UNION ALL SELECT epoch_ms(172800000), 'ALTUSDT', 100.0, 110.0, 100.0
        """)
        assert _price_rows(db).iloc[-1]["distance_from_high_24h"] == pytest.approx(100 / 110 - 1)


def test_zero_previous_close_does_not_produce_infinite_return():
    with duckdb.connect() as db:
        db.execute("""
            CREATE TABLE prices AS
            SELECT epoch_ms(i * 300000) AS feature_time, 'ALTUSDT' AS symbol,
                   i::DOUBLE AS close, 2.0 AS high, 1.0 AS volume_base
            FROM range(2) t(i)
        """)
        import pandas as pd

        assert pd.isna(_price_rows(db).iloc[-1]["price_ret_5m"])
