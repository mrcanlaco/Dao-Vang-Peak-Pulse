import os
from pathlib import Path

import duckdb


def atomic_upsert(target_parquet: Path, csv_paths: list[Path], time_col: str, read_csv_clause: str):
    if not csv_paths:
        return
        
    target_parquet.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = target_parquet.with_suffix('.parquet.tmp')
    
    def sql_path(path: Path) -> str:
        return path.as_posix().replace("'", "''")

    csv_list_str = ", ".join(f"'{sql_path(p)}'" for p in csv_paths)
    new_data_query = read_csv_clause.format(csv_list=csv_list_str).strip().rstrip(';')
    if not new_data_query.lower().startswith(('select ', 'with ')):
        new_data_query = f"SELECT * FROM {new_data_query}"
    time_col = '"' + time_col.replace('"', '""') + '"'
    
    conn = duckdb.connect()
    try:
        if target_parquet.exists():
            conn.execute(f"""
                COPY (
                    SELECT * EXCLUDE(_priority) FROM (
                        SELECT 0 AS _priority, * FROM '{sql_path(target_parquet)}'
                        UNION ALL BY NAME
                        SELECT 1 AS _priority, * FROM ({new_data_query})
                    )
                    QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, {time_col} ORDER BY _priority DESC) = 1
                ) TO '{sql_path(tmp_out)}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """)
        else:
            conn.execute(f"""
                COPY (
                    SELECT * FROM ({new_data_query})
                    QUALIFY ROW_NUMBER() OVER (PARTITION BY symbol, {time_col} ORDER BY {time_col} DESC) = 1
                ) TO '{sql_path(tmp_out)}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """)
            
        # Validation trước replace
        nulls_row = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{sql_path(tmp_out)}') WHERE {time_col} IS NULL OR symbol IS NULL").fetchone()
        nulls = nulls_row[0] if nulls_row else 0
        if nulls > 0:
            raise ValueError(f"Validation failed: {nulls} dòng bị NULL khóa (symbol / {time_col}).")
            
        os.replace(tmp_out, target_parquet)
    except Exception:
        if tmp_out.exists():
            tmp_out.unlink()
        raise
    finally:
        conn.close()
