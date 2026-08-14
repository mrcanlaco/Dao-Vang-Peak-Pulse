from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dao_vang.domain.errors import SchemaError

# The application is operated from Vietnam.  Keep this as the single source
# of truth for wall-clock dates and user-facing timestamps.  Market exchange
# timestamps are still normalized to UTC at the data boundary because they
# represent absolute instants, not local calendar times.
SYSTEM_TIMEZONE_NAME = "Asia/Ho_Chi_Minh"
SYSTEM_TIMEZONE = ZoneInfo(SYSTEM_TIMEZONE_NAME)
SYSTEM_TIMEZONE_LABEL = "Hà Nội / Hồ Chí Minh (UTC+7)"


def ensure_utc(dt: datetime) -> datetime:
    """Ensure the datetime is timezone-aware and set to UTC.

    Raises:
        SchemaError: If the datetime is naive or not UTC.
    """
    if dt.tzinfo is None:
        raise SchemaError("Datetime must be timezone-aware.")

    if dt.tzinfo.utcoffset(dt) != timezone.utc.utcoffset(None):
        raise SchemaError("Datetime must be in UTC timezone.")

    return dt


def utc_now() -> datetime:
    """Return the current time in UTC."""
    return datetime.now(timezone.utc)


def system_now() -> datetime:
    """Return the current wall-clock time in the system timezone (UTC+7)."""
    return datetime.now(SYSTEM_TIMEZONE)


def as_system_timezone(
    value: datetime,
    *,
    assume_timezone=timezone.utc,
) -> datetime:
    """Convert a datetime to the application's UTC+7 display timezone.

    DuckDB ``TIMESTAMP`` values are timezone-naive even though this project
    stores them as UTC.  ``assume_timezone`` makes that legacy/storage
    convention explicit instead of letting the host machine decide.
    """
    aware = value if value.tzinfo is not None else value.replace(tzinfo=assume_timezone)
    return aware.astimezone(SYSTEM_TIMEZONE)


def system_iso(value: Any, *, assume_timezone=timezone.utc) -> str | None:
    """Serialize a datetime-like value as an ISO timestamp with ``+07:00``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return as_system_timezone(value, assume_timezone=assume_timezone).isoformat()
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return raw
        if raw.upper().endswith(" UTC+7"):
            raw = f"{raw[:-6]}+07:00"
        elif raw.upper().endswith(" UTC"):
            raw = f"{raw[:-4]}+00:00"
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return value
        return as_system_timezone(parsed, assume_timezone=assume_timezone).isoformat()
    return str(value)
