from datetime import datetime, timezone

from dao_vang.scanner.daemon import _last_closed_5m_end


def test_last_closed_5m_end_excludes_currently_forming_candle():
    now = datetime(2026, 8, 12, 18, 52, 30, tzinfo=timezone.utc)

    assert _last_closed_5m_end(now) == datetime(
        2026, 8, 12, 18, 49, 59, 999000, tzinfo=timezone.utc
    )


def test_last_closed_5m_end_normalizes_local_timezone():
    now = datetime.fromisoformat("2026-08-13T01:52:30+07:00")

    assert _last_closed_5m_end(now) == datetime(
        2026, 8, 12, 18, 49, 59, 999000, tzinfo=timezone.utc
    )
