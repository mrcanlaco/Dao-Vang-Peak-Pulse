import duckdb
import json
from pathlib import Path

DATA_LAKE = Path("D:/Quant-trading/data_lake")
UNIVERSE_FILE = Path("data/true_lowcap_universe.json")

def get_time_col(conn, path_pattern):
    try:
        schema = conn.sql(f"DESCRIBE SELECT * FROM '{path_pattern}' LIMIT 1").fetchall()
        cols = [row[0] for row in schema]
        for c in ['open_time', 'funding_time', 'create_time', 'timestamp']:
            if c in cols:
                return c
        for c in cols:
            if 'time' in c.lower():
                return c
        return None
    except Exception:
        return None

def audit():
    print("--- Comprehensive Recursive Audit D: Data Lake ---")
    conn = duckdb.connect()
    
    try:
        with open(UNIVERSE_FILE, 'r') as f:
            u_data = json.load(f)
            if isinstance(u_data, dict):
                universe = set(u_data.keys())
            else:
                universe = set(u_data)
        print(f"Universe size: {len(universe)} symbols\n")
    except Exception as e:
        print(f"Lỗi đọc universe: {e}")
        universe = set()
        
    dirs = [
        "klines/5m", "funding", "open_interest", "metrics",
        "global_ratio", "taker_volume", "top_position_ratio", "top_ratio"
    ]
    
    for d in dirs:
        p = DATA_LAKE / d
        if not p.exists():
            print(f"[{d}] KHÔNG TỒN TẠI")
            continue
            
        path_pattern = f"{p.as_posix()}/**/*.parquet"
        parquet_files = list(p.rglob("*.parquet"))
        
        if not parquet_files:
            print(f"[{d}] TRỐNG (0 files)")
            continue
            
        time_col = get_time_col(conn, path_pattern)
        if not time_col:
            print(f"[{d}] Không tìm thấy cột thời gian")
            continue
            
        try:
            res = conn.sql(f"""
                SELECT 
                    COUNT(DISTINCT symbol) as coins,
                    MIN({time_col}) as min_time,
                    MAX({time_col}) as max_time,
                    COUNT(*) as total_rows
                FROM '{path_pattern}'
            """).fetchone()
            
            symbols_in_db = set(row[0] for row in conn.sql(f"SELECT DISTINCT symbol FROM '{path_pattern}'").fetchall())
            missing = universe - symbols_in_db
            
            print(f"[{d}] (Cột thời gian: {time_col})")
            print(f"  - Coins: {res[0]} (Thiếu {len(missing)} so với Universe)")
            print(f"  - Range: {res[1]} -> {res[2]}")
            print(f"  - Rows: {res[3]}")
            if len(missing) > 0 and len(missing) <= 10:
                print(f"  - Missing samples: {list(missing)[:5]}")
        except Exception as e:
            print(f"[{d}] Lỗi truy vấn: {e}")
        print()

if __name__ == "__main__":
    audit()