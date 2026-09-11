"""Scanner liveness check used by Docker; a stale file is not a heartbeat."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def heartbeat_is_healthy(path: Path, *, now: datetime | None = None, max_age_seconds: float = 900) -> bool:
    try:
        heartbeat = json.loads(path.read_text(encoding="utf-8"))
        stamp = datetime.fromisoformat(heartbeat["timestamp"])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
        return -60 <= age <= max_age_seconds and heartbeat.get("status") == "running" and heartbeat.get("last_cycle_status") != "failed"
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", type=Path, default=Path("data_live/scanner_heartbeat.json"))
    parser.add_argument("--max-age-seconds", type=float, default=900)
    args = parser.parse_args()
    return 0 if heartbeat_is_healthy(args.path, max_age_seconds=args.max_age_seconds) else 1

if __name__ == "__main__":
    raise SystemExit(main())
