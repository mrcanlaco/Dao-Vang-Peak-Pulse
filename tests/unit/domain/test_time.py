from datetime import datetime, timedelta, timezone

import pytest

from dao_vang.domain import (
    SYSTEM_TIMEZONE_NAME,
    SchemaError,
    as_system_timezone,
    ensure_utc,
    system_iso,
    system_now,
    utc_now,
)


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


def test_system_now_uses_hanoi_timezone() -> None:
    dt = system_now()
    assert SYSTEM_TIMEZONE_NAME == "Asia/Ho_Chi_Minh"
    assert dt.tzinfo is not None
    assert dt.utcoffset() == timedelta(hours=7)


def test_system_iso_converts_utc_storage_timestamp_to_utc_plus_7() -> None:
    assert system_iso("2026-08-12T18:00:00+00:00") == "2026-08-13T01:00:00+07:00"
    assert system_iso(datetime(2026, 8, 12, 18, 0)) == "2026-08-13T01:00:00+07:00"
    assert system_iso("2026-08-13 01:00:00 UTC+7") == "2026-08-13T01:00:00+07:00"


def test_as_system_timezone_preserves_instant() -> None:
    local = as_system_timezone(datetime(2026, 8, 12, 18, 0, tzinfo=timezone.utc))
    assert local.hour == 1
    assert local.day == 13
