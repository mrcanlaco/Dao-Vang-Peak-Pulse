from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.features.builder import build_features


def test_build_features():
    db = DuckDBQueryLayer(":memory:")

    # Create the raw_timeline view with all necessary columns for all builders
    db.conn.execute(
        """
        CREATE VIEW raw_timeline AS 
        SELECT 
            epoch_ms(i * 300000) AS feature_time,
            'BTCUSDT' AS symbol,
            100 + i AS close,
            105 + i AS high,
            95 + i AS low,
            100 + i * 10 AS volume_base,
            100 + i * 10 AS volume_quote,
            0.0001 + i * 0.00001 AS funding_rate_last_known,
            10 + i AS funding_age_minutes,
            1000 + i * 10 AS open_interest_contracts,
            1000 + i * 100 AS open_interest_value,
            1000 + i * 10 AS buy_volume,
            1000 - i * 10 AS sell_volume,
            1.0 AS buy_sell_ratio,
            1.5 + i * 0.01 AS global_long_short_ratio,
            1.0 + i * 0.01 AS top_long_short_ratio
        FROM range(100) tbl(i)
        """
    )

    build_features(db, "raw_timeline", "feature_dataset")

    res = db.query("SELECT * FROM feature_dataset ORDER BY feature_time").fetchall()

    # Check that we have the rows
    assert len(res) == 100

    # Check columns
    cols = db.query("DESCRIBE feature_dataset").fetchall()
    col_names = [c[0] for c in cols]

    # Ensure some key features are present
    assert "feature_time" in col_names
    assert "price_ret_5m" in col_names
    assert "funding_rate_raw" in col_names
    assert "oi_change_1h" in col_names
    assert "taker_buy_ratio" in col_names
    assert "global_ls_ratio" in col_names

    # Ensure there's only ONE feature_time column
    assert col_names.count("feature_time") == 1
