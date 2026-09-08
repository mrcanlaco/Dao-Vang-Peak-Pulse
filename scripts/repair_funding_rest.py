import httpx
import duckdb
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.dao_vang.updater.upsert import atomic_upsert

def audit_funding(sym, path):
    conn = duckdb.connect()
    try:
        res = conn.execute(f"SELECT COUNT(*), COUNT(mark_price), MIN(funding_time), MAX(funding_time) FROM read_parquet('{path}')").fetchone()
        print(f"[{sym}] Rows: {res[0]}, With mark_price: {res[1]}, Range: {res[2]} -> {res[3]}")
    except Exception as e:
        print(f"[{sym}] Audit error: {e}")

def repair():
    for sym in ["DASHUSDT", "ATOMUSDT", "IOTAUSDT"]:
        path = f"D:/Quant-trading/data_lake/funding/{sym}_funding.parquet"
        print(f"--- BEFORE {sym} ---")
        audit_funding(sym, path)

        start_ms = int(pd.Timestamp("2026-08-01", tz="UTC").timestamp() * 1000)
        end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={start_ms}&endTime={end_ms}&limit=1000"
        
        try:
            resp = httpx.get(url, timeout=20.0)
            if resp.status_code == 200 and resp.json():
                df = pd.DataFrame(resp.json())
                out_csv = Path(f"artifacts/tmp_repair_{sym}.csv")
                out_csv.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(out_csv, index=False)
                
                q = """
                SELECT 
                    '{symbol}' as symbol,
                    to_timestamp(fundingTime / 1000) as funding_time,
                    fundingRate as funding_rate,
                    markPrice as mark_price
                FROM read_csv_auto([{csv_list}], header=True)
                """.replace("{symbol}", sym)
                
                atomic_upsert(Path(path), [out_csv], "funding_time", q)
                out_csv.unlink(missing_ok=True)
        except Exception as e:
            print(f"Failed to repair {sym}: {e}")
            
        print(f"--- AFTER {sym} ---")
        audit_funding(sym, path)
        print()

if __name__ == "__main__":
    repair()
