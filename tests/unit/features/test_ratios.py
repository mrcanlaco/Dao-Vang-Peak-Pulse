import duckdb

from dao_vang.features.builders.ratios import build_ratio_features_sql


def test_build_ratio_features():
    db = duckdb.connect(":memory:")
    db.execute(
        """
        CREATE TABLE raw_timeline (
            feature_time TIMESTAMP,
            symbol VARCHAR,
            global_long_short_ratio DOUBLE,
            top_long_short_ratio DOUBLE
        )
        """
    )

    # Insert dummy data
    for i in range(100):
        gls = 1.5 + i * 0.01
        tls = 1.0 + i * 0.01
        db.execute(
            f"INSERT INTO raw_timeline VALUES (epoch_ms({i * 300000}), 'BTCUSDT', {gls}, {tls})"
        )

    sql = build_ratio_features_sql("raw_timeline")
    query = f"""
        WITH {sql}
        SELECT feature_time, global_ls_ratio, retail_top_spread, spread_trend_1h
        FROM ratios_features 
        ORDER BY feature_time
    """

    res = db.execute(query).fetchall()

    assert len(res) == 100

    # At i = 0, gls = 1.5, tls = 1.0 => spread = 0.5
    assert res[0][1] == 1.5
    assert abs(res[0][2] - 0.5) < 1e-6

    # Check trend isn't null
    assert res[12][3] is not None
