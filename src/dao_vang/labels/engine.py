from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

import duckdb

from dao_vang.labels.models import DistributionLabelResult

# Type alias for a row from the database
RowType = Tuple[str, datetime, float, float, float, float, str]


class DistributionLabelEngine:
    """
    Engine to compute Distribution Label v0.1 based on LABEL_SPECIFICATION.md.
    """

    def __init__(
        self,
        target_drawdown: Decimal = Decimal("0.08"),
        max_adverse_excursion: Decimal = Decimal("0.04"),
        max_horizon_minutes: int = 1440,
    ):
        self.target_drawdown = target_drawdown
        self.max_ae = max_adverse_excursion
        self.max_horizon_minutes = max_horizon_minutes

    def compute_all(
        self, db: duckdb.DuckDBPyConnection, input_table: str
    ) -> List[DistributionLabelResult]:
        """
        Compute labels for all rows in the input table using DuckDB window functions.
        The input table must have: symbol, feature_time, open, high, low, close, quality_status.

        Uses window functions with ROWS BETWEEN frame to avoid the O(n^2) self-join.
        With 5m candles, 24h horizon = ~288 rows. We use a frame of 290 FOLLOWING.
        """
        target_dd = float(self.target_drawdown)
        horizon = self.max_horizon_minutes
        gap_threshold = 15  # minutes
        # 5m candles → 288 candles per 24h. Add buffer for edge cases.
        horizon_rows = horizon // 5 + 2  # 290

        # Drop temp tables from prior runs
        for t in ("_dl_wide", "_dl_ae", "_dl_target"):
            for kind in ("VIEW", "TABLE"):
                try:
                    db.execute(f"DROP {kind} {t}")
                except Exception:
                    pass

        # Step 1a: Window functions for simple aggregates (single pass, O(n * horizon_rows)).
        # These don't depend on the signal row's close, so window functions work correctly.
        db.execute(f"""
            CREATE TEMPORARY TABLE _dl_wide AS
            WITH lagged AS (
                SELECT
                    symbol,
                    feature_time,
                    open,
                    high,
                    low,
                    close,
                    quality_status,
                    feature_time - LAG(feature_time) OVER (
                        PARTITION BY symbol ORDER BY feature_time
                    ) AS gap_from_prev
                FROM {input_table}
            )
            SELECT
                symbol,
                feature_time AS signal_time,
                close AS signal_close,
                quality_status AS signal_qs,
                MAX(high) OVER w AS future_max_high,
                MIN(low) OVER w AS future_min_low,
                MAX(1 - low / close) OVER w AS max_fe,
                MAX(high / close - 1) OVER w AS max_ae_any,
                MAX(feature_time) OVER w AS last_future_time,
                COUNT(*) OVER w AS future_count,
                MAX(
                    CASE
                        WHEN gap_from_prev > INTERVAL '{gap_threshold}' MINUTES
                        THEN 1 ELSE 0
                    END
                ) OVER w AS gap_exceeded
            FROM lagged
            WINDOW w AS (
                PARTITION BY symbol
                ORDER BY feature_time
                ROWS BETWEEN 1 FOLLOWING AND {horizon_rows} FOLLOWING
            )
        """)

        # Step 1b: Target detection via filtered self-join.
        # Only joins rows where low <= signal_close * (1 - target_dd),
        # so the intermediate result is much smaller than a full self-join.
        db.execute(f"""
            CREATE TEMPORARY TABLE _dl_target AS
            SELECT
                s.symbol,
                s.feature_time AS signal_time,
                MIN(f.feature_time) AS target_time
            FROM {input_table} s
            INNER JOIN {input_table} f
                ON s.symbol = f.symbol
                AND f.feature_time > s.feature_time
                AND f.feature_time <= s.feature_time + INTERVAL '{horizon}' MINUTES
                AND f.low <= s.close * (1 - {target_dd})
            GROUP BY s.symbol, s.feature_time
        """)

        # Step 2: For rows where target was reached, compute prior_max_ae and ae_at_target.
        # AE = future_high / signal_close - 1 (NOT future_high / future_close - 1).
        # Uses correlated subqueries but only for rows in _dl_target (small subset).
        db.execute(f"""
            CREATE TEMPORARY TABLE _dl_ae AS
            SELECT
                t.symbol,
                t.signal_time,
                (
                    SELECT r.high / s.close - 1
                    FROM {input_table} r
                    INNER JOIN {input_table} s
                        ON s.symbol = t.symbol AND s.feature_time = t.signal_time
                    WHERE r.symbol = t.symbol AND r.feature_time = t.target_time
                ) AS ae_at_target,
                COALESCE(
                    (
                        SELECT MAX(r.high / s.close - 1)
                        FROM {input_table} r
                        CROSS JOIN {input_table} s
                        WHERE s.symbol = t.symbol AND s.feature_time = t.signal_time
                          AND r.symbol = t.symbol
                          AND r.feature_time > t.signal_time
                          AND r.feature_time < t.target_time
                    ),
                    0
                ) AS prior_max_ae
            FROM _dl_target t
        """)

        # Step 3: Join wide + target + ae and build results
        all_rows = db.execute("""
            SELECT
                w.symbol,
                w.signal_time,
                w.signal_close,
                w.signal_qs,
                w.future_max_high,
                w.future_min_low,
                w.max_fe,
                COALESCE(ae.prior_max_ae, 0) AS prior_max_ae,
                w.max_ae_any,
                t.target_time,
                COALESCE(ae.ae_at_target, 0) AS ae_at_target,
                w.gap_exceeded,
                w.last_future_time,
                w.future_count
            FROM _dl_wide w
            LEFT JOIN _dl_target t
                ON w.symbol = t.symbol AND w.signal_time = t.signal_time
            LEFT JOIN _dl_ae ae
                ON w.symbol = ae.symbol AND w.signal_time = ae.signal_time
            ORDER BY w.symbol, w.signal_time
        """).fetchall()

        results = []
        for row in all_rows:
            results.append(self._build_result(row))

        # Cleanup temp tables
        for t in ("_dl_wide", "_dl_target", "_dl_ae"):
            try:
                db.execute(f"DROP TABLE {t}")
            except Exception:
                pass

        return results

    def compute_all_to_table(
        self, db: duckdb.DuckDBPyConnection, input_table: str, output_table: str = "labels"
    ) -> tuple[int, int, int]:
        """
        Compute labels and write them directly to a DuckDB table.
        This avoids the slow Python executemany round-trip for large datasets.

        Returns (n_total, n_positive, n_negative).
        """
        target_dd = float(self.target_drawdown)
        max_ae = float(self.max_ae)
        horizon = self.max_horizon_minutes
        gap_threshold = 15
        horizon_rows = horizon // 5 + 2

        # Drop temp and output tables
        for t in ("_dl_wide", "_dl_ae", "_dl_target", output_table):
            for kind in ("VIEW", "TABLE"):
                try:
                    db.execute(f"DROP {kind} {t}")
                except Exception:
                    pass

        # Step 1a: window functions
        db.execute(f"""
            CREATE TEMPORARY TABLE _dl_wide AS
            WITH lagged AS (
                SELECT symbol, feature_time, open, high, low, close, quality_status,
                    feature_time - LAG(feature_time) OVER (PARTITION BY symbol ORDER BY feature_time) AS gap_from_prev
                FROM {input_table}
            )
            SELECT symbol, feature_time AS signal_time, close AS signal_close, quality_status AS signal_qs,
                MAX(high) OVER w AS future_max_high,
                MIN(low) OVER w AS future_min_low,
                MAX(1 - low / close) OVER w AS max_fe,
                MAX(high / close - 1) OVER w AS max_ae_any,
                MAX(feature_time) OVER w AS last_future_time,
                COUNT(*) OVER w AS future_count,
                MAX(CASE WHEN gap_from_prev > INTERVAL '{gap_threshold}' MINUTES THEN 1 ELSE 0 END) OVER w AS gap_exceeded
            FROM lagged
            WINDOW w AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 1 FOLLOWING AND {horizon_rows} FOLLOWING)
        """)

        # Step 1b: target detection
        db.execute(f"""
            CREATE TEMPORARY TABLE _dl_target AS
            SELECT s.symbol, s.feature_time AS signal_time, MIN(f.feature_time) AS target_time
            FROM {input_table} s
            INNER JOIN {input_table} f
                ON s.symbol = f.symbol
                AND f.feature_time > s.feature_time
                AND f.feature_time <= s.feature_time + INTERVAL '{horizon}' MINUTES
                AND f.low <= s.close * (1 - {target_dd})
            GROUP BY s.symbol, s.feature_time
        """)

        # Step 2: AE computation
        db.execute(f"""
            CREATE TEMPORARY TABLE _dl_ae AS
            SELECT t.symbol, t.signal_time,
                (SELECT r.high / s.close - 1 FROM {input_table} r
                 INNER JOIN {input_table} s ON s.symbol = t.symbol AND s.feature_time = t.signal_time
                 WHERE r.symbol = t.symbol AND r.feature_time = t.target_time) AS ae_at_target,
                COALESCE((SELECT MAX(r.high / s.close - 1) FROM {input_table} r
                 CROSS JOIN {input_table} s
                 WHERE s.symbol = t.symbol AND s.feature_time = t.signal_time
                   AND r.symbol = t.symbol AND r.feature_time > t.signal_time AND r.feature_time < t.target_time), 0) AS prior_max_ae
            FROM _dl_target t
        """)

        # Step 3: Build labels table directly in SQL
        db.execute(f"""
            CREATE TABLE {output_table} AS
            SELECT
                w.symbol,
                w.signal_time,
                CASE
                    -- Excluded: invalid quality
                    WHEN w.signal_qs IN ('invalid', 'quarantined') THEN NULL
                    -- Excluded: no future data
                    WHEN w.future_count IS NULL OR w.future_count = 0 THEN NULL
                    -- Excluded: gap exceeded
                    WHEN COALESCE(w.gap_exceeded, 0) = 1 THEN NULL
                    -- Excluded: didn't reach horizon
                    WHEN w.last_future_time IS NULL
                        OR w.last_future_time < (w.signal_time + INTERVAL '{horizon}' MINUTE) - INTERVAL '5' MINUTE THEN NULL
                    -- Ambiguous: target reached but AE at target candle exceeds max_ae
                    -- while prior AE was within limit
                    WHEN t.target_time IS NOT NULL
                        AND COALESCE(ae.prior_max_ae, 0) <= {max_ae}
                        AND COALESCE(ae.ae_at_target, 0) > {max_ae} THEN NULL
                    -- Positive: target reached and prior AE within limit
                    WHEN t.target_time IS NOT NULL
                        AND COALESCE(ae.prior_max_ae, 0) <= {max_ae} THEN 1
                    -- Negative: everything else
                    ELSE 0
                END AS label_value,
                t.target_time,
                CASE
                    WHEN t.target_time IS NOT NULL
                        THEN CAST(
                            EXTRACT(EPOCH FROM (t.target_time - w.signal_time)) / 60 AS INTEGER
                        )
                    ELSE NULL
                END AS lead_time_minutes,
                -- Invalidation time: signal expires at end of horizon.
                -- After this, an un-materialized positive signal is invalidated.
                w.signal_time + INTERVAL '{horizon}' MINUTE AS invalidation_time
            FROM _dl_wide w
            LEFT JOIN _dl_target t ON w.symbol = t.symbol AND w.signal_time = t.signal_time
            LEFT JOIN _dl_ae ae ON w.symbol = ae.symbol AND w.signal_time = ae.signal_time
        """)

        # Get counts
        counts = db.execute(f"""
            SELECT
                COUNT(*) AS n_total,
                COUNT(CASE WHEN label_value = 1 THEN 1 END) AS n_positive,
                COUNT(CASE WHEN label_value = 0 THEN 1 END) AS n_negative
            FROM {output_table}
        """).fetchone()
        n_total, n_positive, n_negative = counts

        # Cleanup temp tables
        for t in ("_dl_wide", "_dl_target", "_dl_ae"):
            try:
                db.execute(f"DROP TABLE {t}")
            except Exception:
                pass

        return n_total, n_positive, n_negative

    def _build_result(self, row: tuple) -> DistributionLabelResult:
        """Build a DistributionLabelResult from a database row."""
        (
            symbol, signal_time, close, qs,
            future_max_high, future_min_low, max_fe,
            prior_max_ae, max_ae_any, target_time,
            ae_at_target, gap_exceeded, last_future_time, future_count,
        ) = row

        P0 = Decimal(str(close)) if close is not None else None

        def null_result(reason: str) -> DistributionLabelResult:
            return DistributionLabelResult(
                signal_time=signal_time,
                symbol=symbol,
                signal_price=P0 if P0 is not None else Decimal("0"),
                exclusion_reason=reason,
            )

        if qs in ("invalid", "quarantined"):
            return null_result("invalid_signal_quality")

        if P0 is None or P0 <= 0:
            return null_result("invalid_signal_price")

        # No future data at all
        if future_count is None or future_count == 0:
            return null_result("missing_future_data")

        # Determine if we reached the horizon (last future data is near 24h)
        horizon_end = signal_time + timedelta(minutes=self.max_horizon_minutes)
        reached = last_future_time is not None and last_future_time >= horizon_end - timedelta(minutes=5)

        # Check gap
        gap_exc = bool(gap_exceeded) if gap_exceeded is not None else False

        if gap_exc:
            return null_result("gap_exceeds_threshold")
        if not reached:
            return null_result("missing_future_data")

        target_reached = target_time is not None
        max_ae_f = float(self.max_ae)

        prior_ae_val = float(prior_max_ae) if prior_max_ae is not None else 0.0
        ae_at_target_val = float(ae_at_target) if ae_at_target is not None else 0.0

        # recorded_mae: if target reached, use max(prior_max_ae, ae_at_target);
        # otherwise use max_ae_any over entire horizon
        if target_reached:
            recorded_mae = max(prior_ae_val, ae_at_target_val)
        else:
            recorded_mae = float(max_ae_any) if max_ae_any is not None else 0.0

        # Ambiguous: target reached on a candle where AE also exceeds max_ae,
        # but prior AE was within limit (can't determine intrabar order)
        ambiguous = False
        if target_reached:
            if prior_ae_val <= max_ae_f and ae_at_target_val > max_ae_f:
                ambiguous = True

        lead_time_minutes = None
        if target_time is not None:
            lead_time_minutes = int((target_time - signal_time).total_seconds() / 60)

        label_value: Optional[int] = None
        exclusion_reason: Optional[str] = None

        if ambiguous:
            label_value = None
            exclusion_reason = "ambiguous_intrabar"
        else:
            if target_reached and prior_ae_val <= max_ae_f:
                label_value = 1
            else:
                label_value = 0

        return DistributionLabelResult(
            signal_time=signal_time,
            symbol=symbol,
            signal_price=P0,
            label_value=label_value,
            target_reached=target_reached,
            target_time=target_time,
            lead_time_minutes=lead_time_minutes,
            max_adverse_excursion=recorded_mae,
            max_favorable_excursion_24h=float(max_fe) if max_fe is not None else 0.0,
            future_max_high=Decimal(str(future_max_high)) if future_max_high is not None else None,
            future_min_low=Decimal(str(future_min_low)) if future_min_low is not None else None,
            exclusion_reason=exclusion_reason,
        )

    def compute_all_python(
        self, db: duckdb.DuckDBPyConnection, input_table: str
    ) -> List[DistributionLabelResult]:
        """
        Original Python-based O(n^2) implementation.
        Kept for reference and testing. Use compute_all() for production.
        """
        rows = db.query(
            f"SELECT symbol, feature_time, open, high, low, close, quality_status FROM {input_table} ORDER BY symbol, feature_time"
        ).fetchall()

        results = []
        for i in range(len(rows)):
            results.append(self._process_row(rows, i))
        return results

    def _process_row(self, rows: List[RowType], i: int) -> DistributionLabelResult:
        symbol, signal_time, o, h, lo, c, qs = rows[i]
        P0 = Decimal(str(c)) if c is not None else None

        def null_result(reason: str) -> DistributionLabelResult:
            return DistributionLabelResult(
                signal_time=signal_time,
                symbol=symbol,
                signal_price=P0 if P0 is not None else Decimal("0"),
                exclusion_reason=reason,
            )

        if qs in ("invalid", "quarantined"):
            return null_result("invalid_signal_quality")

        if P0 is None or P0 <= 0:
            return null_result("invalid_signal_price")

        target_threshold = float(P0) * float(1 - self.target_drawdown)
        float(P0) * float(1 + self.max_ae)

        horizon_end_time = signal_time + timedelta(minutes=self.max_horizon_minutes)

        target_reached = False
        target_time: Optional[datetime] = None
        max_fe = 0.0
        future_max_high: Optional[float] = None
        future_min_low: Optional[float] = None

        prior_max_ae = 0.0
        final_mae = 0.0
        ambiguous = False
        gap_exceeded = False
        reached_horizon = False

        last_time = signal_time

        for j in range(i + 1, len(rows)):
            sym_j, fj, oj, hj, lj, cj, qsj = rows[j]

            if sym_j != symbol:
                break

            if fj > horizon_end_time:
                reached_horizon = True
                break

            gap_minutes = (fj - last_time).total_seconds() / 60
            if gap_minutes > 15:
                gap_exceeded = True
                break

            last_time = fj

            if future_max_high is None or hj > future_max_high:
                future_max_high = hj
            if future_min_low is None or lj < future_min_low:
                future_min_low = lj

            P0_float = float(P0)
            fe_j = float(1 - float(lj) / P0_float)
            ae_j = float(float(hj) / P0_float - 1)

            if fe_j > max_fe:
                max_fe = fe_j

            if not target_reached:
                if float(lj) <= target_threshold:
                    target_reached = True
                    target_time = fj
                    final_mae = max(prior_max_ae, ae_j)

                    if prior_max_ae <= float(self.max_ae) and ae_j > float(self.max_ae):
                        ambiguous = True
                else:
                    if ae_j > prior_max_ae:
                        prior_max_ae = ae_j

            if fj == horizon_end_time:
                reached_horizon = True
                break

        if not reached_horizon and (last_time < horizon_end_time):
            if gap_exceeded:
                return null_result("gap_exceeds_threshold")
            else:
                return null_result("missing_future_data")

        recorded_mae = final_mae if target_reached else prior_max_ae
        lead_time_minutes = None
        if target_time:
            lead_time_minutes = int((target_time - signal_time).total_seconds() / 60)

        label_value: Optional[int] = None
        exclusion_reason: Optional[str] = None

        if ambiguous:
            label_value = None
            exclusion_reason = "ambiguous_intrabar"
        else:
            if target_reached and prior_max_ae <= float(self.max_ae):
                label_value = 1
            else:
                label_value = 0

        return DistributionLabelResult(
            signal_time=signal_time,
            symbol=symbol,
            signal_price=P0,
            label_value=label_value,
            target_reached=target_reached,
            target_time=target_time,
            lead_time_minutes=lead_time_minutes,
            max_adverse_excursion=recorded_mae,
            max_favorable_excursion_24h=max_fe,
            future_max_high=Decimal(str(future_max_high))
            if future_max_high is not None
            else None,
            future_min_low=Decimal(str(future_min_low))
            if future_min_low is not None
            else None,
            exclusion_reason=exclusion_reason,
        )
