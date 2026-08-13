"""Record an unattended health trace for the live scanner and web API.

This monitor is intentionally read-only.  It does not restart processes, send
alerts, or write to DuckDB; it appends one JSON object per observation so the
next session can measure gaps and failures instead of relying on a screenshot.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb

from dao_vang.domain.time import as_system_timezone, system_now


def utc_now() -> datetime:
    # Kept for compatibility with the monitor's existing call sites; the
    # monitor's wall-clock records are intentionally emitted in UTC+7.
    return system_now()


def iso_now() -> str:
    return utc_now().isoformat()


def parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # DuckDB TIMESTAMP columns are stored as UTC-naive values.  Never use
        # the host machine timezone when interpreting them.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, ValueError) as exc:
        return None, f"read_error:{exc}"
    if not isinstance(payload, dict):
        return None, "not_an_object"
    return payload, None


def fetch_status(url: str) -> tuple[dict[str, Any] | None, str | None]:
    request = urllib.request.Request(
        url, headers={"User-Agent": "dao-vang-live-monitor/1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        return None, f"api_error:{exc}"
    if not isinstance(payload, dict):
        return None, "api_response_not_an_object"
    return payload, None


def read_db_snapshot(db_path: Path) -> tuple[dict[str, Any] | None, str | None]:
    connection = None
    temporary_copy: Path | None = None
    try:
        try:
            connection = duckdb.connect(str(db_path), read_only=True)
        except duckdb.Error as direct_error:
            # Windows may hold an exclusive DuckDB file lock during a write.
            # Read a private snapshot instead of treating that normal write
            # window as a scanner failure.
            if not db_path.exists():
                raise direct_error
            fd, temporary_name = tempfile.mkstemp(
                prefix="dao_vang_monitor_", suffix=".duckdb", dir=db_path.parent
            )
            os.close(fd)
            temporary_copy = Path(temporary_name)
            shutil.copy2(db_path, temporary_copy)
            connection = duckdb.connect(str(temporary_copy), read_only=True)
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
        result: dict[str, Any] = {"tables": len(tables)}
        if "scan_results" in tables:
            count, latest = connection.execute(
                "SELECT count(*), max(scan_time) FROM scan_results"
            ).fetchone()
            result["scan_rows"] = int(count or 0)
            result["latest_scan_time"] = latest.isoformat() if latest else None
        if "alert_history" in tables:
            count, latest = connection.execute(
                "SELECT count(*), max(signal_time) FROM alert_history"
            ).fetchone()
            result["alert_rows"] = int(count or 0)
            result["latest_alert_time"] = latest.isoformat() if latest else None
        return result, None
    except (OSError, duckdb.Error) as exc:
        return None, f"db_error:{exc}"
    finally:
        if connection is not None:
            connection.close()
        if temporary_copy is not None:
            try:
                temporary_copy.unlink(missing_ok=True)
            except OSError:
                pass


def file_snapshot(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"exists": False}
    return {
        "exists": True,
        "bytes": stat.st_size,
        "modified_at": as_system_timezone(
            datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        ).isoformat(),
    }


def collect_sample(args: argparse.Namespace, started_at: float) -> dict[str, Any]:
    observed_at = utc_now()
    record: dict[str, Any] = {
        "type": "sample",
        "observed_at": observed_at.isoformat(),
        "elapsed_seconds": round(time.monotonic() - started_at, 1),
        "checks": {},
    }

    heartbeat, heartbeat_error = read_json(args.heartbeat_path)
    heartbeat_check: dict[str, Any] = {"path": str(args.heartbeat_path)}
    if heartbeat is not None:
        heartbeat_time = parse_timestamp(heartbeat.get("timestamp"))
        heartbeat_age = (
            (observed_at - heartbeat_time).total_seconds() if heartbeat_time else None
        )
        heartbeat_check.update(
            {
                "status": heartbeat.get("status"),
                "cycle": heartbeat.get("cycle"),
                "pid": heartbeat.get("pid"),
                "run_id": heartbeat.get("run_id"),
                "last_cycle_status": heartbeat.get("last_cycle_status"),
                "last_cycle_completed_at": heartbeat.get("last_cycle_completed_at"),
                "age_seconds": (
                    round(heartbeat_age, 1) if heartbeat_age is not None else None
                ),
            }
        )
        heartbeat_ok = (
            heartbeat.get("status") == "running"
            and heartbeat_age is not None
            and heartbeat_age <= args.max_heartbeat_age_minutes * 60
        )
    else:
        heartbeat_ok = False
    heartbeat_check["ok"] = heartbeat_ok
    if heartbeat_error:
        heartbeat_check["error"] = heartbeat_error
    record["checks"]["heartbeat"] = heartbeat_check

    api_status, api_error = fetch_status(args.api_url)
    api_check: dict[str, Any] = {"url": args.api_url, "ok": api_status is not None}
    if api_status is not None:
        api_check.update(
            {
                "scanner_status": api_status.get("scanner_status"),
                "heartbeat": api_status.get("heartbeat"),
                "scanned_coins_count": api_status.get("scanned_coins_count"),
                "telegram_connected": api_status.get("telegram_connected"),
                "db_read_status": api_status.get("db_read_status"),
            }
        )
        api_check["ok"] = api_status.get("scanner_status") == "ONLINE"
    if api_error:
        api_check["error"] = api_error
    record["checks"]["api"] = api_check

    db_snapshot, db_error = read_db_snapshot(args.db_path)
    db_check: dict[str, Any] = {
        "path": str(args.db_path),
        "ok": db_snapshot is not None,
    }
    if db_snapshot is not None:
        db_check.update(db_snapshot)
        latest_scan = parse_timestamp(db_snapshot.get("latest_scan_time"))
        scan_age = (observed_at - latest_scan).total_seconds() if latest_scan else None
        db_check["latest_scan_age_seconds"] = (
            round(scan_age, 1) if scan_age is not None else None
        )
        db_check["ok"] = (
            latest_scan is not None and scan_age <= args.max_scan_age_minutes * 60
        )
    if db_error:
        db_check["error"] = db_error
    db_error_text = str(db_check.get("error", "")).lower()
    db_check["transient_lock"] = "used by another process" in db_error_text
    record["checks"]["db"] = db_check

    record["files"] = {
        "scanner_log": file_snapshot(args.scanner_log_path),
        "web_log": file_snapshot(args.web_log_path),
    }
    # A live DuckDB writer can briefly block a second Windows process.  The
    # API/heartbeat fallback makes this a degraded read window, not a scanner
    # outage; keep it visible in the DB check without creating a false alarm.
    db_acceptable = db_check.get("ok") or db_check.get("transient_lock")
    record["healthy"] = bool(
        record["checks"]["heartbeat"].get("ok")
        and record["checks"]["api"].get("ok")
        and db_acceptable
    )
    return record


def append_json(log_handle: Any, record: dict[str, Any]) -> None:
    log_handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    log_handle.flush()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hours", type=float, default=8.0)
    parser.add_argument("--interval-seconds", type=int, default=300)
    parser.add_argument("--api-url", default="http://127.0.0.1:8001/api/status")
    parser.add_argument(
        "--heartbeat-path",
        type=Path,
        default=Path("data_live/scanner_heartbeat.json"),
    )
    parser.add_argument("--db-path", type=Path, default=Path("data_live/live.duckdb"))
    parser.add_argument(
        "--scanner-log-path",
        type=Path,
        default=Path("scripts/logs/scanner_live.log"),
    )
    parser.add_argument(
        "--web-log-path", type=Path, default=Path("scripts/logs/web_live.log")
    )
    parser.add_argument(
        "--log-path",
        type=Path,
        default=Path("scripts/logs/live_8h_monitor.jsonl"),
    )
    parser.add_argument("--max-heartbeat-age-minutes", type=float, default=15.0)
    parser.add_argument("--max-scan-age-minutes", type=float, default=15.0)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.hours <= 0 or args.interval_seconds <= 0:
        raise SystemExit("--hours and --interval-seconds must be positive")

    args.log_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()
    deadline = started_at + args.hours * 3600
    samples = 0
    unhealthy_samples = 0
    max_heartbeat_age = 0.0
    max_scan_age = 0.0

    with args.log_path.open("a", encoding="utf-8", buffering=1) as log_handle:
        append_json(
            log_handle,
            {
                "type": "monitor_started",
                "started_at": iso_now(),
                "monitor_pid": os.getpid(),
                "duration_hours": args.hours,
                "interval_seconds": args.interval_seconds,
                "api_url": args.api_url,
                "heartbeat_path": str(args.heartbeat_path),
                "db_path": str(args.db_path),
            },
        )
        try:
            while time.monotonic() < deadline:
                record = collect_sample(args, started_at)
                samples += 1
                unhealthy_samples += int(not record["healthy"])
                heartbeat_age = record["checks"]["heartbeat"].get("age_seconds")
                scan_age = record["checks"]["db"].get("latest_scan_age_seconds")
                if isinstance(heartbeat_age, (int, float)):
                    max_heartbeat_age = max(max_heartbeat_age, heartbeat_age)
                if isinstance(scan_age, (int, float)):
                    max_scan_age = max(max_scan_age, scan_age)
                append_json(log_handle, record)
                remaining = deadline - time.monotonic()
                if remaining > 0:
                    time.sleep(min(args.interval_seconds, remaining))
        except KeyboardInterrupt:
            append_json(log_handle, {"type": "monitor_interrupted", "at": iso_now()})
            return 130

        append_json(
            log_handle,
            {
                "type": "monitor_finished",
                "finished_at": iso_now(),
                "samples": samples,
                "unhealthy_samples": unhealthy_samples,
                "max_heartbeat_age_seconds": round(max_heartbeat_age, 1),
                "max_scan_age_seconds": round(max_scan_age, 1),
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
