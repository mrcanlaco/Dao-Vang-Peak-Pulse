"""Local, aggregate usability counters; no external analytics service."""

import hashlib
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path


def tracking_usage(path: Path, visitor: str | None = None) -> dict[str, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).date()
    if visitor is not None and not re.fullmatch(r"[a-zA-Z0-9-]{16,80}", visitor):
        raise ValueError("Invalid anonymous visitor id")
    with sqlite3.connect(path, timeout=5) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS visits (visitor TEXT, day TEXT, PRIMARY KEY(visitor, day))")
        if visitor:
            conn.execute("INSERT OR IGNORE INTO visits VALUES (?, ?)", (hashlib.sha256(visitor.encode()).hexdigest(), today.isoformat()))
        since = (today - timedelta(days=6)).isoformat()
        counts = conn.execute("SELECT visitor, COUNT(*) FROM visits WHERE day >= ? GROUP BY visitor", (since,)).fetchall()
        return {"visitors_7d": len(counts), "returning_visitors_7d": sum(1 for _, days in counts if days > 1)}
