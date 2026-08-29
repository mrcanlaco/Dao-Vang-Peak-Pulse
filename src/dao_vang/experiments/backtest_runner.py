from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb
import pandas as pd

from dao_vang.data.historical_adapter import DEFAULT_DATA_LAKE_PATH, DEFAULT_MASTER_DUCKDB, HistoricalDataAdapter
from dao_vang.features.builder import build_features
from dao_vang.labels.engine_v1 import DistributionLabelEngineV1
from dao_vang.labels.specs.distribution_short_v1 import specs as default_label_specs
from dao_vang.scoring.two_tier_scorer import TwoTierDistributionScore

logger = logging.getLogger(__name__)


@dataclass
class BacktestRunConfig:
    start_date: str = "2024-01-01"
    end_date: str = "2026-08-28"
    symbols: Optional[List[str]] = None
    output_db_path: Path | str = Path("artifacts/backtest_results.duckdb")
    data_lake_root: Path | str = DEFAULT_DATA_LAKE_PATH
    master_duckdb_path: Path | str = DEFAULT_MASTER_DUCKDB
    horizon_hours: int = 12


class FullBacktestRunner:
    """End-to-end backtest pipeline runner on multi-year historical data."""

    def __init__(self, config: BacktestRunConfig) -> None:
        self.config = config
        self.adapter = HistoricalDataAdapter(
            master_duckdb_path=config.master_duckdb_path,
            data_lake_root=config.data_lake_root,
        )

    def run(self) -> Dict[str, Any]:
        """Execute end-to-end: Timeline -> Features -> Labels -> Scoring -> Evaluation."""
        output_db = Path(self.config.output_db_path)
        output_db.parent.mkdir(parents=True, exist_ok=True)

        conn = duckdb.connect(str(output_db))
        try:
            # 1. Attach Master DB
            master_posix = Path(self.config.master_duckdb_path).as_posix()
            conn.execute(f"ATTACH '{master_posix}' AS data_lake_db (READ_ONLY)")

            # 2. Build Filtered Source View
            sym_filter = ""
            if self.config.symbols:
                sym_list = ", ".join(f"'{s}'" for s in self.config.symbols)
                sym_filter = f"AND symbol IN ({sym_list})"

            start_t = f"'{self.config.start_date}'"
            end_t = f"'{self.config.end_date}'"

            conn.execute(f"""
            CREATE OR REPLACE VIEW bt_source_timeline AS
            WITH k AS (
                SELECT
                    symbol,
                    close_time AS feature_time,
                    close_time AS decision_time,
                    close_time AS feature_available_time,
                    open, high, low, close,
                    volume AS volume_base,
                    quote_volume AS volume_quote,
                    0 AS trade_count,
                    'valid' AS quality_status
                FROM data_lake_db.klines_5m
                WHERE open_time >= {start_t} AND close_time <= {end_t} {sym_filter}
            ),
            m AS (
                SELECT
                    symbol,
                    timestamp,
                    open_interest AS open_interest_contracts,
                    open_interest_value,
                    top_trader_account_ratio AS top_long_short_ratio,
                    top_trader_position_ratio AS top_long_short_position_ratio,
                    global_account_ratio AS global_long_short_ratio,
                    taker_buy_sell_ratio AS buy_sell_ratio,
                    0.0 AS buy_volume,
                    0.0 AS sell_volume
                FROM data_lake_db.metrics_5m
                WHERE timestamp >= {start_t} AND timestamp <= {end_t} {sym_filter}
            ),
            f AS (
                SELECT
                    symbol,
                    funding_time,
                    funding_rate,
                    mark_price
                FROM data_lake_db.funding_history
                WHERE funding_time >= {start_t} AND funding_time <= {end_t} {sym_filter}
            ),
            km AS (
                SELECT
                    k.*,
                    m.open_interest_contracts,
                    m.open_interest_value,
                    m.buy_volume,
                    m.sell_volume,
                    m.buy_sell_ratio,
                    m.global_long_short_ratio,
                    m.top_long_short_ratio,
                    m.top_long_short_position_ratio
                FROM k
                LEFT JOIN m
                    ON k.symbol = m.symbol
                    AND time_bucket(INTERVAL '5 minutes', k.feature_time) = time_bucket(INTERVAL '5 minutes', m.timestamp)
            )
            SELECT
                km.*,
                COALESCE(f.funding_rate, 0.0) AS funding_rate,
                COALESCE(f.funding_rate, 0.0) AS funding_rate_last_known,
                COALESCE(f.mark_price, km.close) AS mark_price
            FROM km
            ASOF LEFT JOIN f
                ON km.symbol = f.symbol
                AND km.feature_time >= f.funding_time
            """)

            # Wrap for Feature & Label Builder
            class DBWrapper:
                def __init__(self, c):
                    self.conn = c

            db_wrap = DBWrapper(conn)

            # 3. Build Features
            logger.info("Building features from historical timeline...")
            build_features(db_wrap, "bt_source_timeline", "bt_features")

            # 4. Materialize Labels
            logger.info("Materializing labels...")
            spec = default_label_specs[self.config.horizon_hours]
            label_engine = DistributionLabelEngineV1(spec)
            label_engine.compute_all_to_table(conn, "bt_source_timeline", "bt_labels")

            # 5. Summary Evaluation
            eval_query = """
            SELECT 
                COUNT(*) as total_samples,
                COUNT(l.label_value) as valid_labels,
                SUM(CASE WHEN l.label_value = 1 THEN 1 ELSE 0 END) as positive_events,
                AVG(CASE WHEN l.label_value = 1 THEN 1.0 ELSE 0.0 END) as positive_rate
            FROM bt_features f
            JOIN bt_labels l ON f.symbol = l.symbol AND f.feature_time = l.signal_time
            """
            res = conn.execute(eval_query).fetchone()

            summary = {
                "start_date": self.config.start_date,
                "end_date": self.config.end_date,
                "total_samples": int(res[0] or 0),
                "valid_labels": int(res[1] or 0),
                "positive_events": int(res[2] or 0),
                "positive_rate": round(float(res[3] or 0.0), 4),
                "output_db": str(self.config.output_db_path),
            }
            return summary
        finally:
            conn.close()
