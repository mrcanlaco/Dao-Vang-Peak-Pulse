from datetime import datetime, timezone

from dao_vang.domain.errors import SchemaError


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
