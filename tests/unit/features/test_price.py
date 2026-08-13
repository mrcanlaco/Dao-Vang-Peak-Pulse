import duckdb

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
