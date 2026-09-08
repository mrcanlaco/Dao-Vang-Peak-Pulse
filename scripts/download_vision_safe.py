import httpx
import zipfile
import io
import pandas as pd
import duckdb
from pathlib import Path
import json
import hashlib

def main():
    staging_db = Path("artifacts/staging.duckdb")
    if staging_db.exists():
        staging_db.unlink()
    conn = duckdb.connect(str(staging_db))
    
    # 1. Setup Staging Tables (Matching quant_master schema)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staging_metrics_5m (
            symbol VARCHAR, timestamp TIMESTAMP WITH TIME ZONE,
            open_interest DOUBLE, open_interest_value DOUBLE,
            top_trader_account_ratio DOUBLE, top_trader_position_ratio DOUBLE,
            global_account_ratio DOUBLE, taker_buy_sell_ratio DOUBLE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS staging_funding_history (
            symbol VARCHAR, funding_time TIMESTAMP WITH TIME ZONE,
            funding_rate DOUBLE, mark_price DOUBLE
        )
    """)
    
    # Target symbols (The Top 50 Gainers identified earlier)
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
    
    start_date = pd.Timestamp("2025-06-01")
    
    manifest = []
    
    # For demonstration of the validated pipeline, we process a small subset.
    # In full production, loop over all `symbols`.
    test_symbols = symbols[:2]
    
    print(f"Starting Validated Staging Ingestion for {len(test_symbols)} symbols...")
    
    for sym in test_symbols:
        print(f"Processing {sym}...")
        
        # --- A. Daily Metrics Backfill ---
        curr = start_date
        while curr < start_date + pd.Timedelta(days=5): # Test limit for 5 days
            ymd = curr.strftime("%Y-%m-%d")
            url = f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{ymd}.zip"
            chk_url = url + ".CHECKSUM"
            
            try:
                chk_resp = httpx.get(chk_url, timeout=10.0)
                if chk_resp.status_code == 200:
                    expected_hash = chk_resp.text.split()[0].lower()
                    resp = httpx.get(url, timeout=15.0)
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
                            conn.register("tmp_m", df_insert)
                            conn.execute("INSERT INTO staging_metrics_5m SELECT * FROM tmp_m")
                            print(f"  [+] Metrics {ymd} ingested successfully.")
                    else:
                        manifest.append({"url": url, "error": "checksum_mismatch"})
                        print(f"  [!] Checksum mismatch for {ymd}")
                else:
                    manifest.append({"url": url, "error": f"HTTP {chk_resp.status_code}"})
            except Exception as e:
                manifest.append({"url": url, "error": str(e)})
                
            curr += pd.Timedelta(days=1)
            
        # --- B. Monthly Funding Backfill ---
        curr_month = start_date.replace(day=1)
        while curr_month <= start_date: # Test limit for 1 month
            ym = curr_month.strftime("%Y-%m")
            url = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip"
            chk_url = url + ".CHECKSUM"
            
            try:
                chk_resp = httpx.get(chk_url, timeout=10.0)
                if chk_resp.status_code == 200:
                    expected_hash = chk_resp.text.split()[0].lower()
                    resp = httpx.get(url, timeout=15.0)
                    actual_hash = hashlib.sha256(resp.content).hexdigest().lower()
                    
                    if actual_hash == expected_hash:
                        z = zipfile.ZipFile(io.BytesIO(resp.content))
                        df = pd.read_csv(z.open(z.namelist()[0]))
                        if "calc_time" in df.columns:
                            df["funding_time"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
                            df["funding_rate"] = df["last_funding_rate"]
                            df["symbol"] = sym
                            df["mark_price"] = None # Preserve mark_price as NULL
                            
                            df_insert = df[["symbol", "funding_time", "funding_rate", "mark_price"]]
                            conn.register("tmp_f", df_insert)
                            conn.execute("INSERT INTO staging_funding_history SELECT * FROM tmp_f")
                            print(f"  [+] Funding {ym} ingested successfully.")
                    else:
                        manifest.append({"url": url, "error": "checksum_mismatch"})
                else:
                    manifest.append({"url": url, "error": f"HTTP {chk_resp.status_code}"})
            except Exception as e:
                manifest.append({"url": url, "error": str(e)})
                
            curr_month += pd.DateOffset(months=1)
            
    with open("artifacts/download_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
        
    print("\nValidation Summary:")
    print(conn.execute("SELECT symbol, COUNT(*) as rows, MIN(timestamp), MAX(timestamp) FROM staging_metrics_5m GROUP BY symbol").df())
    print("Staging complete. Error manifest saved to artifacts/download_manifest.json.")
    conn.close()

if __name__ == "__main__":
    main()
