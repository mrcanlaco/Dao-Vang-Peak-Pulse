import duckdb
from pathlib import Path

def assert_smoke():
    conn = duckdb.connect()
    
    datasets = {
        'klines/5m': ('artifacts/smoke_v2/klines/5m/DASHUSDT.parquet', 'open_time', 5),
        'metrics/5m': ('artifacts/smoke_v2/metrics/5m/DASHUSDT_metrics.parquet', 'timestamp', 5),
        'funding': ('artifacts/smoke_v2/funding/DASHUSDT_funding.parquet', 'funding_time', 8 * 60) # 8 hours cadence
    }
    
    for name, (path, time_col, cadence_mins) in datasets.items():
        print(f"=== Asserting {name} ===")
        p = Path(path)
        assert p.exists(), f"ERROR: File {path} does not exist!"
            
        # Core checks
        res = conn.execute(f"""
            SELECT 
                COUNT(*), 
                MIN({time_col}), 
                MAX({time_col}),
                COUNT(CASE WHEN {time_col} IS NULL OR symbol IS NULL THEN 1 END) as nulls,
                COUNT(DISTINCT symbol || {time_col}) as unique_keys
            FROM read_parquet('{path}')
        """).fetchone()
        
        assert res is not None, "Query returned None"
        rows, min_t, max_t, nulls, unique_keys = res
        
        print(f"Min Time: {min_t}, Max Time: {max_t}")
        print(f"Row Count: {rows}, Unique Keys: {unique_keys}, Nulls: {nulls}")
        
        assert nulls == 0, f"Validation failed: {nulls} NULL keys found!"
        assert rows == unique_keys, f"Validation failed: {rows - unique_keys} duplicate keys found!"
        assert rows > 0, "Validation failed: 0 rows found!"
        
        # Cadence check
        diff_minutes = (max_t - min_t).total_seconds() / 60
        expected_rows = int(diff_minutes / cadence_mins) + 1
        
        # Cho phép du xê dịch một chút do Binance API hoặc thời gian lên sàn
        # Nhưng lý tưởng nhất là expected_rows == rows
        missing_intervals = expected_rows - rows
        print(f"Expected Rows ({cadence_mins}m cadence): {expected_rows}")
        print(f"Missing Intervals: {missing_intervals}")
        if name == 'metrics/5m':
            assert missing_intervals <= 10, f"Cadence validation failed: Missing {missing_intervals} intervals (> 10 limit)!"
        else:
            assert missing_intervals == 0, f"Cadence validation failed: Missing {missing_intervals} intervals!"
        print(f"[{name}] PASSED ALL ASSERTIONS.\n")

if __name__ == "__main__":
    assert_smoke()
