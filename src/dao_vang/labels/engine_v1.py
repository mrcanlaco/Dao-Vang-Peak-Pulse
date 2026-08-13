"""Point-in-time distribution label engine, contract ``distribution_short_v1``.

The engine deliberately materializes excluded rows with ``label_value = NULL``.
An excluded row is not a negative example: treating missing future data or an
invalid quality row as ``0`` would bias prevalence and leak data availability
into the model.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import duckdb

from dao_vang.labels.models_v1 import DistributionLabelResultV1
from dao_vang.labels.specs.distribution_short_v1 import (
    DistributionShortV1Spec,
    specs,
)

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(name: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(name):
        raise ValueError(f"Unsafe DuckDB identifier: {name!r}")
    return name


def _columns(db: duckdb.DuckDBPyConnection, table: str) -> set[str]:
    table = _identifier(table)
    try:
        return {str(row[0]) for row in db.execute(f"DESCRIBE {table}").fetchall()}
    except Exception:
        return {str(row[1]) for row in db.execute(f"PRAGMA table_info('{table}')").fetchall()}


class DistributionLabelEngineV1:
    """Materialize one or more deterministic, horizon-specific label tables."""

    def __init__(self, spec: DistributionShortV1Spec):
        if spec.horizon_hours not in (6, 12, 24):
            raise ValueError("distribution_short_v1 supports only 6h, 12h and 24h horizons")
        self.spec = spec
        self.horizon_minutes = spec.horizon_hours * 60

    def compute_all_to_table(
        self,
        db: duckdb.DuckDBPyConnection,
        input_table: str,
        output_table: str,
    ) -> None:
        """Compute labels for ``input_table`` into ``output_table``.

        Accepted timestamp names are ``feature_time`` (production),
        ``timestamp`` (collector/replay tests), or ``close_time``.  A quality
        column is optional for backwards-compatible snapshots; when present,
        ``invalid`` and ``quarantined`` rows are excluded.
        """
        source = _identifier(input_table)
        target = _identifier(output_table)
        cols = _columns(db, source)
        time_col = next(
            (candidate for candidate in ("feature_time", "timestamp", "close_time") if candidate in cols),
            None,
        )
        required = {"symbol", "close", "high", "low"}
        missing = sorted(required - cols)
        if time_col is None or missing:
            raise ValueError(
                "label input requires symbol, close/high/low and a timestamp column; "
                f"missing={missing}, timestamp={time_col!r}"
            )

        quality_expr = (
            "COALESCE(LOWER(CAST(s.quality_status AS VARCHAR)), 'invalid')"
            if "quality_status" in cols
            else "'valid'"
        )
        target_pct = float(self.spec.target_drawdown)
        mae_pct = float(self.spec.max_adverse_excursion)
        gap_tol = int(self.spec.gap_tolerance_minutes)
        horizon = int(self.horizon_minutes)
        # Five-minute candles are closed at the end of their interval.  A
        # 6-hour label therefore needs the last candle at 05:55, not a candle
        # whose timestamp is exactly 06:00.  Keep a full interval of tolerance
        # while still excluding genuinely short futures.
        materialized_until = max(0, horizon - 5)

        # Drop an existing table/view so re-materialization is idempotent.
        for statement in (f"DROP TABLE IF EXISTS {target}", f"DROP VIEW IF EXISTS {target}"):
            try:
                db.execute(statement)
            except Exception:
                pass

        query = f"""
        CREATE TABLE {target} AS
        WITH source_rows AS (
            SELECT src.*, ROW_NUMBER() OVER () AS _source_ord
            FROM {source} src
        ),
        signals AS (
            SELECT
                s.symbol,
                s.{time_col} AS signal_time,
                CAST(s.close AS DOUBLE) AS signal_price,
                {quality_expr} AS signal_quality
            FROM source_rows s
        ),
        future_raw AS (
            SELECT
                s.symbol,
                s.signal_time,
                s.signal_price,
                s.signal_quality,
                f.{time_col} AS f_time,
                CAST(f.high AS DOUBLE) AS f_high,
                CAST(f.low AS DOUBLE) AS f_low,
                (CAST(f.high AS DOUBLE) - s.signal_price) / NULLIF(s.signal_price, 0) AS f_high_pct,
                (CAST(f.low AS DOUBLE) - s.signal_price) / NULLIF(s.signal_price, 0) AS f_low_pct,
                CASE WHEN CAST(f.low AS DOUBLE) <= s.signal_price * (1.0 - {target_pct}) THEN TRUE ELSE FALSE END AS hit_target,
                CASE WHEN CAST(f.high AS DOUBLE) >= s.signal_price * (1.0 + {mae_pct}) THEN TRUE ELSE FALSE END AS hit_mae,
                f._source_ord
            FROM signals s
            JOIN source_rows f
              ON s.symbol = f.symbol
             AND f.{time_col} > s.signal_time
             AND f.{time_col} <= s.signal_time + INTERVAL '{horizon}' MINUTE
        ),
        future_with_gaps AS (
            SELECT
                fr.*,
                LAG(fr.f_time) OVER (
                    PARTITION BY fr.symbol, fr.signal_time ORDER BY fr._source_ord
                ) AS previous_f_time
            FROM future_raw fr
        ),
        evaluated AS (
            SELECT
                s.symbol,
                s.signal_time,
                s.signal_price,
                s.signal_quality,
                MIN(CASE WHEN fw.hit_target THEN fw.f_time END) AS first_target_time,
                MIN(CASE WHEN fw.hit_mae THEN fw.f_time END) AS first_mae_time,
                MAX(CASE WHEN fw.f_time > COALESCE(fw.previous_f_time, s.signal_time)
                         THEN EXTRACT(EPOCH FROM (
                             fw.f_time - COALESCE(fw.previous_f_time, s.signal_time)
                         )) / 60.0 ELSE 0.0 END) AS max_gap_minutes,
                MAX(fw.f_time) AS max_f_time,
                MAX(fw.f_high) AS future_max_high,
                MIN(fw.f_low) AS future_min_low,
                MAX(fw.f_high_pct) AS max_adverse_excursion,
                MIN(fw.f_low_pct) AS max_favorable_excursion
            FROM signals s
            LEFT JOIN future_with_gaps fw
              ON s.symbol = fw.symbol AND s.signal_time = fw.signal_time
            GROUP BY s.symbol, s.signal_time, s.signal_price, s.signal_quality
        )
        SELECT
            symbol,
            signal_time,
            CAST(signal_price AS DECIMAL(20,8)) AS signal_price,
            '{self.spec.version}' AS label_version,
            {self.spec.horizon_hours} AS horizon_hours,
            CASE
                WHEN signal_quality IN ('invalid', 'quarantined') THEN NULL
                WHEN max_gap_minutes > {gap_tol} THEN NULL
                WHEN max_f_time IS NULL OR max_f_time < signal_time + INTERVAL '{materialized_until}' MINUTE THEN NULL
                WHEN first_target_time IS NOT NULL AND first_mae_time = first_target_time THEN NULL
                WHEN first_target_time IS NOT NULL AND (first_mae_time IS NULL OR first_target_time < first_mae_time) THEN 1
                WHEN first_mae_time IS NOT NULL THEN 0
                ELSE 0
            END AS label_value,
            CASE
                WHEN signal_quality IN ('invalid', 'quarantined') THEN NULL
                WHEN max_gap_minutes > {gap_tol} THEN NULL
                WHEN max_f_time IS NULL OR max_f_time < signal_time + INTERVAL '{materialized_until}' MINUTE THEN NULL
                WHEN first_target_time IS NOT NULL AND first_mae_time = first_target_time THEN NULL
                ELSE first_target_time IS NOT NULL
            END AS target_reached,
            first_target_time AS target_time,
            CASE WHEN first_target_time IS NOT NULL
                 THEN EXTRACT(EPOCH FROM (first_target_time - signal_time)) / 60.0
                 ELSE NULL END AS lead_time_minutes,
            max_adverse_excursion,
            max_favorable_excursion,
            CAST(future_max_high AS DECIMAL(20,8)) AS future_max_high,
            CAST(future_min_low AS DECIMAL(20,8)) AS future_min_low,
            CASE
                WHEN signal_quality IN ('invalid', 'quarantined') THEN 'invalid_quality'
                WHEN max_gap_minutes > {gap_tol} THEN 'data_gap'
                WHEN max_f_time IS NULL OR max_f_time < signal_time + INTERVAL '{materialized_until}' MINUTE THEN 'missing_future_data'
                WHEN first_target_time IS NOT NULL AND first_mae_time = first_target_time THEN 'ambiguous_intrabar'
                ELSE NULL
            END AS exclusion_reason,
            CASE
                WHEN first_target_time IS NOT NULL AND first_mae_time = first_target_time THEN TRUE
                ELSE FALSE
            END AS ambiguous_intrabar,
            signal_quality AS quality_status
        FROM evaluated
        """
        db.execute(query)

    def compute_all_horizons_to_table(
        self,
        db: duckdb.DuckDBPyConnection,
        input_table: str,
        output_table: str,
        horizons: Iterable[int] = (6, 12, 24),
    ) -> None:
        """Materialize 6h/12h/24h labels in one table.

        Each horizon is computed using the same input snapshot and then unioned
        with a stable schema.  This prevents accidental use of the default 24h
        label when the caller asks for another horizon.
        """
        requested = tuple(dict.fromkeys(int(h) for h in horizons))
        invalid = [h for h in requested if h not in specs]
        if not requested or invalid:
            raise ValueError(f"horizons must be a non-empty subset of 6/12/24; invalid={invalid}")
        target = _identifier(output_table)
        temp_tables: list[str] = []
        try:
            for horizon in requested:
                temp = f"_labels_v1_{horizon}h"
                temp_tables.append(temp)
                DistributionLabelEngineV1(specs[horizon]).compute_all_to_table(
                    db, input_table, temp
                )
            union_sql = " UNION ALL ".join(
                f"SELECT * FROM {temp}" for temp in temp_tables
            )
            for statement in (f"DROP TABLE IF EXISTS {target}", f"DROP VIEW IF EXISTS {target}"):
                try:
                    db.execute(statement)
                except Exception:
                    pass
            db.execute(f"CREATE TABLE {target} AS {union_sql}")
        finally:
            for temp in temp_tables:
                try:
                    db.execute(f"DROP TABLE IF EXISTS {temp}")
                except Exception:
                    pass


__all__ = ["DistributionLabelEngineV1", "DistributionLabelResultV1"]
