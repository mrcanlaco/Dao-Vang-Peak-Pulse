import httpx
import hashlib
import zipfile
import io
import duckdb
import json
from pathlib import Path

def run_smoke_test():
    sym = "DASHUSDT"
    with open("data/backfill_manifest.json") as f:
        manifest = json.load(f)
    missing_months = manifest[sym]["missing_months"]
    if not missing_months:
        print(f"No missing months for {sym}")
        return
    
    ym = missing_months[0]
    print(f"Smoke testing {sym} for {ym}...")
    
    db_path = Path("artifacts/smoke_test.duckdb")
    if db_path.exists(): 
        db_path.unlink()
    
    conn = duckdb.connect(str(db_path))
    
    # 1. Test Klines
    kline_url = f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{sym}-5m-{ym}.zip"
    
    print(f"Fetching {kline_url}...")
    chk_resp = httpx.get(kline_url + ".CHECKSUM", timeout=10)
    if chk_resp.status_code == 200:
        expected_hash = chk_resp.text.split()[0].lower()
        print(f"Expected checksum: {expected_hash}")
        
        resp = httpx.get(kline_url, timeout=30)
        actual_hash = hashlib.sha256(resp.content).hexdigest().lower()
        print(f"Actual checksum:   {actual_hash}")
        
        assert expected_hash == actual_hash, f"Checksum mismatch! {expected_hash} != {actual_hash}"
        print("Checksum OK. Extracting...")
        
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            csv_name = z.namelist()[0]
            csv_data = z.read(csv_name)
            
        tmp_csv = Path("artifacts/tmp_smoke_klines.csv")
        tmp_csv.write_bytes(csv_data)
        
        # Đọc bằng DuckDB, tận dụng Header có sẵn của Binance Vision
        conn.execute(f"""
            CREATE TABLE staging_klines AS 
            SELECT 
                '{sym}' as symbol,
                to_timestamp(open_time / 1000) as open_time,
                open, high, low, close, volume
            FROM read_csv_auto('{tmp_csv.as_posix()}', header=True)
        """)
        
        # 2. Audit
        res = conn.execute("SELECT MIN(open_time), MAX(open_time), COUNT(*), COUNT(DISTINCT open_time) FROM staging_klines").fetchone()
        nulls = conn.execute("SELECT COUNT(*) FROM staging_klines WHERE open_time IS NULL").fetchone()[0]
        
        print("\n--- AUDIT RESULTS ---")
        print(f"Min time: {res[0]}")
        print(f"Max time: {res[1]}")
        print(f"Row count: {res[2]}")
        print(f"Unique times: {res[3]}")
        print(f"Null times: {nulls}")
        print(f"Duplicates: {res[2] - res[3]}")
        
        tmp_csv.unlink(missing_ok=True)
    else:
        print(f"Lỗi tải Checksum: {chk_resp.status_code}")
        
    conn.close()

if __name__ == "__main__":
    run_smoke_test()
