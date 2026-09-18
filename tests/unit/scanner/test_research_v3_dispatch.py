"""Observe-level lifecycle dispatch coverage for the V3 research lane."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dao_vang.alerts import notification_dispatcher
from dao_vang.config.settings import AppSettings
from dao_vang.scanner import research_v3
from tests.unit.scanner.test_research_v3 import setup as setup_fixture  # noqa: F401


class RecordingDispatcher:
    """A transport fake that proves dispatch happens after ledger commit."""

    instances: list["RecordingDispatcher"] = []

    def __init__(self, notifier: object, storage_path: str | Path, **_: object) -> None:
        del notifier
        self.storage_path = Path(storage_path)
        self.events: list[tuple[str, dict]] = []
        self.retry_calls = 0
        type(self).instances.append(self)

    def retry_pending(self) -> list[object]:
        self.retry_calls += 1
        return []

    def _record(self, kind: str, event: dict) -> None:
        signal_id = event["signal_id"]
        with sqlite3.connect(self.storage_path.with_name("observations.sqlite")) as ledger:
            assert ledger.execute(
                "SELECT 1 FROM observations WHERE id=?", [signal_id]
            ).fetchone() is not None
        self.events.append((kind, event))

    def dispatch_signal(self, event: dict) -> None:
        self._record("signal", event)

    def dispatch_outcome(self, event: dict) -> None:
        self._record("outcome", event)


def test_observe_dispatches_committed_signal_actual_and_all_entry_fills(
    setup_fixture,  # noqa: F811
    monkeypatch,
) -> None:
    """Entry2/Entry3 are not lost and no event is sent inside the ledger tx."""

    conn, args = setup_fixture
    conn.execute(
        """UPDATE feature_results
           SET distance_from_high_24h=-0.03,
               funding_persistence_7d=0.01,
               funding_change_8h=0.001"""
    )
    settings = AppSettings(
        research_v3_telegram_enabled=True,
        research_v3_chat_id="shadow-chat",
    )
    RecordingDispatcher.instances.clear()
    monkeypatch.setattr(
        notification_dispatcher, "NotificationDispatcher", RecordingDispatcher
    )
    monkeypatch.setattr(
        "dao_vang.alerts.telegram.TelegramNotifier",
        lambda *unused_args, **unused_kwargs: object(),
    )

    payload = {
        "status": "target",
        "fills": [
            {"leg": 1, "timestamp": "2026-09-14T02:05:00+00:00", "price": 100.0, "average_entry": 100.0},
            {"leg": 2, "timestamp": "2026-09-14T02:10:00+00:00", "price": 103.0, "average_entry": 101.0},
            {"leg": 3, "timestamp": "2026-09-14T02:15:00+00:00", "price": 106.0, "average_entry": 102.0},
            ],
        "exit_price": 80.0,
        "post_stop": {"status": "not_applicable"},
    }
    monkeypatch.setattr(
        research_v3,
        "evaluate_dual",
        lambda **_: SimpleNamespace(to_dict=lambda: json.loads(json.dumps(payload))),
    )

    # Establish the observation activation boundary before replaying the
    # fixture’s historical-looking rows, matching the real forward-only cycle.
    research_v3.observe(
        conn,
        **args,
        now=research_v3.time_value("2026-09-14T00:00:00+00:00"),
        settings=settings,
    )
    result = None
    for hour in range(1, 5):
        result = research_v3.observe(
            conn,
            **args,
            now=research_v3.time_value(
                f"2026-09-14T{hour:02d}:05:00+00:00"
            ),
            settings=settings,
        )
    assert result["entry_count"] == 1, result

    assert all(item.retry_calls == 1 for item in RecordingDispatcher.instances)
    events_with_kind = [
        item for dispatcher in RecordingDispatcher.instances for item in dispatcher.events
    ]
    assert [kind for kind, _ in events_with_kind] == [
        "signal", "outcome", "outcome", "outcome"
    ]
    events = [event for _, event in events_with_kind]
    assert events[0]["event_type"] == "signal"
    fills = events[1:3]
    assert [event["event_type"] for event in fills] == ["entry_fill", "entry_fill"]
    assert [event["event_key"] for event in fills] == [
        f"{events[0]['signal_id']}:fill:2",
        f"{events[0]['signal_id']}:fill:3",
    ]
    assert events[3]["event_type"] == "target"


def test_observe_replays_stop_until_post_stop_recovery_is_resolved(
    setup_fixture,  # noqa: F811
    monkeypatch,
) -> None:
    """A stopped path is not terminal until its frozen-average path resolves."""

    conn, args = setup_fixture
    conn.execute(
        """UPDATE feature_results
           SET distance_from_high_24h=-0.03,
               funding_persistence_7d=0.01,
               funding_change_8h=0.001"""
    )
    settings = AppSettings(
        research_v3_telegram_enabled=True,
        research_v3_chat_id="shadow-chat",
    )
    RecordingDispatcher.instances.clear()
    monkeypatch.setattr(
        notification_dispatcher, "NotificationDispatcher", RecordingDispatcher
    )
    monkeypatch.setattr(
        "dao_vang.alerts.telegram.TelegramNotifier",
        lambda *unused_args, **unused_kwargs: object(),
    )

    stop_payload = {
        "status": "stop",
        "engine_status": "stop",
        "eligible": True,
        "exclusion_reason": None,
        "contract": "distribution_short_v3_policy_48h",
        "contract_checksum": "contract-checksum",
        "fills": [
            {
                "leg": 1,
                "timestamp": "2026-09-14T04:05:00+00:00",
                "price": 100.0,
                "average_entry": 100.0,
            }
        ],
        "exit_time": "2026-09-14T04:10:00+00:00",
        "exit_price": 116.0,
        "post_stop": {
            "status": "incomplete_after_stop",
            "contract": "distribution_short_v3_policy_48h",
            "contract_checksum": "contract-checksum",
            "frozen_average_entry": 100.0,
            "frozen_target_price": 80.0,
        },
    }
    recovery_payload = {
        **stop_payload,
        "post_stop": {
            **stop_payload["post_stop"],
            "status": "target_after_stop",
            "target_time": "2026-09-14T04:15:00+00:00",
            "target_price": 80.0,
            "horizon_time": "2026-09-16T04:05:00+00:00",
        },
    }
    calls = 0

    def fake_evaluate(**_: object) -> SimpleNamespace:
        nonlocal calls
        current = stop_payload if calls == 0 else recovery_payload
        calls += 1
        return SimpleNamespace(to_dict=lambda: json.loads(json.dumps(current)))

    monkeypatch.setattr(research_v3, "evaluate_dual", fake_evaluate)
    research_v3.observe(
        conn,
        **args,
        now=research_v3.time_value("2026-09-14T00:00:00+00:00"),
        settings=settings,
    )
    for hour in range(1, 5):
        research_v3.observe(
            conn,
            **args,
            now=research_v3.time_value(f"2026-09-14T{hour:02d}:05:00+00:00"),
            settings=settings,
        )
    research_v3.observe(
        conn,
        **args,
        now=research_v3.time_value("2026-09-14T05:05:00+00:00"),
        settings=settings,
    )

    assert calls == 2
    with sqlite3.connect(args["storage"] / "observations.sqlite") as ledger:
        identity, text = ledger.execute(
            "SELECT id, payload FROM outcomes"
        ).fetchone()
    assert identity
    outcome = json.loads(text)
    assert outcome["status"] == "stop"
    assert outcome["post_stop"]["status"] == "target_after_stop"
    lifecycle = [
        event
        for dispatcher in RecordingDispatcher.instances
        for _, event in dispatcher.events
    ]
    assert any(
        event.get("event_type") == "post_stop"
        and event.get("status") == "target_after_stop"
        for event in lifecycle
    )
