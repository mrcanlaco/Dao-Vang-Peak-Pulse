import duckdb
from pathlib import Path
from upsert import atomic_upsert

def run_test():
    target = Path("test_data.parquet")
    csv_file = Path("test_new.csv")
    
    # 1. Tạo data cũ (priority = 0)
    conn = duckdb.connect()
    conn.execute("CREATE TABLE t1 AS SELECT 'BTCUSDT' as symbol, 1000 as open_time, 50.0 as open")
    conn.execute(f"COPY t1 TO '{target.as_posix()}' (FORMAT PARQUET)")
    conn.close()
    
    # 2. Tạo data mới (priority = 1, đụng độ tại 1000)
    with open(csv_file, "w") as f:
        f.write("symbol,open_time,open\nBTCUSDT,1000,99.9\nBTCUSDT,2000,105.0\n")
        
    read_clause = "read_csv_auto([{csv_list}])"
    
    # 3. Upsert
    atomic_upsert(target, [csv_file], "open_time", read_clause)
    
    # 4. Kiểm chứng
    conn = duckdb.connect()
    res = conn.execute(f"SELECT * FROM '{target.as_posix()}' ORDER BY open_time").fetchall()
    
    assert res[0][2] == 99.9, "Row đụng độ: Data mới không ghi đè!"
    assert len(res) == 2, "Sai số lượng rows!"
    print(f"Test passed! Data cuối: {res}")
    
    target.unlink()
    csv_file.unlink()

if __name__ == "__main__":
    run_test()
