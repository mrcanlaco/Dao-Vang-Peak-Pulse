"""Tests for the user-facing tracking watchlist store."""

from pathlib import Path

import pytest

from dao_vang.scanner.tracking_watchlist import (
    TrackingWatchlistStore,
    calculate_position_metrics,
)


def test_position_metrics_use_direction_and_exposure_correctly() -> None:
    profitable_short = calculate_position_metrics(
        current_price=0.04351,
        entry_price=0.0497,
        position_side="SHORT",
        quantity=25,
        leverage=5,
    )
    losing_short = calculate_position_metrics(
        current_price=0.4787,
        entry_price=0.4443,
        position_side="SHORT",
        quantity=25,
        leverage=5,
    )

    assert profitable_short == {
        "position_change_pct": 12.45,
        "position_pnl": 0.15475,
        "position_roi_pct": 62.27,
    }
    assert losing_short == {
        "position_change_pct": -7.74,
        "position_pnl": -0.86,
        "position_roi_pct": -38.71,
    }


def test_position_metrics_prefer_explicit_usdt_notional() -> None:
    metrics = calculate_position_metrics(
        current_price=110,
        entry_price=100,
        position_side="LONG",
        quantity=2,
        notional=500,
        leverage=3,
    )

    assert metrics["position_pnl"] == 50.0
    assert metrics["position_roi_pct"] == 30.0


def test_add_is_idempotent_for_same_signal(tmp_path: Path) -> None:
    store = TrackingWatchlistStore(tmp_path / "tracking.json")
    first, created = store.add(
        {
            "symbol": "sol",
            "source": "radar",
            "source_signal_time": "2026-08-13T10:00:00+07:00",
            "source_probability": 0.82,
            "source_price": 150.0,
            "source_target_price": 138.0,
        }
    )
    second, created_again = store.add(
        {
            "symbol": "SOLUSDT",
            "source": "radar",
            "source_signal_time": "2026-08-13T10:00:00+07:00",
        }
    )

    assert created is True
    assert created_again is False
    assert second["id"] == first["id"]
    assert len(store.list()) == 1


def test_position_update_requires_direction_and_entry(tmp_path: Path) -> None:
    store = TrackingWatchlistStore(tmp_path / "tracking.json")
    entry, _ = store.add({"symbol": "BTCUSDT", "source": "manual"})

    with pytest.raises(ValueError, match="position_side"):
        store.update(entry["id"], {"status": "IN_POSITION"})

    updated = store.update(
        entry["id"],
        {
            "status": "IN_POSITION",
            "position_side": "short",
            "entry_price": 100000,
            "notional": 250,
            "leverage": 3,
        },
    )

    assert updated is not None
    assert updated["status"] == "IN_POSITION"
    assert updated["position_side"] == "SHORT"
    assert updated["entry_price"] == 100000
    assert updated["opened_at"]


def test_remove_only_deletes_requested_entry(tmp_path: Path) -> None:
    store = TrackingWatchlistStore(tmp_path / "tracking.json")
    first, _ = store.add({"symbol": "ETHUSDT"})
    second, _ = store.add({"symbol": "BNBUSDT"})

    assert store.remove(first["id"]) is True
    assert store.remove(first["id"]) is False
    assert [item["id"] for item in store.list()] == [second["id"]]


def test_unfollow_retains_original_observation_and_journal(tmp_path: Path) -> None:
    store = TrackingWatchlistStore(tmp_path / "tracking.json")
    entry, _ = store.add({"symbol": "BTC", "source_price": 100, "source_target_price": 92})
    store.update(entry["id"], {"notes": "Theo dõi thử"})
    assert store.remove(entry["id"]) is True
    assert store.list() == []
    archived = store.list(include_archived=True)[0]
    assert archived['source_price'] == 100
    assert archived['source_target_price'] == 92
    assert archived['archived_at']
    assert [event['event'] for event in archived['history']] == ['SAVED', 'UPDATED', 'ARCHIVED']
    with pytest.raises(ValueError, match='Archived'):
        store.update(entry['id'], {'notes': 'rewrite'})
    replacement, created = store.add({'symbol': 'BTC'})
    assert created
    assert replacement['id'] != entry['id']
    assert len(store.list(include_archived=True)) == 2


def test_source_snapshot_cannot_be_rewritten(tmp_path: Path) -> None:
    store = TrackingWatchlistStore(tmp_path / 'tracking.json')
    entry, _ = store.add({'symbol': 'BTC', 'source_price': 100})
    with pytest.raises(ValueError, match='Unsupported'):
        store.update(entry['id'], {'source_price': 200})
    assert store.get(entry['id'])['source_price'] == 100
