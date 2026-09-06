import duckdb
from pathlib import Path

db_path = "data/dev.duckdb"
print(f"Updating views in {db_path} to include all historical data...")

conn = duckdb.connect(db_path)

tables = ["klines", "open_interest", "taker_ratio", "global_ratio", "top_ratio", "top_position_ratio", "funding"]
view_names = ["kline", "open_interest", "taker_volume", "global_ratio", "top_ratio", "top_position_ratio", "funding"]

for table_dir, view_name in zip(tables, view_names):
    # Use glob to match all dates
    parquet_glob = f"data/normalized/{table_dir}/**/*.parquet"
    print(f"Registering view {view_name} -> {parquet_glob}")
    
    # We use union_by_name to handle schema evolution if any
    sql = f"""
    CREATE OR REPLACE VIEW {view_name} AS 
    SELECT * FROM read_parquet('{parquet_glob}', union_by_name=true)
    """
    
    # Special handling for deduplication if needed like in the original views
    if view_name == 'kline':
        sql += " QUALIFY (row_number() OVER (PARTITION BY symbol, close_time ORDER BY available_time DESC) = 1)"
    elif view_name == 'funding':
        sql += " QUALIFY (row_number() OVER (PARTITION BY symbol, event_time ORDER BY available_time DESC) = 1)"
    else:
        sql += " QUALIFY (row_number() OVER (PARTITION BY symbol, period_end ORDER BY available_time DESC) = 1)"

    conn.execute(sql)

print("Recreating aligned_5m view...")
# Recreate aligned_5m using the timeline module which has the exact SQL
from dao_vang.data.timeline import align_exact_5m
# We need to wrap conn in DuckDBQueryLayer for the align_exact_5m function
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
layer = DuckDBQueryLayer(db_path)
layer.conn = conn
align_exact_5m(layer, "aligned_5m", top_position_view="top_position_ratio")

print("Creating final_dataset with ASOF funding join...")
from dao_vang.data.timeline import align_funding_asof
align_funding_asof(layer, "final_dataset", aligned_view="aligned_5m", funding_view="funding")

print("Done updating views!")
