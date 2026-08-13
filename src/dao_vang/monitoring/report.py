"""Evidence-backed operational monitoring for shadow and canary windows."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import duckdb

from dao_vang.domain.time import system_now
from dao_vang.scanner.operations import (
    KillSwitch,
    build_health_snapshot,
    compute_prediction_drift,
)


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * q))))
    return float(ordered[index])


def collect_operational_metrics(
    db_path: str | Path,
    *,
    heartbeat_path: str | Path | None = None,
    kill_switch_path: str | Path | None = None,
    mode: str = "shadow",
    window_hours: int = 24,
    max_heartbeat_age_minutes: int = 15,
) -> dict[str, Any]:
    """Read operational counters without inventing unavailable outcomes."""

    now = system_now()
    cutoff = now - timedelta(hours=max(1, int(window_hours)))
    result: dict[str, Any] = {
        "generated_at": now.isoformat(),
        "window_hours": int(window_hours),
        "mode": mode,
        "evidence_status": "complete",
        "predictions": 0,
        "outcomes": 0,
        "materialized_events": None,
        "pending_outcomes": None,
        "quality_status_counts": {},
        "tier_counts": {},
        "latency_ms": {"p50": None, "p95": None, "n": 0},
    }
    try:
        conn = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        result["evidence_status"] = "unavailable"
        result["error"] = str(exc)
        result["health"] = asdict_health(
            build_health_snapshot(
                mode=mode,
                heartbeat_path=heartbeat_path,
                pending_outcomes=None,
                kill_switch=KillSwitch(kill_switch_path) if kill_switch_path else None,
                bundle_valid=False,
                max_heartbeat_age_minutes=max_heartbeat_age_minutes,
            )
        )
        return result

    try:
        try:
            rows = conn.execute(
                "SELECT quality_status, tier, latency_ms FROM predictions WHERE signal_time >= ?",
                [cutoff],
            ).fetchall()
            latency = [float(row[2]) for row in rows if row[2] is not None]
            result["predictions"] = len(rows)
            result["quality_status_counts"] = _counts(row[0] for row in rows)
            result["tier_counts"] = _counts(row[1] for row in rows)
            result["latency_ms"] = {
                "p50": _percentile(latency, 0.50),
                "p95": _percentile(latency, 0.95),
                "n": len(latency),
            }
            result["outcomes"] = int(
                conn.execute(
                    "SELECT count(*) FROM prediction_outcomes "
                    "WHERE materialized_at >= ?",
                    [cutoff],
                ).fetchone()[0]
            )
            try:
                result["materialized_events"] = int(
                    conn.execute(
                        "SELECT count(DISTINCT event_id) FROM prediction_outcomes "
                        "WHERE event_id IS NOT NULL AND label_value = 1"
                    ).fetchone()[0]
                )
            except Exception:
                # Older databases predate the event_id migration.  Keep the
                # metric unavailable instead of treating missing IDs as zero.
                result["materialized_events"] = None
            result["pending_outcomes"] = int(
                conn.execute(
                    """
                    SELECT count(*) FROM predictions p
                    LEFT JOIN prediction_outcomes o ON o.prediction_id = p.prediction_id
                    WHERE p.invalidation_time IS NOT NULL
                      AND p.invalidation_time <= ? AND o.prediction_id IS NULL
                    """,
                    [now],
                ).fetchone()[0]
            )
        except Exception as exc:
            result["evidence_status"] = "partial"
            result["error"] = str(exc)
    finally:
        conn.close()

    health = build_health_snapshot(
        mode=mode,
        heartbeat_path=heartbeat_path,
        pending_outcomes=result.get("pending_outcomes"),
        kill_switch=KillSwitch(kill_switch_path) if kill_switch_path else None,
        bundle_valid=True,
        max_heartbeat_age_minutes=max_heartbeat_age_minutes,
    )
    result["health"] = asdict_health(health)
    return result


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value) if value is not None else "NULL"
        counts[key] = counts.get(key, 0) + 1
    return counts


def asdict_health(value: Any) -> dict[str, Any]:
    return {
        "status": value.status,
        "checked_at": value.checked_at,
        "mode": value.mode,
        "heartbeat_age_minutes": value.heartbeat_age_minutes,
        "pending_outcomes": value.pending_outcomes,
        "kill_switch_active": value.kill_switch_active,
        "bundle_valid": value.bundle_valid,
        "reasons": list(value.reasons),
        "details": value.details,
    }


def prediction_drift_report(
    reference: list[float],
    current: list[float],
    *,
    min_samples: int = 30,
    psi_warning: float = 0.10,
    psi_critical: float = 0.25,
) -> dict[str, Any]:
    """Serialize drift status; insufficient samples are explicit."""

    drift = compute_prediction_drift(
        reference,
        current,
        min_samples=min_samples,
        psi_warning=psi_warning,
        psi_critical=psi_critical,
    )
    return {
        "status": drift.status,
        "psi": drift.psi,
        "mean_delta": drift.mean_delta,
        "n_reference": drift.n_reference,
        "n_current": drift.n_current,
        "reasons": list(drift.reasons),
    }


def write_daily_report(
    db_path: str | Path,
    output_dir: str | Path,
    *,
    heartbeat_path: str | Path | None = None,
    kill_switch_path: str | Path | None = None,
    mode: str = "shadow",
    window_hours: int = 24,
    max_heartbeat_age_minutes: int = 15,
) -> Path:
    """Write JSON and Markdown artifacts for an operations review."""

    metrics = collect_operational_metrics(
        db_path,
        heartbeat_path=heartbeat_path,
        kill_switch_path=kill_switch_path,
        mode=mode,
        window_hours=window_hours,
        max_heartbeat_age_minutes=max_heartbeat_age_minutes,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    stamp = system_now().strftime("%Y%m%dT%H%M%S+0700")
    json_path = output / f"monitoring_{stamp}.json"
    md_path = output / f"monitoring_{stamp}.md"
    json_path.write_text(json.dumps(metrics, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    lines = [
        f"# Operations monitoring ({metrics['generated_at']})",
        "",
        f"- Evidence status: **{metrics['evidence_status']}**",
        f"- Mode: `{metrics['mode']}`",
        f"- Predictions: {metrics['predictions']}",
        f"- Outcomes materialized: {metrics['outcomes']}",
        f"- Materialized positive events: {metrics['materialized_events']}",
        f"- Pending outcomes: {metrics['pending_outcomes']}",
        f"- Health: **{metrics['health']['status']}**",
        f"- Health reasons: {', '.join(metrics['health']['reasons']) or 'none'}",
        "",
        "## Quality status counts",
        "",
    ]
    for key, value in metrics["quality_status_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Tier counts", ""])
    for key, value in metrics["tier_counts"].items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(
        [
            "",
            "## Latency (ms)",
            "",
            f"- P50: {metrics['latency_ms']['p50']}",
            f"- P95: {metrics['latency_ms']['p95']}",
            "",
            "No precision/recall/KPI is claimed here; outcomes are reported only when materialized.",
        ]
    )
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return md_path


__all__ = ["collect_operational_metrics", "prediction_drift_report", "write_daily_report"]
