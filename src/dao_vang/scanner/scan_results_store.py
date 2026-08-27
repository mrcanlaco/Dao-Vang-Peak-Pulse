"""Scan result store — persists every scored symbol every cycle, not just alerts.

Constitution Khối 6 requires recording *every signal*, not only the ones that
crossed the alert threshold and were sent to Telegram. `alert_history`
(`dao_vang.alerts.store`) only stores symbols that fired an alert; this store
keeps the full per-cycle scan output (including SAFE/WAIT symbols) so the UI
"candidates" list and future analysis reflect what the scanner actually saw,
instead of hardcoded/fabricated data.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import duckdb

from dao_vang.data.storage.duckdb import (
    configure_connection,
    open_read_only_connection,
)
from dao_vang.domain.time import system_now
from dao_vang.logging import get_logger

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scan_results (
    scan_time          TIMESTAMP NOT NULL,
    symbol             VARCHAR NOT NULL,
    score              DOUBLE NOT NULL,
    recommendation     VARCHAR NOT NULL,
    close_price        DOUBLE,
    price_change_24h   DOUBLE,
    oi_change_24h      DOUBLE,
    funding_rate       DOUBLE,
    taker_sell_ratio   DOUBLE,
    volume_24h_usd     DOUBLE,
    pump_pct           DOUBLE,
    pump_days          INTEGER,
    anomaly_score      DOUBLE,
    anomaly_level      VARCHAR,
    anomaly_count      INTEGER,
    anomalies_json     VARCHAR,
    cycle              INTEGER,
    created_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Append-only serving audit.  ``scan_results`` remains the legacy/UI table;
-- ``predictions`` is the immutable contract used by shadow and canary.
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id                 VARCHAR PRIMARY KEY,
    symbol                        VARCHAR NOT NULL,
    signal_time                   TIMESTAMP NOT NULL,
    created_at                    TIMESTAMP NOT NULL,
    horizon_hours                INTEGER NOT NULL,
    target_drawdown              DOUBLE,
    max_adverse_excursion        DOUBLE,
    label_version                VARCHAR,
    heuristic_score              DOUBLE,
    model_probability            DOUBLE,
    calibrated_probability       DOUBLE,
    data_quality_score           DOUBLE,
    quality_status               VARCHAR NOT NULL,
    max_feature_age_minutes      DOUBLE,
    missing_features_json        VARCHAR,
    dataset_version              VARCHAR,
    feature_set_version          VARCHAR,
    model_id                     VARCHAR NOT NULL,
    calibrator_id                VARCHAR,
    threshold_policy_version     VARCHAR,
    candidate_passed             BOOLEAN NOT NULL,
    state                        VARCHAR NOT NULL,
    tier                         VARCHAR NOT NULL,
    threshold                    DOUBLE,
    reason_codes_json            VARCHAR,
    evidence_groups_json         VARCHAR,
    shadow_mode                  BOOLEAN NOT NULL,
    telegram_sent                BOOLEAN NOT NULL DEFAULT FALSE,
    cooldown_key                 VARCHAR,
    invalidation_time            TIMESTAMP,
    snapshot_id                  VARCHAR,
    bundle_checksum              VARCHAR,
    latency_ms                   DOUBLE,
    event_id                     VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_predictions_pending
    ON predictions(invalidation_time, telegram_sent);
CREATE INDEX IF NOT EXISTS idx_predictions_symbol_time
    ON predictions(symbol, signal_time DESC);

CREATE TABLE IF NOT EXISTS prediction_outcomes (
    prediction_id          VARCHAR PRIMARY KEY,
    label_value            INTEGER,
    target_time            TIMESTAMP,
    lead_time_minutes      DOUBLE,
    mae                     DOUBLE,
    mfe                     DOUBLE,
    outcome_status         VARCHAR NOT NULL,
    exclusion_reason       VARCHAR,
    event_id               VARCHAR,
    materialized_at        TIMESTAMP NOT NULL,
    outcome_engine_version VARCHAR NOT NULL,
    FOREIGN KEY (prediction_id) REFERENCES predictions(prediction_id)
);
CREATE INDEX IF NOT EXISTS idx_prediction_outcomes_status
    ON prediction_outcomes(outcome_status, materialized_at);
"""

# Migrations
_MIGRATIONS: list[str] = [
    # DuckDB 1.5 can leave these legacy indexes stale after a fatal writer
    # interruption, causing MAX/ORDER BY scan_time to return old rows while
    # newer rows exist. scan_results is small enough for reliable table scans.
    "DROP INDEX IF EXISTS idx_scan_symbol_time",
    "DROP INDEX IF EXISTS idx_scan_time",
    "ALTER TABLE scan_results ADD COLUMN heuristic_score DOUBLE",
    "ALTER TABLE scan_results ADD COLUMN calibrated_probability DOUBLE",
    "ALTER TABLE scan_results ADD COLUMN data_quality_score DOUBLE",
    "ALTER TABLE scan_results ADD COLUMN horizon_hours INTEGER",
    "ALTER TABLE scan_results ADD COLUMN model_probability DOUBLE",
    "ALTER TABLE scan_results ADD COLUMN anomaly_score DOUBLE",
    "ALTER TABLE scan_results ADD COLUMN anomaly_level VARCHAR",
    "ALTER TABLE scan_results ADD COLUMN anomaly_count INTEGER",
    "ALTER TABLE scan_results ADD COLUMN anomalies_json VARCHAR",
    "ALTER TABLE prediction_outcomes ADD COLUMN event_id VARCHAR",
]



@dataclass
class ScanResultRecord:
    """One symbol's composite score in one scan cycle."""

    scan_time: datetime
    symbol: str
    score: float
    recommendation: str
    model_probability: float | None = None
    heuristic_score: float | None = None
    calibrated_probability: float | None = None
    data_quality_score: float | None = None
    horizon_hours: int | None = None
    anomaly_score: float = 0.0
    anomaly_level: str = "NORMAL"
    anomaly_count: int = 0
    anomalies_json: str = "{}"
    close_price: float | None = None
    price_change_24h: float | None = None
    oi_change_24h: float | None = None
    funding_rate: float | None = None
    taker_sell_ratio: float | None = None
    volume_24h_usd: float | None = None
    pump_pct: float = 0.0
    pump_days: int = 0
    cycle: int = 0


@dataclass(frozen=True)
class PredictionRecord:
    """Immutable prediction contract for shadow/canary serving."""

    symbol: str
    signal_time: datetime
    horizon_hours: int
    model_id: str
    quality_status: str
    candidate_passed: bool
    state: str
    tier: str
    prediction_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created_at: datetime = field(default_factory=system_now)
    target_drawdown: float | None = None
    max_adverse_excursion: float | None = None
    label_version: str | None = None
    heuristic_score: float | None = None
    model_probability: float | None = None
    calibrated_probability: float | None = None
    data_quality_score: float | None = None
    max_feature_age_minutes: float | None = None
    missing_features: tuple[str, ...] = ()
    dataset_version: str | None = None
    feature_set_version: str | None = None
    calibrator_id: str | None = None
    threshold_policy_version: str | None = None
    threshold: float | None = None
    reason_codes: tuple[str, ...] = ()
    evidence_groups: tuple[str, ...] = ()
    shadow_mode: bool = True
    telegram_sent: bool = False
    cooldown_key: str | None = None
    invalidation_time: datetime | None = None
    snapshot_id: str | None = None
    bundle_checksum: str | None = None
    latency_ms: float | None = None
    event_id: str | None = None

    @classmethod
    def stable_id(cls, symbol: str, signal_time: datetime, model_id: str, horizon_hours: int) -> str:
        """Build a deterministic id for replay/live equivalence tests."""

        normalized_time = (
            signal_time.replace(tzinfo=timezone.utc)
            if signal_time.tzinfo is None
            else signal_time.astimezone(timezone.utc)
        )
        raw = f"{symbol}|{normalized_time.isoformat()}|{model_id}|{int(horizon_hours)}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class ScanResultStore:
    """DuckDB-backed store for full per-cycle scan output.

    Args:
        db_path: Path to DuckDB file (shared with AlertStore/feature tables).
    """

    def __init__(
        self,
        db_path: str,
        read_only: bool = False,
        prefer_snapshot: bool = False,
    ) -> None:
        self._db_path = db_path
        self._read_only = read_only
        self._prefer_snapshot = prefer_snapshot
        try:
            if not self._read_only:
                self._init_schema()
        except duckdb.IOException:
            self._read_only = True
        except duckdb.CatalogException:
            self._read_only = True

    def _conn(self) -> duckdb.DuckDBPyConnection:
        if self._read_only:
            return open_read_only_connection(
                self._db_path,
                prefer_snapshot=self._prefer_snapshot,
            )
        conn = duckdb.connect(self._db_path, read_only=self._read_only)
        configure_connection(conn, self._db_path)
        return conn
    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.execute(_SCHEMA)
            for stmt in _MIGRATIONS:
                try:
                    conn.execute(stmt)
                except duckdb.Error:
                    pass

    def save_prediction(self, record: PredictionRecord) -> bool:
        """Persist one immutable prediction; duplicate deterministic ids are ignored."""

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO predictions (
                    prediction_id, symbol, signal_time, created_at, horizon_hours,
                    target_drawdown, max_adverse_excursion, label_version,
                    heuristic_score, model_probability, calibrated_probability,
                    data_quality_score, quality_status, max_feature_age_minutes,
                    missing_features_json, dataset_version, feature_set_version,
                    model_id, calibrator_id, threshold_policy_version,
                    candidate_passed, state, tier, threshold, reason_codes_json,
                    evidence_groups_json, shadow_mode, telegram_sent, cooldown_key,
                    invalidation_time, snapshot_id, bundle_checksum, latency_ms, event_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (prediction_id) DO NOTHING
                """,
                [
                    record.prediction_id,
                    record.symbol,
                    record.signal_time,
                    record.created_at,
                    record.horizon_hours,
                    record.target_drawdown,
                    record.max_adverse_excursion,
                    record.label_version,
                    record.heuristic_score,
                    record.model_probability,
                    record.calibrated_probability,
                    record.data_quality_score,
                    record.quality_status,
                    record.max_feature_age_minutes,
                    json.dumps(list(record.missing_features)),
                    record.dataset_version,
                    record.feature_set_version,
                    record.model_id,
                    record.calibrator_id,
                    record.threshold_policy_version,
                    record.candidate_passed,
                    record.state,
                    record.tier,
                    record.threshold,
                    json.dumps(list(record.reason_codes)),
                    json.dumps(list(record.evidence_groups)),
                    record.shadow_mode,
                    record.telegram_sent,
                    record.cooldown_key,
                    record.invalidation_time,
                    record.snapshot_id,
                    record.bundle_checksum,
                    record.latency_ms,
                    record.event_id,
                ],
            )
            # DuckDB does not expose rowcount consistently across versions;
            # existence is the useful contract for callers.
            return conn.execute(
                "SELECT 1 FROM predictions WHERE prediction_id = ?",
                [record.prediction_id],
            ).fetchone() is not None

    def mark_prediction_telegram_sent(self, prediction_id: str) -> None:
        """Record successful delivery without mutating prediction scores."""

        with self._conn() as conn:
            conn.execute(
                "UPDATE predictions SET telegram_sent = TRUE WHERE prediction_id = ?",
                [prediction_id],
            )

    def is_prediction_telegram_in_cooldown(
        self,
        symbol: str,
        horizon_hours: int | None = None,
        cooldown_minutes: int | None = None,
    ) -> bool:
        """Return whether this symbol received an observation recently."""
        if cooldown_minutes is None:
            # Called as (cooldown_key, cooldown_minutes) where horizon_hours is the cooldown
            actual_cooldown = int(horizon_hours) if horizon_hours is not None else 120
            if ":" in symbol:
                parts = symbol.split(":")
                actual_symbol = parts[0]
                try:
                    actual_horizon = int(parts[1].rstrip("h"))
                except ValueError:
                    actual_horizon = 24
            else:
                actual_symbol = symbol
                actual_horizon = 24
        else:
            if ":" in symbol and horizon_hours is None:
                parts = symbol.split(":")
                actual_symbol = parts[0]
                try:
                    actual_horizon = int(parts[1].rstrip("h"))
                except ValueError:
                    actual_horizon = 24
            else:
                actual_symbol = symbol
                actual_horizon = int(horizon_hours) if horizon_hours is not None else 24
            actual_cooldown = int(cooldown_minutes)

        cutoff = system_now() - timedelta(minutes=max(0, actual_cooldown))
        with self._conn() as conn:
            return conn.execute(
                """
                SELECT 1
                FROM predictions
                WHERE symbol = ?
                  AND horizon_hours = ?
                  AND telegram_sent = TRUE
                  AND created_at >= ?
                LIMIT 1
                """,
                [actual_symbol, actual_horizon, cutoff],
            ).fetchone() is not None

    def get_prediction_telegram_count(
        self,
        symbol: str | None = None,
        hours: int = 24,
    ) -> int:
        """Count successful prediction deliveries in a recent window."""

        cutoff = system_now() - timedelta(hours=max(0, int(hours)))
        where = "created_at >= ? AND telegram_sent = TRUE"
        params: list[Any] = [cutoff]
        if symbol is not None:
            where += " AND symbol = ?"
            params.append(symbol)
        with self._conn() as conn:
            return int(conn.execute(f"SELECT count(*) FROM predictions WHERE {where}", params).fetchone()[0])

    def prediction(self, prediction_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM predictions WHERE prediction_id = ?",
                [prediction_id],
            ).fetchone()
            if row is None:
                return None
            cols = [str(item[0]) for item in conn.execute("DESCRIBE predictions").fetchall()]
        return dict(zip(cols, row))

    def query_predictions(
        self,
        *,
        days: int = 30,
        model_id: str | None = None,
        tier: str | None = None,
        limit: int = 10_000,
    ) -> list[dict[str, Any]]:
        cutoff = system_now() - timedelta(days=max(0, days))
        conditions = ["signal_time >= ?"]
        params: list[Any] = [cutoff]
        if model_id:
            conditions.append("model_id = ?")
            params.append(model_id)
        if tier:
            conditions.append("tier = ?")
            params.append(tier)
        params.append(limit)
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT * FROM predictions WHERE {' AND '.join(conditions)} "
                "ORDER BY signal_time DESC LIMIT ?",
                params,
            ).fetchall()
            cols = [str(item[0]) for item in conn.execute("DESCRIBE predictions").fetchall()]
        return [dict(zip(cols, row)) for row in rows]

    def pending_predictions(self, as_of: datetime | None = None) -> list[dict[str, Any]]:
        """Predictions whose horizon ended and have no outcome row."""

        cutoff = as_of or system_now()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT p.* FROM predictions p
                LEFT JOIN prediction_outcomes o ON o.prediction_id = p.prediction_id
                WHERE p.invalidation_time IS NOT NULL
                  AND p.invalidation_time <= ?
                  AND o.prediction_id IS NULL
                ORDER BY p.invalidation_time
                """,
                [cutoff],
            ).fetchall()
            cols = [str(item[0]) for item in conn.execute("DESCRIBE predictions").fetchall()]
        return [dict(zip(cols, row)) for row in rows]

    def save_outcome(
        self,
        prediction_id: str,
        *,
        label_value: int | None,
        target_time: datetime | None,
        lead_time_minutes: float | None,
        mae: float | None,
        mfe: float | None,
        outcome_status: str,
        exclusion_reason: str | None,
        outcome_engine_version: str,
        materialized_at: datetime | None = None,
    ) -> bool:
        """Insert one immutable outcome; repeated materialization is idempotent."""

        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO prediction_outcomes (
                    prediction_id, label_value, target_time, lead_time_minutes,
                    mae, mfe, outcome_status, exclusion_reason, materialized_at,
                    outcome_engine_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (prediction_id) DO NOTHING
                """,
                [
                    prediction_id,
                    label_value,
                    target_time,
                    lead_time_minutes,
                    mae,
                    mfe,
                    outcome_status,
                    exclusion_reason,
                    materialized_at or system_now(),
                    outcome_engine_version,
                ],
            )
            return conn.execute(
                "SELECT 1 FROM prediction_outcomes WHERE prediction_id = ?",
                [prediction_id],
            ).fetchone() is not None

    def assign_materialized_event_ids(self, *, gap_minutes: int = 60) -> int:
        """Assign stable event IDs to positive materialized outcomes.

        Event identity is intentionally derived only after the future label is
        known.  This keeps the live prediction append-only and prevents the
        serving path from using future information.  Predictions that are
        negative, excluded, or not yet materialized retain a NULL event ID and
        are not silently counted as positive events.
        """

        gap = max(1, int(gap_minutes))
        with self._conn() as conn:
            try:
                conn.execute("ALTER TABLE prediction_outcomes ADD COLUMN event_id VARCHAR")
            except duckdb.Error:
                pass
            conn.execute(
                f"""
                WITH positive_rows AS (
                    SELECT
                        p.prediction_id,
                        p.symbol,
                        p.signal_time,
                        p.horizon_hours,
                        p.model_id,
                        LAG(p.signal_time) OVER (
                            PARTITION BY p.model_id, p.horizon_hours, p.symbol
                            ORDER BY p.signal_time, p.prediction_id
                        ) AS previous_signal_time
                    FROM predictions p
                    INNER JOIN prediction_outcomes o
                        ON o.prediction_id = p.prediction_id
                    WHERE o.label_value = 1
                ), flagged AS (
                    SELECT *, CASE
                        WHEN previous_signal_time IS NULL THEN 1
                        WHEN EXTRACT(EPOCH FROM (signal_time - previous_signal_time)) / 60.0 >= {gap}
                            THEN 1
                        ELSE 0
                    END AS is_new_event
                    FROM positive_rows
                ), numbered AS (
                    SELECT *, SUM(is_new_event) OVER (
                        PARTITION BY model_id, horizon_hours, symbol
                        ORDER BY signal_time, prediction_id
                    ) AS event_sequence
                    FROM flagged
                ), event_groups AS (
                    SELECT
                        symbol,
                        horizon_hours,
                        model_id,
                        event_sequence,
                        MIN(signal_time) AS event_start
                    FROM numbered
                    GROUP BY symbol, horizon_hours, model_id, event_sequence
                ), event_map AS (
                    SELECT
                        n.prediction_id,
                        n.symbol || '_' || CAST(EXTRACT(EPOCH FROM g.event_start) AS BIGINT)
                            || '_' || CAST(n.horizon_hours AS VARCHAR) AS event_id
                    FROM numbered n
                    INNER JOIN event_groups g
                        ON g.symbol = n.symbol
                       AND g.horizon_hours = n.horizon_hours
                       AND g.model_id = n.model_id
                       AND g.event_sequence = n.event_sequence
                )
                UPDATE prediction_outcomes AS o
                SET event_id = e.event_id
                FROM event_map AS e
                WHERE o.prediction_id = e.prediction_id
                """
            )
            return int(
                conn.execute(
                    "SELECT count(*) FROM prediction_outcomes WHERE event_id IS NOT NULL"
                ).fetchone()[0]
            )

    def materialization_stats(self, as_of: datetime | None = None) -> dict[str, Any]:
        pending = self.pending_predictions(as_of=as_of)
        with self._conn() as conn:
            total = int(conn.execute("SELECT count(*) FROM predictions").fetchone()[0])
            resolved = int(conn.execute("SELECT count(*) FROM prediction_outcomes").fetchone()[0])
            excluded = int(
                conn.execute(
                    "SELECT count(*) FROM prediction_outcomes WHERE label_value IS NULL"
                ).fetchone()[0]
            )
        return {
            "predictions": total,
            "outcomes": resolved,
            "pending": len(pending),
            "excluded": excluded,
            "status": "ok" if not pending else "backlog",
        }


    def save_batch(
        self,
        records: list[ScanResultRecord],
        conn: duckdb.DuckDBPyConnection | None = None,
    ) -> None:
        """Insert a batch of scan results (one cycle's worth)."""
        if not records:
            return

        def insert_rows(target: duckdb.DuckDBPyConnection) -> None:
            target.executemany(
                """
                INSERT INTO scan_results (
                    scan_time, symbol, score, recommendation, close_price,
                    price_change_24h, oi_change_24h, funding_rate,
                    taker_sell_ratio, volume_24h_usd, pump_pct, pump_days,
                    anomaly_score, anomaly_level, anomaly_count, anomalies_json,
                    cycle, model_probability, heuristic_score,
                    calibrated_probability, data_quality_score, horizon_hours
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    [
                        r.scan_time,
                        r.symbol,
                        r.score,
                        r.recommendation,
                        r.close_price,
                        r.price_change_24h,
                        r.oi_change_24h,
                        r.funding_rate,
                        r.taker_sell_ratio,
                        r.volume_24h_usd,
                        r.pump_pct,
                        r.pump_days,
                        r.anomaly_score,
                        r.anomaly_level,
                        r.anomaly_count,
                        r.anomalies_json,
                        r.cycle,
                        r.model_probability,
                        r.heuristic_score,
                        r.calibrated_probability,
                        r.data_quality_score,
                        r.horizon_hours,
                    ]
                    for r in records
                ],
            )

        # The scanner already owns a writer connection for the active cycle.
        # Reusing it keeps scan_results visible to the same cycle snapshot and
        # avoids opening a second DuckDB writer for every scored symbol.
        if conn is not None:
            insert_rows(conn)
            return

        with self._conn() as owned_conn:
            insert_rows(owned_conn)

    def latest_per_symbol(
        self,
        limit: int = 200,
        max_age_hours: int | None = 6,
    ) -> list[dict[str, Any]]:
        """Most recent score for each symbol, newest cycle only.

        Only returns symbols scanned within ``max_age_hours`` so stale rows
        from a scanner that has been down do not silently linger in the UI.
        Pass ``None`` only for an explicit last-known-data fallback where the
        caller labels the returned rows as stale.
        """
        cutoff = (
            system_now() - timedelta(hours=max_age_hours)
            if max_age_hours is not None
            else None
        )
        time_filter = "WHERE scan_time >= ?" if cutoff is not None else ""
        params: list[Any] = [cutoff, limit] if cutoff is not None else [limit]
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT symbol, scan_time, score, recommendation, close_price,
                       price_change_24h, oi_change_24h, funding_rate,
                       taker_sell_ratio, volume_24h_usd, pump_pct, pump_days,
                       anomaly_score, anomaly_level, anomaly_count, anomalies_json,
                       model_probability, heuristic_score, calibrated_probability,
                       data_quality_score, horizon_hours

                FROM (
                    SELECT *,
                        ROW_NUMBER() OVER (
                            PARTITION BY symbol ORDER BY rowid DESC
                        ) AS rn
                    FROM scan_results
                    {time_filter}
                )
                WHERE rn = 1
                ORDER BY score DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            cols = [
                "symbol",
                "scan_time",
                "score",
                "recommendation",
                "close_price",
                "price_change_24h",
                "oi_change_24h",
                "funding_rate",
                "taker_sell_ratio",
                "volume_24h_usd",
                "pump_pct",
                "pump_days",
                "anomaly_score",
                "anomaly_level",
                "anomaly_count",
                "anomalies_json",
                "model_probability",
                "heuristic_score",
                "calibrated_probability",
                "data_quality_score",
                "horizon_hours",

            ]
        return [dict(zip(cols, r)) for r in rows]

    def latest_predictions_per_symbol(
        self,
        limit: int = 200,
        max_age_hours: int | None = 24,
    ) -> list[dict[str, Any]]:
        """Return the latest serving prediction for each recently observed coin.

        ``predictions`` is the append-only audit path used by shadow mode.  It
        records whether the Telegram delivery succeeded, while ``scan_results``
        intentionally does not.  The web Radar needs this view so an
        observation sent from shadow mode is visible even when the coin already
        has an older row in ``alert_history``.
        """
        cutoff = (
            system_now() - timedelta(hours=max_age_hours)
            if max_age_hours is not None
            else None
        )
        time_filter = "WHERE created_at >= ?" if cutoff is not None else ""
        params: list[Any] = [cutoff, limit] if cutoff is not None else [limit]
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT prediction_id, symbol, signal_time, created_at,
                       horizon_hours, target_drawdown, calibrated_probability,
                       model_probability, data_quality_score, quality_status,
                       tier, threshold, shadow_mode, telegram_sent,
                       invalidation_time
                FROM (
                    SELECT *,
                        ROW_NUMBER() OVER (
                            PARTITION BY symbol
                            ORDER BY created_at DESC, signal_time DESC, prediction_id DESC
                        ) AS rn
                    FROM predictions
                    {time_filter}
                )
                WHERE rn = 1
                ORDER BY created_at DESC, signal_time DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            cols = [
                "prediction_id",
                "symbol",
                "signal_time",
                "created_at",
                "horizon_hours",
                "target_drawdown",
                "calibrated_probability",
                "model_probability",
                "data_quality_score",
                "quality_status",
                "tier",
                "threshold",
                "shadow_mode",
                "telegram_sent",
                "invalidation_time",
            ]
        return [dict(zip(cols, r)) for r in rows]

    def latest_for_symbol(self, symbol: str, max_age_hours: int = 24) -> dict[str, Any] | None:
        """Most recent scan result for a single symbol."""
        cutoff = system_now() - timedelta(hours=max_age_hours)
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT symbol, scan_time, score, recommendation, close_price,
                       price_change_24h, oi_change_24h, funding_rate,
                       taker_sell_ratio, volume_24h_usd, pump_pct, pump_days,
                       anomaly_score, anomaly_level, anomaly_count, anomalies_json,
                       model_probability, heuristic_score, calibrated_probability,
                       data_quality_score, horizon_hours

                FROM scan_results
                WHERE symbol = ? AND scan_time >= ?
                ORDER BY rowid DESC
                LIMIT 1
                """,
                [symbol, cutoff],
            ).fetchone()
        if not row:
            return None
        cols = [
            "symbol",
            "scan_time",
            "score",
            "recommendation",
            "close_price",
            "price_change_24h",
            "oi_change_24h",
            "funding_rate",
                "taker_sell_ratio",
                "volume_24h_usd",
                "pump_pct",
                "pump_days",
                "anomaly_score",
                "anomaly_level",
                "anomaly_count",
                "anomalies_json",
                "model_probability",
                "heuristic_score",
                "calibrated_probability",
                "data_quality_score",
                "horizon_hours",

        ]
        return dict(zip(cols, row))

    def latest_cycle_stats(self) -> dict[str, Any]:
        """Summary of the most recent scan cycle for telemetry."""
        with self._conn() as conn:
            # ``cycle`` resets when the daemon restarts. Count the contiguous
            # append-only tail instead of every historical row with the same
            # number, otherwise a fresh cycle=1 is reported as hundreds of
            # symbols from older daemon runs.
            rows = conn.execute(
                """
                SELECT scan_time, cycle, recommendation
                FROM scan_results
                ORDER BY rowid DESC
                LIMIT 1000
                """
            ).fetchall()
            last_scan_time, last_cycle = (
                (rows[0][0], rows[0][1]) if rows else (None, None)
            )
            if last_cycle is None:
                return {"last_scan_time": None, "cycle": None, "n_symbols": 0, "n_alerts": 0}
            current_cycle_rows = []
            for item in rows:
                if item[1] != last_cycle:
                    break
                current_cycle_rows.append(item)
        return {
            "last_scan_time": last_scan_time,
            "cycle": last_cycle,
            "n_symbols": len(current_cycle_rows),
            "n_alerts": sum(
                1 for item in current_cycle_rows
                if item[2] == "SHORT_CANDIDATE"
            ),
        }
