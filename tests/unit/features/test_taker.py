import duckdb

from dao_vang.features.builders.taker import build_taker_features_sql


def test_build_taker_features():
    db = duckdb.connect(":memory:")
    db.execute(
        """
        CREATE TABLE raw_timeline (
            feature_time TIMESTAMP,
            close DOUBLE,
            buy_volume DOUBLE,
            sell_volume DOUBLE,
            buy_sell_ratio DOUBLE
        )
        """
    )

    # Insert dummy data
    for i in range(100):
        b = 1000 + i * 10
        s = 1000 - i * 10
        db.execute(
            f"INSERT INTO raw_timeline VALUES (epoch_ms({i * 300000}), {100 + i}, {b}, {s}, {b / s if s else 1.0})"
        )

    sql = build_taker_features_sql("raw_timeline")
    query = f"""
        WITH {sql}
        SELECT feature_time, taker_buy_ratio, taker_buy_ratio_change_1h, price_flow_divergence_1h
        FROM taker_features 
        ORDER BY feature_time
    """

    res = db.execute(query).fetchall()

    assert len(res) == 100

    # At i = 0, b=1000, s=1000 -> buy_ratio = 0.5
    assert res[0][1] == 0.5

    # At i = 12, b=1120, s=880 -> buy_ratio = 1120 / 2000 = 0.56
    # Change = 0.56 - 0.5 = 0.06
    assert abs(res[12][2] - 0.06) < 1e-6
