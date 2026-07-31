from pathlib import Path

import duckdb


class DuckDBQueryLayer:
    """A thin wrapper around DuckDB for querying normalized Parquet datasets."""

    def __init__(self, db_path: Path | str = ":memory:"):
        self.conn = duckdb.connect(str(db_path))

    def query(self, sql: str) -> duckdb.DuckDBPyRelation:
        """Execute a SQL query and return a DuckDB relation."""
        return self.conn.query(sql)

    def register_parquet_view(self, view_name: str, parquet_path: Path | str):
        """Register a Parquet file or glob pattern as a view."""
        # read_parquet handles both single files and globs (e.g. *.parquet)
        sql = (
            f"CREATE OR REPLACE VIEW {view_name} "
            f"AS SELECT * FROM read_parquet('{parquet_path}')"
        )
        self.conn.execute(sql)

    def close(self):
        """Close the DuckDB connection."""
        self.conn.close()
