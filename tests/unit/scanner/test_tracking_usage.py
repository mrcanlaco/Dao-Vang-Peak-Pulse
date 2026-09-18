import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from dao_vang.scanner.tracking_usage import tracking_usage


def test_daily_visits_deduplicate_and_returning_devices_require_another_day(tmp_path):
    path = tmp_path / 'usage.sqlite3'
    visitor = 'anonymous-device-1234'
    assert tracking_usage(path, visitor) == {'visitors_7d': 1, 'returning_visitors_7d': 0}
    assert tracking_usage(path, visitor) == {'visitors_7d': 1, 'returning_visitors_7d': 0}
    with sqlite3.connect(path) as conn:
        hashed, _ = conn.execute('SELECT visitor, day FROM visits').fetchone()
        assert hashed != visitor
        yesterday = (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
        conn.execute('INSERT INTO visits VALUES (?, ?)', (hashed, yesterday))
    assert tracking_usage(path) == {'visitors_7d': 1, 'returning_visitors_7d': 1}
    with pytest.raises(ValueError):
        tracking_usage(path, 'user@example.com')
