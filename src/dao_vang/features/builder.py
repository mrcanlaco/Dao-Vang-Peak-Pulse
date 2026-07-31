from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.features.builders.funding import build_funding_features_sql
from dao_vang.features.builders.open_interest import build_oi_features_sql
from dao_vang.features.builders.price import build_price_features_sql
from dao_vang.features.builders.ratios import build_ratio_features_sql
from dao_vang.features.builders.taker import build_taker_features_sql


def build_features(db: DuckDBQueryLayer, source_table: str, target_table: str):
    """
    Builds the full feature set table from the source timeline table.
    """
    price_sql = build_price_features_sql(source_table)
    funding_sql = build_funding_features_sql(source_table)
    oi_sql = build_oi_features_sql(source_table)
    taker_sql = build_taker_features_sql(source_table)
    ratios_sql = build_ratio_features_sql(source_table)

    sql = f"""
    CREATE OR REPLACE TABLE {target_table} AS 
    WITH 
    {price_sql},
    {funding_sql},
    {oi_sql},
    {taker_sql},
    {ratios_sql}
    
    SELECT 
       p.*,
       f.* EXCLUDE (feature_time),
       o.* EXCLUDE (feature_time),
       t.* EXCLUDE (feature_time),
       r.* EXCLUDE (feature_time)
    FROM price_features p
    LEFT JOIN funding_features f ON p.feature_time = f.feature_time
    LEFT JOIN oi_features o ON p.feature_time = o.feature_time
    LEFT JOIN taker_features t ON p.feature_time = t.feature_time
    LEFT JOIN ratios_features r ON p.feature_time = r.feature_time
    ORDER BY p.feature_time
    """
    db.conn.execute(sql)
