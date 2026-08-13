"""Event-safe validation split utilities.

Rows belonging to a single distribution episode must never be split between
train/validation/calibration/test.  The helper below validates boundaries and
materializes a filtered ``<labels_table>_event_safe`` table for callers that
want a fail-closed dataset.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

import duckdb

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Unsafe DuckDB identifier: {value!r}")
    return value


def _boundary(value: Any) -> tuple[datetime, datetime] | None:
    """Read tuple, mapping or Pydantic ``SplitBounds``-like values."""
    if isinstance(value, Mapping):
        start = value.get("start_time", value.get("start"))
        end = value.get("end_time", value.get("end"))
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        start, end = value
    else:
        start = getattr(value, "start_time", getattr(value, "start", None))
        end = getattr(value, "end_time", getattr(value, "end", None))
    if start is None or end is None:
        return None
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        # DuckDB/pandas timestamps expose ``to_pydatetime``.
        start = start.to_pydatetime() if hasattr(start, "to_pydatetime") else start
        end = end.to_pydatetime() if hasattr(end, "to_pydatetime") else end
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise TypeError("split boundaries must contain datetime values")
    def _utc_naive(timestamp: datetime) -> datetime:
        if timestamp.tzinfo is not None:
            return timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        return timestamp

    return _utc_naive(start), _utc_naive(end)


def _flatten_boundaries(fold_boundaries: Any) -> dict[str, tuple[datetime, datetime]]:
    """Normalize common fold-boundary shapes into ``name -> (start, end)``."""
    if isinstance(fold_boundaries, Mapping):
        # A single fold is represented as {train: ..., validation: ..., test: ...}.
        direct: dict[str, tuple[datetime, datetime]] = {}
        nested: dict[str, Any] = {}
        for name, value in fold_boundaries.items():
            parsed = _boundary(value)
            if parsed is not None:
                direct[str(name)] = parsed
            elif isinstance(value, Mapping):
                nested[str(name)] = value
        if direct:
            return direct
        if nested:
            flattened: dict[str, tuple[datetime, datetime]] = {}
            for fold_name, fold in nested.items():
                for split_name, value in fold.items():
                    parsed = _boundary(value)
                    if parsed is not None:
                        flattened[f"{fold_name}:{split_name}"] = parsed
            return flattened
    if isinstance(fold_boundaries, (list, tuple)):
        flattened = {}
        for index, fold in enumerate(fold_boundaries):
            for name, bounds in _flatten_boundaries(fold).items():
                flattened[f"fold{index}:{name}"] = bounds
        return flattened
    raise TypeError("fold_boundaries must be a mapping or sequence of mappings")


def enforce_event_grouping_in_splits(
    db: duckdb.DuckDBPyConnection,
    labels_table: str,
    fold_boundaries: dict[str, Any] | list[dict[str, Any]],
) -> dict[str, Any]:
    """Validate and materialize event-safe rows.

    Boundaries are half-open ``[start, end)`` intervals.  If one ``event_id``
    has member rows in more than one interval, every row of that event is
    removed from ``<labels_table>_event_safe``.  The source table is never
    modified.  The return value is intentionally JSON-serializable and safe to
    persist in a leakage audit report.
    """
    source = _identifier(labels_table)
    boundaries = _flatten_boundaries(fold_boundaries)
    if not boundaries:
        raise ValueError("at least one non-empty split boundary is required")

    try:
        columns = {
            str(row[0])
            for row in db.execute(f"DESCRIBE {source}").fetchall()
        }
    except Exception:
        columns = set()
    if "event_id" not in columns:
        return {
            "ok": True,
            "violations": [],
            "dropped_event_ids": [],
            "n_dropped": 0,
            "safe_table": None,
            "reason": "labels table has no event_id column",
        }
    time_col = next(
        (name for name in ("signal_time", "feature_time", "timestamp") if name in columns),
        None,
    )
    if time_col is None:
        raise ValueError("labels table requires signal_time/feature_time/timestamp")

    rows = db.execute(
        f"SELECT event_id, {time_col} FROM {source} WHERE event_id IS NOT NULL"
    ).fetchall()
    event_splits: dict[str, set[str]] = {}
    for event_id, timestamp in rows:
        if timestamp is None:
            continue
        if hasattr(timestamp, "to_pydatetime"):
            timestamp = timestamp.to_pydatetime()
        if isinstance(timestamp, datetime) and timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        memberships = {
            name
            for name, (start, end) in boundaries.items()
            if start <= timestamp < end
        }
        # A partially assigned event is unsafe too: an embargo/out-of-range
        # row must not silently disappear while its other members train a
        # model.  Entirely out-of-range events are harmless because callers do
        # not select them into any split.
        if not memberships:
            memberships = {"__unassigned__"}
        event_splits.setdefault(str(event_id), set()).update(memberships)

    violations = [
        {"event_id": event_id, "splits": sorted(splits)}
        for event_id, splits in sorted(event_splits.items())
        if len(splits) > 1
    ]
    dropped = [entry["event_id"] for entry in violations]

    safe_table = _identifier(f"{source}_event_safe")
    for statement in (f"DROP TABLE IF EXISTS {safe_table}", f"DROP VIEW IF EXISTS {safe_table}"):
        try:
            db.execute(statement)
        except Exception:
            pass
    if dropped:
        placeholders = ", ".join("?" for _ in dropped)
        db.execute(
            f"CREATE TABLE {safe_table} AS SELECT * FROM {source} WHERE event_id IS NULL OR event_id NOT IN ({placeholders})",
            dropped,
        )
    else:
        db.execute(f"CREATE TABLE {safe_table} AS SELECT * FROM {source}")

    return {
        "ok": not violations,
        "violations": violations,
        "dropped_event_ids": dropped,
        "n_dropped": len(dropped),
        "safe_table": safe_table,
    }


__all__ = ["enforce_event_grouping_in_splits"]
