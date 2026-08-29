from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

from dao_vang.data.storage.duckdb import DuckDBQueryLayer

logger = logging.getLogger(__name__)

DEFAULT_DATA_LAKE_PATH = Path("D:/Quant-trading/data_lake")
DEFAULT_MASTER_DUCKDB = DEFAULT_DATA_LAKE_PATH / "quant_master.duckdb"


@dataclass
class HistoricalDataSummary:
    symbols_count: int
    klines_count: int
    metrics_count: int
    funding_count: int
    earliest_time: Optional[datetime]
    latest_time: Optional[datetime]


class HistoricalDataAdapter:
    """Bridges Quant-trading Data Lake (Parquet / DuckDB) into dao_vang pipeline."""

    def __init__(
        self,
        master_duckdb_path: Path | str = DEFAULT_MASTER_DUCKDB,
        data_lake_root: Path | str = DEFAULT_DATA_LAKE_PATH,
    ) -> None:
        self.master_duckdb_path = Path(master_duckdb_path)
        self.data_lake_root = Path(data_lake_root)

    def get_connection(self, read_only: bool = True) -> duckdb.DuckDBPyConnection:
        """Connect to master duckdb or create in-memory view over parquets."""
        if self.master_duckdb_path.exists():
            return duckdb.connect(str(self.master_duckdb_path), read_only=read_only)
        conn = duckdb.connect(":memory:")
        self._mount_views(conn)
        return conn

    def _mount_views(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Mount parquet files directly into virtual tables if master DB is absent."""
        klines_glob = (self.data_lake_root / "klines" / "5m" / "*.parquet").as_posix()
        metrics_glob = (self.data_lake_root / "metrics" / "5m" / "*.parquet").as_posix()
        funding_glob = (self.data_lake_root / "funding" / "*.parquet").as_posix()

        try:
            conn.execute(f"CREATE OR REPLACE VIEW klines_5m AS SELECT * FROM read_parquet('{klines_glob}')")
        except Exception as e:
            logger.warning(f"Could not mount klines_5m: {e}")

        try:
            conn.execute(f"CREATE OR REPLACE VIEW metrics_5m AS SELECT * FROM read_parquet('{metrics_glob}')")
        except Exception as e:
            logger.warning(f"Could not mount metrics_5m: {e}")

        try:
            conn.execute(f"CREATE OR REPLACE VIEW funding_history AS SELECT * FROM read_parquet('{funding_glob}')")
        except Exception as e:
            logger.warning(f"Could not mount funding_history: {e}")

    def get_summary(self) -> HistoricalDataSummary:
        """Return dataset boundaries and record counts."""
        conn = self.get_connection(read_only=True)
        try:
            k_res = conn.execute(
                "SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(open_time), MAX(close_time) FROM klines_5m"
            ).fetchone()
            m_res = conn.execute("SELECT COUNT(*) FROM metrics_5m").fetchone()
            f_res = conn.execute("SELECT COUNT(*) FROM funding_history").fetchone()

            return HistoricalDataSummary(
                symbols_count=int(k_res[1] or 0),
                klines_count=int(k_res[0] or 0),
                metrics_count=int(m_res[0] or 0),
                funding_count=int(f_res[0] or 0),
                earliest_time=k_res[2],
                latest_time=k_res[3],
            )
        finally:
            conn.close()

    def load_symbol_timeline(
        self,
        symbol: str,
        start_time: Optional[datetime | str] = None,
        end_time: Optional[datetime | str] = None,
    ) -> pd.DataFrame:
        """Load unified 5m timeline for a single symbol aligning klines, metrics and funding."""
        conn = self.get_connection(read_only=True)
        try:
            time_filter_k = ""
            time_filter_m = ""
            time_filter_f = ""

            if start_time:
                st = f"'{start_time}'"
                time_filter_k += f" AND open_time >= {st}"
                time_filter_m += f" AND timestamp >= {st}"
                time_filter_f += f" AND funding_time >= {st}"
            if end_time:
                et = f"'{end_time}'"
                time_filter_k += f" AND close_time <= {et}"
                time_filter_m += f" AND timestamp <= {et}"
                time_filter_f += f" AND funding_time <= {et}"

            query = f"""
            WITH k AS (
                SELECT
                    symbol,
                    close_time AS feature_time,
                    open, high, low, close,
                    volume AS volume_base,
                    quote_volume AS volume_quote,
                    taker_buy_volume AS buy_volume,
                    (volume - taker_buy_volume) AS sell_volume,
                    CASE WHEN (volume - taker_buy_volume) > 0 
                         THEN taker_buy_volume / (volume - taker_buy_volume) 
                         ELSE 1.0 END AS buy_sell_ratio
                FROM klines_5m
                WHERE symbol = '{symbol}' {time_filter_k}
            ),
            m AS (
                SELECT
                    symbol,
                    timestamp,
                    open_interest AS open_interest_contracts,
                    open_interest_value,
                    top_trader_account_ratio AS top_long_short_ratio,
                    top_trader_position_ratio AS top_long_short_position_ratio,
                    global_account_ratio AS global_long_short_ratio
                FROM metrics_5m
                WHERE symbol = '{symbol}' {time_filter_m}
            ),
            f AS (
                SELECT
                    symbol,
                    funding_time,
                    funding_rate,
                    mark_price
                FROM funding_history
                WHERE symbol = '{symbol}' {time_filter_f}
            ),
            km AS (
                SELECT
                    k.*,
                    m.open_interest_contracts,
                    m.open_interest_value,
                    m.top_long_short_ratio,
                    m.top_long_short_position_ratio,
                    m.global_long_short_ratio
                FROM k
                LEFT JOIN m
                    ON k.symbol = m.symbol
                    AND time_bucket(INTERVAL '5 minutes', k.feature_time) = time_bucket(INTERVAL '5 minutes', m.timestamp)
            )
            SELECT
                km.*,
                f.funding_rate,
                f.mark_price
            FROM km
            ASOF LEFT JOIN f
                ON km.symbol = f.symbol
                AND km.feature_time >= f.funding_time
            ORDER BY km.feature_time ASC
            """
            return conn.execute(query).fetchdf()
        finally:
            conn.close()

    def mount_to_target_duckdb(
        self,
        target_db: DuckDBQueryLayer,
        table_prefix: str = "hist_",
        symbols: Optional[List[str]] = None,
        start_time: Optional[datetime | str] = None,
        end_time: Optional[datetime | str] = None,
    ) -> None:
        """Materialize or attach historical views into dao_vang DuckDBQueryLayer."""
        master_posix = self.master_duckdb_path.as_posix()
        target_db.conn.execute(f"ATTACH '{master_posix}' AS data_lake_db (READ_ONLY)")

        sym_filter = ""
        if symbols:
            sym_list = ", ".join(f"'{s}'" for s in symbols)
            sym_filter = f" WHERE symbol IN ({sym_list})"

        time_filter_k = sym_filter
        if start_time:
            time_filter_k += f" {'AND' if sym_filter else 'WHERE'} open_time >= '{start_time}'"
        if end_time:
            time_filter_k += f" AND close_time <= '{end_time}'"

        target_db.conn.execute(f"""
        CREATE OR REPLACE VIEW {table_prefix}klines AS 
        SELECT * FROM data_lake_db.klines_5m {time_filter_k}
        """)

        target_db.conn.execute(f"""
        CREATE OR REPLACE VIEW {table_prefix}metrics AS 
        SELECT * FROM data_lake_db.metrics_5m {sym_filter}
        """)

        target_db.conn.execute(f"""
        CREATE OR REPLACE VIEW {table_prefix}funding AS 
        SELECT * FROM data_lake_db.funding_history {sym_filter}
        """)
