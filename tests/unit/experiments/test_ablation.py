import duckdb

from dao_vang.experiments.ablation import generate_ablation_queries


def test_generate_ablation_queries():
    db = duckdb.connect(':memory:')
    db.execute("CREATE TABLE features (id INT, price_ret_24h FLOAT, volume_percentile_24h FLOAT, funding_rate_raw FLOAT)")
    
    queries = generate_ablation_queries(db, 'features')
    
    # Check full
    assert "NULL" not in queries["full"]
    
    # Check price_only (volume and funding should be NULL)
    assert "NULL AS volume_percentile_24h" in queries["price_only"]
    assert "NULL AS funding_rate_raw" in queries["price_only"]
    assert "price_ret_24h" in queries["price_only"]
    assert "NULL AS price_ret_24h" not in queries["price_only"]

    # Check price_volume
    assert "NULL AS volume_percentile_24h" not in queries["price_volume"]
    assert "NULL AS funding_rate_raw" in queries["price_volume"]

