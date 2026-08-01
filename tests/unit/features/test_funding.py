import duckdb

from dao_vang.features.builders.funding import build_funding_features_sql


def test_build_funding_features():
    db = duckdb.connect(":memory:")
    db.execute(
        """
        CREATE TABLE raw_timeline (
            feature_time TIMESTAMP,
            symbol VARCHAR,
            funding_rate_last_known DOUBLE
        )
        """
    )

    # Insert some dummy rows
    for i in range(100):
        # alternate funding rates
        val = 0.0001 if i % 2 == 0 else -0.0001
        db.execute(f"INSERT INTO raw_timeline VALUES (epoch_ms({i * 300000}), 'BTCUSDT', {val})")

    sql = build_funding_features_sql("raw_timeline")
    query = f"""
        WITH {sql}
        SELECT feature_time, funding_rate_raw, funding_percentile_7d, funding_change_8h 
        FROM funding_features 
        ORDER BY feature_time
    """

    res = db.execute(query).fetchall()

    assert len(res) == 100
    assert res[0][1] == 0.0001

    # Not nulls check
    not_nulls = [r[2] for r in res if r[2] is not None]
    assert len(not_nulls) > 0
