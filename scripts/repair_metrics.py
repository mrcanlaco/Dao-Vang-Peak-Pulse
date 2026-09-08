import duckdb
import os
import json
from pathlib import Path

def repair():
    conn = duckdb.connect()
    symbols = ["DASHUSDT", "ATOMUSDT"]
    
    for sym in symbols:
        path = f"D:/Quant-trading/data_lake/metrics/5m/{sym}.parquet"
        if os.path.exists(path):
            print(f"Repairing {path}...")
            tmp = path + ".tmp"
            
            # Xóa sạch data từ 2026-07-01 trở đi do bị ghi đè sai lệch timezone
            conn.execute(f"""
                COPY (
                    SELECT * FROM read_parquet('{path}') 
                    WHERE timestamp < '2026-07-01 00:00:00+00:00'
                ) TO '{tmp}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """)
            os.replace(tmp, path)
            print(f"Repaired {sym} metrics.")

    # Cập nhật manifest để tải lại tháng 7 cho 2 mã này
    manifest_file = "data/backfill_manifest.json"
    with open(manifest_file, "r") as f:
        manifest = json.load(f)
        
    for sym in symbols:
        if sym in manifest:
            if "2026-07" not in manifest[sym]["missing_months"]:
                manifest[sym]["missing_months"].insert(0, "2026-07")
                
    with open(manifest_file, "w") as f:
        json.dump(manifest, f, indent=2)
    print("Manifest updated to re-fetch July 2026 for repaired symbols.")

if __name__ == "__main__":
    repair()
