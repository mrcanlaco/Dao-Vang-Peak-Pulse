"""Scanner liveness checks shared by Docker, the API, and monitors."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def inspect_heartbeat(
    path: Path,
    *,
    now: datetime | None = None,
    max_age_seconds: float = 900,
) -> dict[str, Any]:
    """Return a safe, structured scanner-health decision.

    The result deliberately excludes process IDs, paths, and exception text so
    it can be exposed by the unauthenticated readiness endpoint.
    """

    result: dict[str, Any] = {
        "healthy": False,
        "reason": "heartbeat_invalid",
        "age_seconds": None,
        "heartbeat_time": None,
        "scanner_status": None,
        "last_cycle_status": None,
    }
    try:
        heartbeat = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        result["reason"] = "heartbeat_missing"
        return result
    except (OSError, ValueError, TypeError):
        return result
    if not isinstance(heartbeat, dict):
        return result

    result["scanner_status"] = heartbeat.get("status")
    result["last_cycle_status"] = heartbeat.get("last_cycle_status")
    try:
        stamp = datetime.fromisoformat(str(heartbeat["timestamp"]))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(timezone.utc)
        clock = now or datetime.now(timezone.utc)
        if clock.tzinfo is None:
            clock = clock.replace(tzinfo=timezone.utc)
        else:
            clock = clock.astimezone(timezone.utc)
        age = (clock - stamp).total_seconds()
    except (ValueError, TypeError, KeyError, AttributeError):
        return result

    result["age_seconds"] = round(age, 1)
    result["heartbeat_time"] = stamp.isoformat()
    if age < -60:
        result["reason"] = "heartbeat_clock_skew"
    elif age > max_age_seconds:
        result["reason"] = "heartbeat_stale"
    elif heartbeat.get("status") != "running":
        result["reason"] = "scanner_not_running"
    elif heartbeat.get("last_cycle_status") == "failed":
        result["reason"] = "last_cycle_failed"
    else:
        result["healthy"] = True
        result["reason"] = "ok"
    return result


def heartbeat_is_healthy(
    path: Path,
    *,
    now: datetime | None = None,
    max_age_seconds: float = 900,
) -> bool:
    return bool(
        inspect_heartbeat(path, now=now, max_age_seconds=max_age_seconds)["healthy"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("data_live/scanner_heartbeat.json"),
    )
    parser.add_argument("--max-age-seconds", type=float, default=900)
    args = parser.parse_args()
    return (
        0
        if heartbeat_is_healthy(
            args.path,
            max_age_seconds=args.max_age_seconds,
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
