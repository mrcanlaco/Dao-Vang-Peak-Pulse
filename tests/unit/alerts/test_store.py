"""Tests for AlertStore — DuckDB-backed alert history with cooldown."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dao_vang.alerts.store import AlertRecord, AlertStore


@pytest.fixture
def store(tmp_path: Path) -> AlertStore:
    """Fresh AlertStore with temp DuckDB file."""
    return AlertStore(str(tmp_path / "test_alerts.duckdb"))


def _make_record(
    symbol: str = "BTCUSDT",
    risk: str = "CAO",
    prob: float = 0.75,
    minutes_ago: int = 0,
) -> AlertRecord:
    now = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return AlertRecord(
        signal_time=now,
        symbol=symbol,
        probability=prob,
        risk_level=risk,
        threshold=0.4,
        close_price=65000.0,
        model_id="frozen_test_001",
        invalidation_time=now + timedelta(hours=24),
    )


class TestAlertStoreSchema:
    def test_init_creates_table(self, store: AlertStore) -> None:
        """Store should create alert_history table on init."""
        import duckdb

        conn = duckdb.connect(store._db_path)
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name='alert_history'"
        ).fetchall()
        assert len(tables) == 1
        conn.close()

    def test_idempotent_init(self, tmp_path: Path) -> None:
        """Re-creating store on same DB should not error."""
        db = str(tmp_path / "test.duckdb")
        AlertStore(db)
        AlertStore(db)  # should not raise


class TestAlertStoreSave:
    def test_save_and_query(self, store: AlertStore) -> None:
        """Saved record should appear in query results."""
        record = _make_record(symbol="ETHUSDT", risk="CAO")
        store.save(record)
        rows = store.query(symbol="ETHUSDT", days=1)
        assert len(rows) == 1
        assert rows[0]["symbol"] == "ETHUSDT"
        assert rows[0]["risk_level"] == "CAO"
        assert rows[0]["probability"] == 0.75

    def test_query_filters_by_symbol(self, store: AlertStore) -> None:
        """Query with symbol filter should only return matching rows."""
        store.save(_make_record(symbol="BTCUSDT"))
        store.save(_make_record(symbol="ETHUSDT"))
        btc = store.query(symbol="BTCUSDT", days=1)
        assert len(btc) == 1
        assert btc[0]["symbol"] == "BTCUSDT"

    def test_query_filters_by_risk(self, store: AlertStore) -> None:
        """Query with risk_levels filter should only return matching levels."""
        store.save(_make_record(symbol="BTC", risk="CAO"))
        store.save(_make_record(symbol="ETH", risk="THẤP"))
        high_only = store.query(risk_levels=["CAO"], days=1)
        assert len(high_only) == 1
        assert high_only[0]["risk_level"] == "CAO"


class TestAlertStoreCooldown:
    def test_no_cooldown_when_zero(self, store: AlertStore) -> None:
        """Cooldown=0 should never block."""
        record = _make_record()
        record.telegram_sent = True
        record.telegram_sent_at = datetime.now(timezone.utc)
        store.save(record)
        assert not store.is_in_cooldown("BTCUSDT", 0)

    def test_cooldown_blocks_recent(self, store: AlertStore) -> None:
        """Recent alert should trigger cooldown."""
        record = _make_record(minutes_ago=10)
        record.telegram_sent = True
        record.telegram_sent_at = datetime.now(timezone.utc) - timedelta(minutes=10)
        store.save(record)
        assert store.is_in_cooldown("BTCUSDT", 60)

    def test_cooldown_expires(self, store: AlertStore) -> None:
        """Old alert should not trigger cooldown."""
        record = _make_record(minutes_ago=120)
        record.telegram_sent = True
        record.telegram_sent_at = datetime.now(timezone.utc) - timedelta(minutes=120)
        store.save(record)
        assert not store.is_in_cooldown("BTCUSDT", 60)

    def test_cooldown_per_symbol(self, store: AlertStore) -> None:
        """Cooldown for one symbol should not block another."""
        record = _make_record(symbol="BTCUSDT", minutes_ago=5)
        record.telegram_sent = True
        record.telegram_sent_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        store.save(record)
        assert store.is_in_cooldown("BTCUSDT", 60)
        assert not store.is_in_cooldown("ETHUSDT", 60)

    def test_cooldown_ignores_unsent(self, store: AlertStore) -> None:
        """Alerts without telegram_sent should not count for cooldown."""
        record = _make_record(minutes_ago=5)
        record.telegram_sent = False
        store.save(record)
        assert not store.is_in_cooldown("BTCUSDT", 60)


class TestAlertStoreDailyBudget:
    def test_shadow_observations_do_not_consume_production_budget(
        self, store: AlertStore
    ) -> None:
        shadow = _make_record(symbol="SHADOWUSDT")
        shadow.telegram_sent = True
        shadow.telegram_sent_at = datetime.now(timezone.utc)
        shadow.shadow_mode = True
        store.save(shadow)

        production = _make_record(symbol="PRODUSDT")
        production.telegram_sent = True
        production.telegram_sent_at = datetime.now(timezone.utc)
        production.shadow_mode = False
        store.save(production)

        assert store.get_daily_alert_count() == 1


class TestAlertStoreMarkSent:
    def test_mark_telegram_sent(self, store: AlertStore) -> None:
        """Mark sent should update telegram_sent + telegram_sent_at."""
        record = _make_record()
        store.save(record)
        store.mark_telegram_sent(record.signal_time, "BTCUSDT")
        rows = store.query(symbol="BTCUSDT", days=1)
        assert rows[0]["telegram_sent"] is True
        assert rows[0]["telegram_sent_at"] is not None


class TestAlertStoreDismiss:
    def test_dismiss(self, store: AlertStore) -> None:
        """Dismiss should set dismissed=True + dismissed_at."""
        record = _make_record()
        store.save(record)
        store.dismiss(record.signal_time, "BTCUSDT")
        rows = store.query(symbol="BTCUSDT", days=1, include_dismissed=True)
        assert rows[0]["dismissed"] is True
        assert rows[0]["dismissed_at"] is not None

    def test_query_excludes_dismissed_by_default(self, store: AlertStore) -> None:
        """Dismissed alerts should be excluded by default."""
        record = _make_record()
        store.save(record)
        store.dismiss(record.signal_time, "BTCUSDT")
        rows = store.query(symbol="BTCUSDT", days=1, include_dismissed=False)
        assert len(rows) == 0


class TestAlertStoreUpdateHits:
    def test_update_hits(self, store: AlertStore) -> None:
        """Update hits should set hit + hit_time for matching records."""
        record = _make_record()
        store.save(record)
        labels = {("BTCUSDT", record.signal_time): True}
        updated = store.update_hits(labels)
        assert updated >= 1
        rows = store.query(symbol="BTCUSDT", days=1)
        assert rows[0]["hit"] is True
        assert rows[0]["hit_time"] is not None

    def test_update_hits_skip_already_set(self, store: AlertStore) -> None:
        """Already-judged alerts should not be re-updated."""
        record = _make_record()
        store.save(record)
        labels = {("BTCUSDT", record.signal_time): True}
        store.update_hits(labels)
        # Second update with different result should not change
        labels2 = {("BTCUSDT", record.signal_time): False}
        store.update_hits(labels2)
        rows = store.query(symbol="BTCUSDT", days=1)
        assert rows[0]["hit"] is True  # still True, not overwritten


class TestAlertStoreStats:
    def test_stats_empty(self, store: AlertStore) -> None:
        """Stats on empty store should return zeros."""
        stats = store.stats(days=7)
        assert stats["total"] == 0
        assert stats["hit_rate"] is None

    def test_stats_with_data(self, store: AlertStore) -> None:
        """Stats should count alerts by risk level."""
        store.save(_make_record(symbol="BTC", risk="CAO"))
        store.save(_make_record(symbol="ETH", risk="TRUNG BÌNH"))
        store.save(_make_record(symbol="SOL", risk="CAO"))
        stats = store.stats(days=1)
        assert stats["total"] == 3
        assert stats["by_risk"].get("CAO", 0) == 2
        assert stats["by_risk"].get("TRUNG BÌNH", 0) == 1
