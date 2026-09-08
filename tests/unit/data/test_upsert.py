from pathlib import Path

import duckdb
import pytest

from src.dao_vang.updater.upsert import atomic_upsert


@pytest.fixture
def temp_dir(tmp_path):
    return tmp_path

def create_base_parquet(conn, target: Path):
    conn.execute("CREATE TABLE base (symbol VARCHAR, t BIGINT, v DOUBLE)")
    conn.execute("INSERT INTO base VALUES ('A', 1, 10.0), ('B', 1, 20.0)")
    conn.execute(f"COPY base TO '{target.as_posix()}' (FORMAT PARQUET)")
    
def test_upsert_priority_new_wins(temp_dir):
    target = temp_dir / "target.parquet"
    csv = temp_dir / "new.csv"
    conn = duckdb.connect()
    create_base_parquet(conn, target)
    
    with open(csv, "w") as f:
        f.write("symbol,t,v\nA,1,15.0\nA,2,25.0\n")
        
    atomic_upsert(target, [csv], "t", "read_csv_auto([{csv_list}])")
    
    res = conn.execute(f"SELECT * FROM '{target.as_posix()}' ORDER BY symbol, t").fetchall()
    assert res == [('A', 1, 15.0), ('A', 2, 25.0), ('B', 1, 20.0)]
    conn.close()

def test_upsert_schema_mismatch(temp_dir):
    target = temp_dir / "target.parquet"
    csv = temp_dir / "new.csv"
    conn = duckdb.connect()
    create_base_parquet(conn, target)
    
    with open(csv, "w") as f:
        f.write("symbol,wrong_time,v\nA,1,15.0\n")
        
    with pytest.raises(Exception):
        atomic_upsert(target, [csv], "t", "read_csv_auto([{csv_list}])")
        
    # File gốc phải còn nguyên
    res = conn.execute(f"SELECT * FROM '{target.as_posix()}' ORDER BY symbol, t").fetchall()
    assert res == [('A', 1, 10.0), ('B', 1, 20.0)]
    conn.close()

def test_upsert_duplicate_in_new_batch(temp_dir):
    target = temp_dir / "target.parquet"
    csv = temp_dir / "new.csv"
    conn = duckdb.connect()
    create_base_parquet(conn, target)
    
    with open(csv, "w") as f:
        # 2 dòng trùng nhau trong mẻ mới, row dưới cùng lấy win do ORDER BY t DESC (bị trùng t thì fallback row_number)
        # Sửa thành giá trị khác nhau để thấy qualifer
        f.write("symbol,t,v\nA,2,30.0\nA,2,40.0\n")
        
    atomic_upsert(target, [csv], "t", "read_csv_auto([{csv_list}])")
    res = conn.execute(f"SELECT COUNT(*) FROM '{target.as_posix()}' WHERE symbol='A' AND t=2").fetchone()
    assert res and res[0] == 1
    conn.close()

def test_upsert_null_keys_abort(temp_dir):
    target = temp_dir / "target.parquet"
    csv = temp_dir / "new.csv"
    conn = duckdb.connect()
    create_base_parquet(conn, target)
    
    with open(csv, "w") as f:
        f.write("symbol,t,v\n,2,30.0\nA,,40.0\n")
        
    with pytest.raises(ValueError, match="bị NULL khóa"):
        atomic_upsert(target, [csv], "t", "read_csv_auto([{csv_list}])")
        
    res = conn.execute(f"SELECT * FROM '{target.as_posix()}' ORDER BY symbol, t").fetchall()
    assert res == [('A', 1, 10.0), ('B', 1, 20.0)]
    conn.close()
