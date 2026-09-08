import os
from pathlib import Path

import duckdb

STAGING_DB = Path("artifacts/staging.duckdb")
DEFAULT_MASTER_DUCKDB = "D:/Quant-trading/data_lake/quant_master.duckdb"

def export_deduplicated_parquets(db_path: Path):
    print("Deduplicating staging data against Master DB and exporting atomically...")
    
    metrics_final = Path("D:/Quant-trading/data_lake/metrics/5m/vision_backfill_metrics.parquet")
    funding_final = Path("D:/Quant-trading/data_lake/funding/vision_backfill_funding.parquet")
    metrics_tmp = Path("D:/Quant-trading/data_lake/metrics/5m/vision_backfill_metrics.parquet.tmp")
    funding_tmp = Path("D:/Quant-trading/data_lake/funding/vision_backfill_funding.parquet.tmp")
    
    if metrics_tmp.exists():
        metrics_tmp.unlink()
    if funding_tmp.exists():
        funding_tmp.unlink()
    
    master_db = duckdb.connect(str(DEFAULT_MASTER_DUCKDB), read_only=True)
    master_db.execute(f"ATTACH '{db_path}' AS staging (READ_ONLY)")
    
    print("Exporting deduplicated metrics...")
    master_db.execute(f"""
        COPY (
            WITH dedup_staging AS (
                SELECT * FROM staging.staging_metrics_5m
                QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, timestamp ORDER BY timestamp) = 1
            )
            SELECT s.* FROM dedup_staging s
            LEFT JOIN metrics_5m m ON s.symbol = m.symbol AND s.timestamp = m.timestamp
            WHERE m.timestamp IS NULL
        ) TO '{metrics_tmp}' (FORMAT PARQUET)
    """)
    
    print("Exporting deduplicated funding...")
    master_db.execute(f"""
        COPY (
            WITH dedup_staging AS (
                SELECT * FROM staging.staging_funding_history
                QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, funding_time ORDER BY funding_time) = 1
            )
            SELECT s.* FROM dedup_staging s
            LEFT JOIN funding_history f ON s.symbol = f.symbol AND s.funding_time = f.funding_time
            WHERE f.funding_time IS NULL
        ) TO '{funding_tmp}' (FORMAT PARQUET)
    """)
    master_db.close()
    
    print("Validating temp files before atomic move...")
    val_conn = duckdb.connect(":memory:")
    
    if metrics_tmp.exists():
        m_row = val_conn.execute(f"SELECT COUNT(*) FROM read_parquet('{metrics_tmp}')").fetchone()
        cnt = m_row[0] if m_row else 0
        u_row = val_conn.execute(f"SELECT COUNT(DISTINCT symbol || timestamp) FROM read_parquet('{metrics_tmp}')").fetchone()
        uniq = u_row[0] if u_row else 0
        
        assert cnt == uniq, f"Duplicate keys in metrics export! ({cnt} vs {uniq})"
        if cnt > 0:
            os.replace(metrics_tmp, metrics_final)
            print(f"Atomically replaced metrics parquet ({cnt} unique missing rows backfilled).")
        else:
            metrics_tmp.unlink()
            print("No missing metric rows found.")
            
    if funding_tmp.exists():
        f_row = val_conn.execute(f"SELECT COUNT(*) FROM read_parquet('{funding_tmp}')").fetchone()
        cnt = f_row[0] if f_row else 0
        uf_row = val_conn.execute(f"SELECT COUNT(DISTINCT symbol || funding_time) FROM read_parquet('{funding_tmp}')").fetchone()
        uniq = uf_row[0] if uf_row else 0
        
        assert cnt == uniq, f"Duplicate keys in funding export! ({cnt} vs {uniq})"
        if cnt > 0:
            os.replace(funding_tmp, funding_final)
            print(f"Atomically replaced funding parquet ({cnt} unique missing rows backfilled).")
        else:
            funding_tmp.unlink()
            print("No missing funding rows found.")
            
    val_conn.close()

if __name__ == "__main__":
    export_deduplicated_parquets(STAGING_DB)
