import argparse
import hashlib
import io
import os
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import cast

import duckdb
import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dao_vang.data.historical_adapter import DEFAULT_MASTER_DUCKDB

db_lock = threading.Lock()

def init_staging(db_path: Path):
    with duckdb.connect(str(db_path)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS staging_metrics_5m (
                symbol VARCHAR, timestamp TIMESTAMP WITH TIME ZONE,
                open_interest DOUBLE, open_interest_value DOUBLE,
                top_trader_account_ratio DOUBLE, top_trader_position_ratio DOUBLE,
                global_account_ratio DOUBLE, taker_buy_sell_ratio DOUBLE
            );
            CREATE TABLE IF NOT EXISTS staging_funding_history (
                symbol VARCHAR, funding_time TIMESTAMP WITH TIME ZONE,
                funding_rate DOUBLE, mark_price DOUBLE
            );
            CREATE TABLE IF NOT EXISTS download_state (
                url VARCHAR PRIMARY KEY, status VARCHAR
            );
        """)

def get_completed_urls(db_path: Path):
    with duckdb.connect(str(db_path), read_only=True) as conn:
        try:
            rows = conn.execute("SELECT url FROM download_state WHERE status = 'ok'").fetchall()
            return set(r[0] for r in rows)
        except Exception:
            return set()

def insert_and_mark(url: str, status: str, db_path: Path, df_insert: pd.DataFrame | None = None, table_name: str | None = None):
    """Atomically marks a URL completed and inserts its payload into staging."""
    with db_lock:
        with duckdb.connect(str(db_path)) as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute("INSERT OR REPLACE INTO download_state VALUES (?, ?)", [url, status])
                if df_insert is not None and not df_insert.empty and status == "ok" and table_name:
                    conn.register("tmp_df", df_insert)
                    conn.execute(f"INSERT INTO {table_name} SELECT * FROM tmp_df")
                conn.execute("COMMIT")
            except Exception as e:
                conn.execute("ROLLBACK")
                raise e

def fetch_metrics(sym, ymd, completed, db_path):
    url = f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{ymd}.zip"
    if url in completed:
        return
    chk_url = url + ".CHECKSUM"
    try:
        with httpx.Client(timeout=20.0) as client:
            chk_resp = client.get(chk_url)
            if chk_resp.status_code == 200:
                expected_hash = chk_resp.text.split()[0].lower()
                resp = client.get(url)
                actual_hash = hashlib.sha256(resp.content).hexdigest().lower()
                if actual_hash == expected_hash:
                    z = zipfile.ZipFile(io.BytesIO(resp.content))
                    df = pd.read_csv(z.open(z.namelist()[0]))
                    if "create_time" in df.columns:
                        df["timestamp"] = pd.to_datetime(df["create_time"], utc=True)
                        df_insert = df[[
                            "symbol", "timestamp", "sum_open_interest", "sum_open_interest_value", 
                            "count_toptrader_long_short_ratio", "sum_toptrader_long_short_ratio", 
                            "count_long_short_ratio", "sum_taker_long_short_vol_ratio"
                        ]].copy()
                        df_insert.columns = [
                            "symbol", "timestamp", "open_interest", "open_interest_value", 
                            "top_trader_account_ratio", "top_trader_position_ratio", 
                            "global_account_ratio", "taker_buy_sell_ratio"
                        ]
                        insert_and_mark(url, "ok", db_path, cast(pd.DataFrame, df_insert), "staging_metrics_5m")
                    else:
                        insert_and_mark(url, "schema_error", db_path)
                else:
                    insert_and_mark(url, "checksum_mismatch", db_path)
            else:
                insert_and_mark(url, f"http_{chk_resp.status_code}", db_path)
    except Exception as e:
        insert_and_mark(url, str(e), db_path)

def fetch_funding(sym, ym, completed, db_path):
    url = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip"
    if url in completed:
        return
    chk_url = url + ".CHECKSUM"
    try:
        with httpx.Client(timeout=20.0) as client:
            chk_resp = client.get(chk_url)
            if chk_resp.status_code == 200:
                expected_hash = chk_resp.text.split()[0].lower()
                resp = client.get(url)
                actual_hash = hashlib.sha256(resp.content).hexdigest().lower()
                if actual_hash == expected_hash:
                    z = zipfile.ZipFile(io.BytesIO(resp.content))
                    df = pd.read_csv(z.open(z.namelist()[0]))
                    if "calc_time" in df.columns:
                        df["funding_time"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
                        df["funding_rate"] = df["last_funding_rate"]
                        df["symbol"] = sym
                        df["mark_price"] = None
                        df_insert = df[["symbol", "funding_time", "funding_rate", "mark_price"]].copy()
                        insert_and_mark(url, "ok", db_path, cast(pd.DataFrame, df_insert), "staging_funding_history")
                    else:
                        insert_and_mark(url, "schema_error", db_path)
                else:
                    insert_and_mark(url, "checksum_mismatch", db_path)
            else:
                insert_and_mark(url, f"http_{chk_resp.status_code}", db_path)
    except Exception as e:
        insert_and_mark(url, str(e), db_path)

def export_deduplicated_parquets(db_path: Path):
    print("Deduplicating staging data against Master DB and exporting atomically...")
    
    metrics_final = Path("D:/Quant-trading/data_lake/metrics/5m/vision_backfill_metrics.parquet")
    funding_final = Path("D:/Quant-trading/data_lake/funding/vision_backfill_funding.parquet")
    metrics_tmp = Path("artifacts/tmp_metrics.parquet")
    funding_tmp = Path("artifacts/tmp_funding.parquet")
    
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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=str, default="2025-05-01")
    parser.add_argument("--end", type=str, default="2026-06-05")
    parser.add_argument("--limit-symbols", type=int, default=0)
    parser.add_argument("--no-export", action="store_true")
    parser.add_argument("--test-btcusdt", action="store_true")
    args = parser.parse_args()

    staging_db = Path("artifacts/staging.duckdb")

    if args.test_btcusdt:
        print("Running in TEST MODE: BTCUSDT, June 2025.")
        symbols = ["BTCUSDT"]
        start_date = pd.Timestamp("2025-06-01")
        end_date = pd.Timestamp("2025-06-03")
        args.no_export = True
        staging_db = Path("artifacts/staging_test.duckdb")
        if staging_db.exists():
            staging_db.unlink()
    else:
        symbols = [
            "COAIUSDT", "JELLYJELLYUSDT", "SOONUSDT", "MUSDT", "ZECUSDT", 
            "BANANAS31USDT", "BASUSDT", "HUSDT", "HEMIUSDT", "TUTUSDT", 
            "DASHUSDT", "KITEUSDT", "QUSDT", "BEATUSDT", "XPINUSDT", 
            "UBUSDT", "BLESSUSDT", "VELVETUSDT", "BIOUSDT", "CLOUSDT", 
            "PENGUUSDT", "MERLUSDT", "XPLUSDT", "SNXUSDT", "LIGHTUSDT", 
            "PIEVERSEUSDT", "CFXUSDT", "CCUSDT", "BRUSDT", "SPKUSDT", 
            "AEROUSDT", "NMRUSDT", "ZENUSDT", "ENAUSDT", "WLFIUSDT", 
            "CVXUSDT", "MEMEUSDT", "ASTERUSDT", "1000BONKUSDT", "APRUSDT", 
            "REDUSDT", "UAIUSDT", "RIVERUSDT", "PROMUSDT", "RVNUSDT", 
            "BATUSDT", "AKEUSDT", "TWTUSDT", "SPXUSDT", "MORPHOUSDT"
        ]
        if args.limit_symbols > 0:
            symbols = symbols[:args.limit_symbols]
        start_date = pd.Timestamp(args.start)
        end_date = pd.Timestamp(args.end)

    init_staging(staging_db)
    completed = get_completed_urls(staging_db)
    
    tasks = []
    
    for sym in symbols:
        curr_month = start_date.replace(day=1)
        while curr_month <= end_date:
            ym = curr_month.strftime("%Y-%m")
            url = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip"
            tasks.append((fetch_funding, sym, ym, url))
            curr_month += pd.DateOffset(months=1)
            
        curr_day = start_date
        while curr_day <= end_date:
            ymd = curr_day.strftime("%Y-%m-%d")
            url = f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{ymd}.zip"
            tasks.append((fetch_metrics, sym, ymd, url))
            curr_day += pd.Timedelta(days=1)
            
    print(f"Total missing intervals to query: {len(tasks) - len(completed)} (out of {len(tasks)} total)")
    print("Executing concurrent downloads (Bounded ThreadPoolExecutor)...")
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = []
        for func, sym, date_str, _url in tasks:
            futures.append(executor.submit(func, sym, date_str, completed, staging_db))
            
        for i, f in enumerate(as_completed(futures), 1):
            if i % 1000 == 0:
                print(f"Progress: {i}/{len(tasks)}")
                
    print("Download phase complete. Validating manifest...")
    
    with duckdb.connect(str(staging_db), read_only=True) as conn:
        expected_urls = {t[3] for t in tasks}
        state_urls = set(r[0] for r in conn.execute("SELECT url FROM download_state").fetchall())
        missing_urls = expected_urls - state_urls
        if missing_urls:
            print(f"\\nFATAL: {len(missing_urls)} scheduled URLs were never recorded in download_state! Blocking export.")
            sys.exit(1)
            
        error_df = conn.execute("SELECT status, COUNT(*) as count FROM download_state WHERE status NOT IN ('ok', 'http_404') GROUP BY status").df()
        
    if not error_df.empty:
        print("\\nFATAL: Corrupted or failed downloads detected! Blocking export to Master DB to prevent data holes.\\n")
        print(error_df.to_string(index=False))
        print("\\nAction: Please re-run the script. It is fully resumable and will automatically retry these failed URLs.")
        sys.exit(1)
        
    if args.test_btcusdt:
        print("Validating test ingestion...")
        with duckdb.connect(str(staging_db), read_only=True) as conn:
            m_row = conn.execute("SELECT COUNT(*) FROM staging_metrics_5m WHERE symbol = 'BTCUSDT' AND timestamp >= '2025-06-01'").fetchone()
            m_cnt = m_row[0] if m_row else 0
            
            f_row = conn.execute("SELECT COUNT(*) FROM staging_funding_history WHERE symbol = 'BTCUSDT' AND funding_time >= '2025-06-01'").fetchone()
            f_cnt = f_row[0] if f_row else 0
            
            status_df = conn.execute("SELECT status, COUNT(*) as cnt FROM download_state GROUP BY status").df()
            print(f"Metrics rows (BTCUSDT June 2025): {m_cnt}")
            print(f"Funding rows (BTCUSDT June 2025): {f_cnt}")
            print("Status Breakdown:")
            print(status_df)
            
            assert m_cnt > 0, "No metrics ingested during test!"
            assert f_cnt > 0, "No funding ingested during test!"
            
            ok_urls = conn.execute("SELECT COUNT(*) FROM download_state WHERE status = 'ok' AND url LIKE '%BTCUSDT%'").fetchone()
            assert ok_urls and ok_urls[0] > 0, "BTCUSDT URLs were not marked 'ok'"
            
            print("Test passed successfully.")
            
    if not args.no_export:
        export_deduplicated_parquets(staging_db)
    else:
        print("Skipping export due to --no-export flag.")

if __name__ == "__main__":
    main()
