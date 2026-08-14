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
from dao_vang.labels.specs.distribution_short_v1 import specs as label_specs
from dao_vang.logging import get_logger
from dao_vang.scanner.scan_results_store import ScanResultStore

logger = get_logger(__name__)


def _normalize_ts(ts: datetime) -> datetime:
    """Strip tzinfo so DuckDB-native (naive) and Python-native (aware)
    timestamps compare equal when both represent the same UTC instant."""
    if ts.tzinfo is not None:
        return ts.astimezone(timezone.utc).replace(tzinfo=None)
    return ts


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

    The label engine is run from the same point-in-time timeline used by
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
    invalid = [h for h in requested if h not in label_specs]
    if not requested or invalid:
        raise ValueError(f"horizons must be a subset of 6/12/24; invalid={invalid}")

    labels_table = "_prediction_outcomes_labels_v1"
    try:
        DistributionLabelEngineV1(label_specs[requested[0]]).compute_all_horizons_to_table(
            db.conn, timeline_table, labels_table, requested
        )
        resolved = 0
        for prediction in pending:
            horizon = int(prediction.get("horizon_hours") or 24)
            if horizon not in requested:
                continue
            signal_time = prediction.get("signal_time")
            # DuckDB stores timestamps without tzinfo; compare UTC-naive values
            # explicitly so a Windows local timezone never shifts a label.
            if isinstance(signal_time, datetime):
                signal_time = _normalize_ts(signal_time)
            row = db.conn.execute(
                f"""
                SELECT label_value, target_time, lead_time_minutes,
                       max_adverse_excursion, max_favorable_excursion,
                       exclusion_reason, label_version
                FROM {labels_table}
                WHERE symbol = ? AND signal_time = ? AND horizon_hours = ?
                LIMIT 1
                """,
                [prediction["symbol"], signal_time, horizon],
            ).fetchone()
            if row is None:
                # No matching row means the snapshot did not contain this
                # signal; leave it pending instead of fabricating an outcome.
                continue
            label_value, target_time, lead, mae, mfe, exclusion, label_version = row
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
            ):
                resolved += 1
        # Event identity is assigned only from materialized positive labels.
        # It is deliberately absent from the live prediction row so future
        # information cannot influence serving-time decisions.
        prediction_store.assign_materialized_event_ids()
        return resolved
    finally:
        try:
            db.conn.execute(f"DROP TABLE IF EXISTS {labels_table}")
        except Exception:
            pass


__all__ = ["materialize_prediction_outcomes", "resolve_pending_outcomes"]
