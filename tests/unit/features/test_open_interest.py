import duckdb

from dao_vang.features.builders.open_interest import build_oi_features_sql


def test_build_oi_features():
    db = duckdb.connect(":memory:")
    db.execute(
        """
        CREATE TABLE raw_timeline (
            feature_time TIMESTAMP,
            symbol VARCHAR,
            close DOUBLE,
            open_interest_value DOUBLE
        )
        """
    )

    # Insert dummy data
    for i in range(100):
        db.execute(
            f"INSERT INTO raw_timeline VALUES (epoch_ms({i * 300000}), 'BTCUSDT', {100 + i}, {1000 + i * 10})"
        )

    sql = build_oi_features_sql("raw_timeline")
    query = f"""
        WITH {sql}
        SELECT feature_time, oi_change_1h, oi_zscore_7d, price_oi_divergence_1h
        FROM oi_features 
        ORDER BY feature_time
    """

    res = db.execute(query).fetchall()

    assert len(res) == 100

    # Test valid return value
    # At i = 12, open_interest_value = 1120, at i = 0, open_interest_value = 1000
    # oi_change_1h should be (1120/1000 - 1) = 0.12
    assert abs(res[12][1] - 0.12) < 1e-6
