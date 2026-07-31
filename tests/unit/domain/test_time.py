from datetime import datetime, timedelta, timezone

import pytest

from dao_vang.domain import SchemaError, ensure_utc, utc_now


def test_ensure_utc_valid() -> None:
    dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert ensure_utc(dt) == dt


def test_ensure_utc_naive_raises() -> None:
    dt = datetime(2026, 1, 1)
    with pytest.raises(SchemaError, match="Datetime must be timezone-aware."):
        ensure_utc(dt)


def test_ensure_utc_non_utc_raises() -> None:
    dt = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=7)))
    with pytest.raises(SchemaError, match="Datetime must be in UTC timezone."):
        ensure_utc(dt)


def test_utc_now_returns_utc() -> None:
    dt = utc_now()
    assert dt.tzinfo is not None
    assert dt.tzinfo.utcoffset(dt) == timezone.utc.utcoffset(None)
