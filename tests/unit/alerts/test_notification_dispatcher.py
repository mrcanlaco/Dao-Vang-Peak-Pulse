"""Durability and threading tests for the V3 Telegram outbox."""

from __future__ import annotations

from pathlib import Path

from dao_vang.alerts.notification_dispatcher import NotificationDispatcher


def _signal(**overrides: object) -> dict[str, object]:
    event: dict[str, object] = {
        "id": "obs-1",
        "event_type": "signal",
        "symbol": "BTCUSDT",
        "entry_price": 100.0,
        "score": 0.52,
        "feature_time": "2026-09-15T00:00:00+00:00",
        "operating_mode": "research",
        "shadow_chat_id": "shadow-1",
        "conditions": {
            "pump": True,
            "reversal": True,
            "funding": True,
            "funding_change": True,
            "score": True,
            "funding_persistence": True,
        },
        "pattern_id": "unknown",
        "pattern_stage": "reversal",
        "pattern_status": "unknown",
        "nearest_pattern": "pattern_01",
        "pattern_discrepancies": ["funding_persistence_7d"],
    }
    event.update(overrides)
    return event


class FakeNotifier:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.signal_calls: list[dict[str, object]] = []
        self.outcome_calls: list[dict[str, object]] = []

    def send_v3_alert_with_result(self, **kwargs: object) -> dict[str, object] | None:
        self.signal_calls.append(kwargs)
        if self.fail:
            return None
        return {"message_id": 101, "chat": {"id": "shadow-1"}}

    def send_v3_outcome_update_with_result(self, **kwargs: object) -> dict[str, object] | None:
        self.outcome_calls.append(kwargs)
        if self.fail:
            return None
        return {"message_id": 102, "chat": {"id": "shadow-1"}}


def test_signal_is_deduplicated_and_message_id_persisted(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(notifier, tmp_path / "notifications.sqlite")

    first = dispatcher.dispatch_signal(_signal())
    second = dispatcher.dispatch_signal(_signal())

    assert first.status == "sent"
    assert first.message_id == 101
    assert second.deduplicated is True
    assert second.message_id == 101
    assert len(notifier.signal_calls) == 1
    assert dispatcher.get("obs-1:signal")["message_id"] == 101  # type: ignore[index]


def test_lifecycle_update_replies_to_root_and_uses_distinct_key(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(notifier, tmp_path / "notifications.sqlite")
    dispatcher.dispatch_signal(_signal(event_key="observation-key"))

    result = dispatcher.dispatch({
        "id": "obs-1",
        "event_type": "target",
        "event_key": "observation-key",
        "symbol": "BTCUSDT",
        "status": "target",
        "event_time": "2026-09-15T04:00:00+00:00",
        "operating_mode": "research",
        "shadow_chat_id": "shadow-1",
    })

    assert result.status == "sent"
    assert notifier.outcome_calls[0]["reply_to_message_id"] == 101
    assert notifier.outcome_calls[0]["chat_id"] == "shadow-1"
    assert result.event_key != "observation-key:signal"


def test_outcome_waits_for_root_then_retries_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "notifications.sqlite"
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(notifier, path)
    pending = dispatcher.dispatch({
        "id": "obs-2",
        "event_type": "stop",
        "symbol": "ETHUSDT",
        "status": "stop",
        "event_time": "2026-09-15T04:00:00+00:00",
        "operating_mode": "research",
        "shadow_chat_id": "shadow-1",
    })
    assert pending.status == "pending"
    assert notifier.outcome_calls == []

    dispatcher.dispatch_signal(_signal(id="obs-2", symbol="ETHUSDT"))
    retried = dispatcher.retry_pending()
    assert [item.status for item in retried] == ["sent"]
    assert notifier.outcome_calls[0]["reply_to_message_id"] == 101


def test_failed_signal_retries_from_persisted_outbox(tmp_path: Path) -> None:
    path = tmp_path / "notifications.sqlite"
    failing = FakeNotifier(fail=True)
    first = NotificationDispatcher(failing, path).dispatch_signal(_signal(id="obs-3"))
    assert first.status == "failed"

    succeeding = FakeNotifier()
    results = NotificationDispatcher(succeeding, path).retry_pending()
    assert [result.status for result in results] == ["sent"]
    assert succeeding.signal_calls


def test_signal_requires_all_five_attested_conditions(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(notifier, tmp_path / "notifications.sqlite")
    result = dispatcher.dispatch_signal(_signal(conditions={"pump": True}))
    assert result.status == "rejected"
    assert notifier.signal_calls == []


def test_persistence_is_an_extra_gate_not_a_replacement_for_score(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(notifier, tmp_path / "notifications.sqlite")
    result = dispatcher.dispatch_signal(_signal(conditions={
        "pump": True,
        "reversal": True,
        "funding": True,
        "funding_change": True,
        "score": True,
        "funding_persistence": False,
    }))
    assert result.status == "sent"
    assert notifier.signal_calls[0]["conditions"]["score"] is True


def test_selector_attestation_allows_confirmed_reference_score_below_display_gate(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(notifier, tmp_path / "notifications.sqlite")
    result = dispatcher.dispatch_signal(_signal(
        champion=True,
        runtime_version="research_v3_runtime_v1",
        conditions={
            "pump": True,
            "reversal": True,
            "funding": True,
            "funding_change": True,
            "score": False,
        },
        selection_attestation={
            "eligible": True,
            "policy_version": "v3_timing_policy_v1",
            "source_id": "obs-1",
        },
    ))
    assert result.status == "sent"
    assert notifier.signal_calls[0]["score_confirmation"] == "runtime selector confirmed"


def test_subthreshold_champion_without_explicit_attestation_is_rejected(tmp_path: Path) -> None:
    notifier = FakeNotifier()
    dispatcher = NotificationDispatcher(notifier, tmp_path / "notifications.sqlite")
    result = dispatcher.dispatch_signal(_signal(
        champion=True,
        runtime_version="research_v3_runtime_v1",
        conditions={
            "pump": True,
            "reversal": True,
            "funding": True,
            "funding_change": True,
            "score": False,
        },
    ))
    assert result.status == "rejected"
    assert notifier.signal_calls == []
