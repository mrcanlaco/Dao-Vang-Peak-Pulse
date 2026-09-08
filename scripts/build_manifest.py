import json
import httpx
import duckdb
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path

UNIVERSE_FILE = Path("data/true_lowcap_universe.json")
DATA_LAKE = Path("D:/Quant-trading/data_lake")

def get_listing_times():
    print("Fetching exchangeInfo for listing times...")
    resp = httpx.get("https://fapi.binance.com/fapi/v1/exchangeInfo")
    data = resp.json()
    symbols = {s['symbol']: pd.to_datetime(s['onboardDate'], unit='ms', utc=True) 
               for s in data['symbols'] if 'onboardDate' in s}
    return symbols

def build_manifest():
    with open(UNIVERSE_FILE, 'r') as f:
        u_data = json.load(f)
        universe = list(u_data.keys()) if isinstance(u_data, dict) else list(u_data)
        
    listings = get_listing_times()
    conn = duckdb.connect()
    
    manifest = {}
    base_start = pd.Timestamp("2024-09-07", tz="UTC")
    end_date = pd.Timestamp("2026-09-06 23:55:00", tz="UTC")
    
    for sym in universe:
        sym_start = listings.get(sym, base_start)
        start_date = max(base_start, sym_start).floor('5min')
        
        # Tạo expected 5m intervals
        expected_idx = pd.date_range(start=start_date, end=end_date, freq='5min', tz="UTC")
        expected_df = pd.DataFrame({'expected_time': expected_idx})
        conn.register("expected", expected_df)
        
        missing_months = set()
        missing_days = set()
        
        # Check klines
        kline_path = DATA_LAKE / "klines" / "5m" / f"{sym}.parquet"
        if not kline_path.exists():
            # Missing entirely
            missing_times = expected_idx
        else:
            actual = conn.execute(f"SELECT open_time FROM '{kline_path.as_posix()}'").df()
            if actual.empty:
                missing_times = expected_idx
            else:
                actual['open_time'] = pd.to_datetime(actual['open_time'], utc=True)
                missing_times = expected_idx.difference(actual['open_time'])
                
        if len(missing_times) > 0:
            for t in missing_times:
                # Nếu thiếu > 10% của tháng thì tải nguyên tháng zip, nếu ko thì tải daily zips
                missing_months.add(t.strftime("%Y-%m"))
                
        manifest[sym] = {
            "start": start_date.isoformat(),
            "missing_months": sorted(list(missing_months))
        }
        print(f"{sym}: Thiếu {len(missing_times)} nến 5m. Tương ứng {len(missing_months)} tháng.")
        
    with open("data/backfill_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print("Manifest saved to data/backfill_manifest.json")

if __name__ == "__main__":
    build_manifest()
