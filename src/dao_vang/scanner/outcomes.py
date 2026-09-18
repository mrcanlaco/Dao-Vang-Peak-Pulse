"""Outcome resolution — the missing link in the self-learning loop.

`AlertStore.update_hits` was defined to back-fill hit/miss on alerts whose
24h horizon has completed, but nothing in the codebase ever called it —
`hit`/`hit_time` stayed NULL forever and `AlertStore.stats()["hit_rate"]`
was always None. This module closes that loop:

    1. Find alerts past their invalidation_time with hit IS NULL.
    2. Compute the *real* Distribution Label v0.1 for those signal times
       from materialized price data (DistributionLabelEngine — the same
       engine used for offline training, so outcome judging uses the same
       definition of "Distribution" as the model itself).
    3. Write hit/miss back to alert_history via AlertStore.update_hits.

Must run AFTER raw_timeline has been refreshed for the relevant symbols
(the daemon calls this right after `_normalize_and_timeline`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from dao_vang.alerts.store import AlertStore
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.domain.time import system_now
from dao_vang.labels.engine import DistributionLabelEngine
from dao_vang.labels.engine_v1 import DistributionLabelEngineV1
from dao_vang.labels.engine_v2 import DistributionLabelEngineV2
from dao_vang.labels.specs.distribution_short_v1 import specs as v1_label_specs
from dao_vang.labels.specs.distribution_short_v2 import specs as v2_label_specs
from dao_vang.logging import get_logger
from dao_vang.scanner.scan_results_store import ScanResultStore

logger = get_logger(__name__)


def _normalize_ts(ts: datetime) -> datetime:
    """Strip tzinfo so DuckDB-native (naive) and Python-native (aware)
    timestamps compare equal when both represent the same UTC instant."""
    if ts.tzinfo is not None:
        return ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


def _label_contract_key(value: object, fallback: str) -> str:
    """Normalize known aliases while leaving unknown versions fail-closed."""

    normalized = str(value or fallback).strip().lower()
    if normalized in {"v1", "distribution_short_v1"}:
        return "distribution_short_v1"
    if normalized in {"v2", "distribution_short_v2"}:
        return "distribution_short_v2"
    return normalized


def resolve_pending_outcomes(
    alert_store: AlertStore,
    db: DuckDBQueryLayer,
    timeline_table: str = "raw_timeline",
    label_engine: DistributionLabelEngine | None = None,
) -> int:
    """Resolve hit/miss for alerts whose 24h horizon has completed.

    Args:
        alert_store: AlertStore backed by the same DuckDB file as ``db``.
        db: Query layer over the scanner DuckDB (must contain
            ``timeline_table`` with symbol/feature_time/OHLC/quality_status).
        timeline_table: Name of the point-in-time timeline table.
        label_engine: Optional engine override (defaults to Label v0.1).

    Returns:
        Number of alert_history rows updated.
    """
    pending = alert_store.pending_outcomes(as_of=system_now())
    if not pending:
        logger.debug("outcome_resolver_no_pending")
        return 0

    engine = label_engine or DistributionLabelEngine()

    try:
        results = engine.compute_all(db.conn, timeline_table)
    except Exception as exc:
        logger.warning("outcome_resolver_label_compute_failed", error=str(exc))
        return 0

    materialized: dict[tuple[str, datetime], bool] = {}
    for r in results:
        if r.label_value is None:
            continue
        materialized[(r.symbol, _normalize_ts(r.signal_time))] = bool(r.label_value == 1)

    labels_to_update: dict[tuple[str, datetime], bool] = {}
    for p in pending:
        key = (p["symbol"], _normalize_ts(p["signal_time"]))
        if key in materialized:
            # update_hits() matches on the *original* signal_time value
            # stored in alert_history, so use p["signal_time"] as the key.
            labels_to_update[(p["symbol"], p["signal_time"])] = materialized[key]

    if not labels_to_update:
        logger.info(
            "outcome_resolver_no_materialized_labels",
            n_pending=len(pending),
        )
        return 0

    updated = alert_store.update_hits(labels_to_update)
    logger.info(
        "outcome_resolver_updated",
        n_pending=len(pending),
        n_resolved=len(labels_to_update),
        n_rows_updated=updated,
    )
    return updated


def materialize_prediction_outcomes(
    prediction_store: ScanResultStore,
    db: DuckDBQueryLayer,
    *,
    timeline_table: str = "raw_timeline",
    horizons: tuple[int, ...] = (6, 12, 24),
    engine_version: str = "distribution_short_v1",
) -> int:
    """Materialize outcomes for immutable shadow/canary predictions.

    The engine is selected from each prediction's immutable label_version,
    so legacy v1 (8%) and active v2 (20%/24h) rows can coexist safely. The
    label engine is run from the same point-in-time timeline used by
    training.  Rows with invalid quality, gaps or ambiguous intrabar data are
    recorded as ``excluded`` with ``label_value = NULL``; they are never
    silently converted to negatives.  Re-running this function is idempotent
    because ``prediction_outcomes.prediction_id`` is unique.

    No KPI is inferred here.  If a horizon has not actually completed or the
    future data is unavailable, the row remains pending (or is explicitly
    excluded by the label contract) and monitoring can report the backlog.
    """

    pending = prediction_store.pending_predictions()
    if not pending:
        return 0
    requested = tuple(dict.fromkeys(int(h) for h in horizons))
    supported_horizons = set(v1_label_specs) | set(v2_label_specs)
    invalid = [h for h in requested if h not in supported_horizons]
    if not requested or invalid:
        raise ValueError(f"horizons must be a subset of 6/12/24; invalid={invalid}")

    # Live timelines are bounded, while immutable predictions retain all
    # history. A missing signal can never produce a label in this snapshot.
    # Avoid running the expensive metrics query once for every old prediction;
    # leave those rows pending for a historical-data maintenance run.
    source_keys = {(symbol, _normalize_ts(stamp)) for symbol, stamp in db.conn.execute(
        f"SELECT DISTINCT symbol,feature_time FROM {timeline_table} WHERE feature_time IS NOT NULL"
    ).fetchall()}
    pending_count = len(pending)
    pending = [prediction for prediction in pending
               if isinstance(prediction.get("signal_time"), datetime)
               and (prediction["symbol"], _normalize_ts(prediction["signal_time"])) in source_keys]
    logger.info("prediction_outcomes_source_coverage", n_pending=pending_count, n_in_window=len(pending))
    if not pending:
        prediction_store.assign_materialized_event_ids()
        return 0

    label_tables: dict[str, str] = {}
    try:
        pending_versions = {
            _label_contract_key(prediction.get("label_version"), engine_version)
            for prediction in pending
        }
        if "distribution_short_v1" in pending_versions:
            v1_horizons = tuple(h for h in requested if h in v1_label_specs)
            if v1_horizons:
                table = "_prediction_outcomes_labels_v1"
                DistributionLabelEngineV1(v1_label_specs[v1_horizons[0]]).compute_all_horizons_to_table(
                    db.conn, timeline_table, table, v1_horizons
                )
                label_tables["distribution_short_v1"] = table
        if "distribution_short_v2" in pending_versions:
            v2_horizons = tuple(h for h in requested if h in v2_label_specs)
            if not v2_horizons:
                raise ValueError("distribution_short_v2 predictions require the 24h horizon")
            table = "_prediction_outcomes_labels_v2"
            DistributionLabelEngineV2(v2_label_specs[24]).compute_all_horizons_to_table(
                db.conn, timeline_table, table, v2_horizons
            )
            label_tables["distribution_short_v2"] = table

        # The label contract itself decides eligibility. Missing future rows
        # stay pending exactly as before, without calculating unused metrics.
        ready_keys = {version: {(symbol, _normalize_ts(stamp), int(horizon))
            for symbol, stamp, horizon in db.conn.execute(
                f"SELECT symbol,signal_time,horizon_hours FROM {table} "
                "WHERE exclusion_reason IS DISTINCT FROM 'missing_future_data'"
            ).fetchall()} for version, table in label_tables.items()}
        resolved = 0
        for prediction in pending:
            horizon = int(prediction.get("horizon_hours") or 24)
            if horizon not in requested:
                continue
            version = _label_contract_key(
                prediction.get("label_version"), engine_version
            )
            labels_table = label_tables.get(version)
            if labels_table is None:
                logger.warning(
                    "prediction_outcome_unknown_label_contract",
                    prediction_id=prediction.get("prediction_id"),
                    label_version=version,
                )
                continue
            target_drawdown = float(
                prediction.get("target_drawdown")
                or (0.20 if version == "distribution_short_v2" else 0.08)
            )
            signal_time = prediction.get("signal_time")
            # DuckDB stores timestamps without tzinfo; compare UTC-naive values
            # explicitly so a Windows local timezone never shifts a label.
            if isinstance(signal_time, datetime):
                signal_time = _normalize_ts(signal_time)
            if (prediction["symbol"], signal_time, horizon) not in ready_keys[version]:
                continue
            row = db.conn.execute(
                f"""
                WITH f AS (
                    SELECT label_value, target_time, lead_time_minutes,
                           max_adverse_excursion, max_favorable_excursion,
                           exclusion_reason, label_version
                    FROM {labels_table}
                    WHERE symbol = ? AND signal_time = ? AND horizon_hours = ?
                    LIMIT 1
                ), signal_klines AS (
                    SELECT k.close, k.high, k.low, k.feature_time as close_time,
                           (CAST(? AS DOUBLE) - k.low) / CAST(? AS DOUBLE) AS drawdown,
                           (k.high - CAST(? AS DOUBLE)) / CAST(? AS DOUBLE) AS adverse_excursion,
                           extract('epoch' from (k.feature_time - ?)) / 3600.0 AS hours_since
                    FROM {timeline_table} k
                    WHERE k.symbol = ?
                      AND k.feature_time > ?
                      AND k.feature_time <= ? + INTERVAL 24 HOUR
                ), metrics AS (
                    SELECT 
                        MAX(CASE WHEN hours_since <= 6 THEN drawdown ELSE NULL END) AS max_drawdown_6h,
                        MAX(CASE WHEN hours_since <= 12 THEN drawdown ELSE NULL END) AS max_drawdown_12h,
                        MAX(CASE WHEN hours_since <= 24 THEN drawdown ELSE NULL END) AS max_drawdown_24h,
                        MIN(CASE WHEN drawdown >= 0.04 THEN close_time ELSE NULL END) AS first_tp1_hit_time,
                        MIN(CASE WHEN drawdown >= ? THEN close_time ELSE NULL END) AS first_tp2_hit_time
                    FROM signal_klines
                ), before_tp AS (
                    SELECT MAX(adverse_excursion) AS max_adverse_excursion_before_tp
                    FROM signal_klines
                    CROSS JOIN metrics m
                    WHERE (m.first_tp1_hit_time IS NULL OR close_time <= m.first_tp1_hit_time)
                )
                SELECT f.*, m.*, b.max_adverse_excursion_before_tp
                FROM f 
                LEFT JOIN metrics m ON 1=1
                LEFT JOIN before_tp b ON 1=1
                """,
                [
                    prediction["symbol"], signal_time, horizon,
                    prediction.get("signal_price"), prediction.get("signal_price"),
                    prediction.get("signal_price"), prediction.get("signal_price"),
                    signal_time,
                    prediction["symbol"], signal_time, signal_time,
                    target_drawdown,
                ],
            ).fetchone()
            if row is None:
                # No matching row means the snapshot did not contain this
                # signal; leave it pending instead of fabricating an outcome.
                continue
            label_value, target_time, lead, mae, mfe, exclusion, label_version, \
            max_drawdown_6h, max_drawdown_12h, max_drawdown_24h, \
            first_tp1_hit_time, first_tp2_hit_time, max_adverse_excursion_before_tp = row
            
            # A row with an unfinished horizon is not materialized.  The V1
            # contract marks it missing_future_data and it should be retried
            # on the next run if the source is still catching up.
            if exclusion == "missing_future_data":
                continue
            status = "excluded" if label_value is None else "materialized"
            if prediction_store.save_outcome(
                prediction["prediction_id"],
                label_value=int(label_value) if label_value is not None else None,
                target_time=target_time,
                lead_time_minutes=float(lead) if lead is not None else None,
                mae=float(mae) if mae is not None else None,
                mfe=float(mfe) if mfe is not None else None,
                outcome_status=status,
                exclusion_reason=str(exclusion) if exclusion else None,
                outcome_engine_version=str(label_version or engine_version),
                max_drawdown_6h=float(max_drawdown_6h) if max_drawdown_6h is not None else None,
                max_drawdown_12h=float(max_drawdown_12h) if max_drawdown_12h is not None else None,
                max_drawdown_24h=float(max_drawdown_24h) if max_drawdown_24h is not None else None,
                first_tp1_hit_time=first_tp1_hit_time,
                first_tp2_hit_time=first_tp2_hit_time,
                max_adverse_excursion_before_tp=float(max_adverse_excursion_before_tp) if max_adverse_excursion_before_tp is not None else None,
            ):
                resolved += 1
        # Event identity is assigned only from materialized positive labels.
        # It is deliberately absent from the live prediction row so future
        # information cannot influence serving-time decisions.
        prediction_store.assign_materialized_event_ids()
        return resolved
    finally:
        try:
            for labels_table in set(label_tables.values()):
                db.conn.execute(f"DROP TABLE IF EXISTS {labels_table}")
        except Exception:
            pass


__all__ = ["materialize_prediction_outcomes", "resolve_pending_outcomes"]
