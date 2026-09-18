"""Durable Telegram dispatch for V3 research lifecycle events.

The research lane is intentionally observation-only, but its notifications
still need production-grade delivery semantics.  This module keeps a small
SQLite outbox with deterministic event keys, retries failed deliveries after a
restart, and stores Telegram message ids so lifecycle updates can reply to the
original signal.  It does not decide which observations are signals: the
scanner supplies the event and this dispatcher never applies the UI's quality
filter.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from dao_vang.logging import get_logger

logger = get_logger(__name__)

_TERMINAL = {"sent", "disabled"}
_OUTCOME_EVENTS = {
    "entry",
    "entry_fill",
    "fill",
    "target",
    "tp",
    "stop",
    "stop_ambiguous",
    "timeout",
    "post_stop",
    "post_stop_price_only",
    "target_after_stop",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get(event: Mapping[str, Any] | Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(event, Mapping) and name in event:
            value = event[name]
        else:
            value = getattr(event, name, None)
        if value is not None:
            return value
    return default


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return value


def _mapping(event: Mapping[str, Any] | Any) -> dict[str, Any]:
    if isinstance(event, Mapping):
        return {str(key): _jsonable(value) for key, value in event.items()}
    if hasattr(event, "__dataclass_fields__"):
        from dataclasses import asdict

        return _jsonable(asdict(event))
    if hasattr(event, "__dict__"):
        return _jsonable(vars(event))
    raise TypeError("notification event must be a mapping or object with fields")


def _normalise_event_type(value: Any) -> str:
    raw = str(value or "signal").strip().lower().replace("-", "_")
    if raw in {"signal", "entry_signal", "v3_signal"}:
        return "signal"
    return raw


def _event_key(event: Mapping[str, Any], event_type: str, signal_id: str) -> str:
    notification_key = event.get("notification_key")
    if notification_key:
        base = str(notification_key)
        if base == event_type or base.endswith(f":{event_type}"):
            return base
        return f"{base}:{event_type}"
    explicit = event.get("event_key")
    if explicit:
        base = str(explicit)
        transition = event.get("transition_id") or event.get("event_id") or event.get("sequence") or event.get("revision")
        if transition is not None:
            return f"{base}:{event_type}:{transition}"
        # An explicit key is already the caller's stable transition identity
        # in the scanner (for example ``id:actual:stop``).  Never append the
        # wall-clock update time: doing so would defeat restart-safe dedup.
        if base == event_type or base.endswith(f":{event_type}"):
            return base
        return f"{base}:{event_type}"
    transition = event.get("transition_id") or event.get("event_id")
    if transition:
        return f"{signal_id}:{event_type}:{transition}"
    # Signal ids are immutable observation ids.  Outcome transitions use a
    # stable status/sequence token when supplied, otherwise their event time.
    if event_type == "signal":
        return f"{signal_id}:signal"
    sequence = event.get("sequence") or event.get("revision")
    token = sequence if sequence is not None else event.get("event_time") or event.get("updated_at")
    if token is None:
        token = hashlib.sha256(
            json.dumps(event, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
    return f"{signal_id}:{event_type}:{token}"


@dataclass(frozen=True)
class DispatchResult:
    """Outcome of one outbox operation."""

    event_key: str
    status: str
    sent: bool
    deduplicated: bool = False
    message_id: int | None = None
    reply_to_message_id: int | None = None
    attempts: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.sent or self.deduplicated


class NotificationDispatcher:
    """Persist and deliver V3 Telegram events.

    ``enabled`` is the scanner's explicit Telegram opt-in.  No quality or UI
    filter is applied here; callers may show only high-quality observations in
    the panel while every selected five-condition signal remains dispatchable.
    """

    def __init__(
        self,
        notifier: Any,
        storage_path: str | Path = "data/research_v3/telegram_notifications.sqlite",
        *,
        enabled: bool = True,
        operating_mode: str = "research",
        shadow_chat_id: str | None = None,
        lease_seconds: int = 60,
    ) -> None:
        self.notifier = notifier
        self.storage_path = Path(storage_path)
        self.enabled = bool(enabled)
        self.operating_mode = operating_mode
        self.shadow_chat_id = shadow_chat_id
        self.lease_seconds = max(1, int(lease_seconds))
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.storage_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA journal_mode=WAL")
        return connection

    def _initialise(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS notification_events (
                    event_key TEXT PRIMARY KEY,
                    signal_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    chat_id TEXT,
                    message_id INTEGER,
                    reply_to_message_id INTEGER,
                    payload_json TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_notification_events_status
                    ON notification_events(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_notification_events_signal
                    ON notification_events(signal_id, event_type, status);
                """
            )

    def _reserve(
        self,
        *,
        event_key: str,
        signal_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> tuple[str, int, int | None, int | None, str | None]:
        """Reserve one event, returning status/attempt metadata.

        A recent ``sending`` lease is left alone so two scanner cycles cannot
        send the same event concurrently.  A stale lease is retried, which is
        what makes a process restart recover an interrupted send.
        """
        now = datetime.now(timezone.utc)
        now_text = now.isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status, attempts, message_id, reply_to_message_id, chat_id, updated_at "
                "FROM notification_events WHERE event_key=?",
                [event_key],
            ).fetchone()
            if row is None:
                connection.execute(
                    """INSERT INTO notification_events (
                        event_key, signal_id, event_type, status, attempts,
                        payload_json, created_at, updated_at
                    ) VALUES (?, ?, ?, 'sending', 1, ?, ?, ?)""",
                    [event_key, signal_id, event_type, json.dumps(payload, sort_keys=True), now_text, now_text],
                )
                return "sending", 1, None, None, None
            status = str(row["status"])
            attempts = int(row["attempts"] or 0)
            message_id = int(row["message_id"]) if row["message_id"] is not None else None
            reply_id = int(row["reply_to_message_id"]) if row["reply_to_message_id"] is not None else None
            chat_id = str(row["chat_id"]) if row["chat_id"] is not None else None
            if status in _TERMINAL:
                return status, attempts, message_id, reply_id, chat_id
            updated = None
            try:
                updated = datetime.fromisoformat(str(row["updated_at"]))
                if updated.tzinfo is None:
                    updated = updated.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                pass
            if status == "sending" and updated is not None and now - updated < timedelta(seconds=self.lease_seconds):
                return "in_progress", attempts, message_id, reply_id, chat_id
            attempts += 1
            connection.execute(
                """UPDATE notification_events
                   SET status='sending', attempts=?, payload_json=?, last_error=NULL, updated_at=?
                 WHERE event_key=?""",
                [attempts, json.dumps(payload, sort_keys=True), now_text, event_key],
            )
            return "sending", attempts, message_id, reply_id, chat_id

    def _finish(
        self,
        event_key: str,
        *,
        status: str,
        attempts: int,
        message_id: int | None = None,
        reply_to_message_id: int | None = None,
        chat_id: str | None = None,
        error: str | None = None,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """UPDATE notification_events
                   SET status=?, attempts=?, message_id=COALESCE(?, message_id),
                       reply_to_message_id=COALESCE(?, reply_to_message_id),
                       chat_id=COALESCE(?, chat_id), last_error=?, updated_at=?
                 WHERE event_key=?""",
                [
                    status,
                    attempts,
                    message_id,
                    reply_to_message_id,
                    chat_id,
                    error,
                    _now(),
                    event_key,
                ],
            )

    def _signal_message(self, signal_id: str) -> tuple[int | None, str | None]:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT message_id, chat_id FROM notification_events
                   WHERE signal_id=? AND event_type='signal' AND status='sent'
                   ORDER BY updated_at DESC LIMIT 1""",
                [signal_id],
            ).fetchone()
        if row is None:
            return None, None
        message_id = int(row["message_id"]) if row["message_id"] is not None else None
        return message_id, str(row["chat_id"]) if row["chat_id"] else None

    @staticmethod
    def _result_metadata(result: Any) -> tuple[bool, int | None, str | None]:
        if isinstance(result, Mapping):
            if "ok" in result and not bool(result.get("ok")):
                return False, None, None
            if "success" in result and not bool(result.get("success")):
                return False, None, None
            message_id = result.get("message_id")
            try:
                message_id = int(message_id) if message_id is not None else None
            except (TypeError, ValueError):
                message_id = None
            chat = result.get("chat", {})
            chat_id = result.get("chat_id") or (chat.get("id") if isinstance(chat, Mapping) else None)
            return True, message_id, str(chat_id) if chat_id is not None else None
        return bool(result), None, None

    def _target_chat(self, event: Mapping[str, Any]) -> str | None:
        mode = str(_get(event, "operating_mode", default=self.operating_mode))
        shadow = _get(event, "shadow_chat_id", default=self.shadow_chat_id)
        resolver = getattr(self.notifier, "_v3_target_chat", None)
        if callable(resolver):
            return resolver(mode, shadow)
        config = getattr(self.notifier, "_config", None)
        if mode in {"research", "shadow"}:
            return shadow or getattr(config, "shadow_chat_id", None)
        return shadow or getattr(config, "chat_id", None)

    def _send_signal(self, event: dict[str, Any]) -> tuple[bool, int | None, str | None]:
        method = getattr(self.notifier, "send_v3_alert_with_result", None)
        if method is None:
            method = getattr(self.notifier, "send_v3_alert")
        kwargs: dict[str, Any] = {
            "symbol": _get(event, "symbol", default=""),
            "entry_price": float(_get(event, "entry_price", "price", default=0.0) or 0.0),
            "probability": float(_get(event, "score", "probability", default=0.0) or 0.0),
            "pump_pct": float(_get(event, "pump_pct", "price_ret_24h", default=0.0) or 0.0),
            "distance_from_high": float(_get(event, "distance_from_high", "distance_from_high_24h", default=0.0) or 0.0),
            "funding_percentile": float(_get(event, "funding_percentile", "funding_percentile_30d", default=0.0) or 0.0),
            "feature_time": str(_get(event, "feature_time", "signal_time", default="")),
            "is_champion": bool(_get(event, "is_champion", "champion", default=False)),
            "is_scout": bool(_get(event, "is_scout", "scout", default=False)),
            "web_url": _get(event, "web_url"),
            "operating_mode": str(_get(event, "operating_mode", default=self.operating_mode)),
            "shadow_chat_id": _get(event, "shadow_chat_id", default=self.shadow_chat_id),
            "pattern_id": _get(event, "pattern_id"),
            "pattern_type": _get(event, "pattern_type"),
            "pattern_stage": _get(event, "pattern_stage", "stage"),
            "pattern_status": _get(event, "pattern_status"),
            "nearest_pattern": _get(event, "nearest_pattern"),
            "pattern_distance": _get(event, "pattern_distance"),
            "pattern_discrepancies": _get(event, "pattern_discrepancies"),
            "pattern_quality": _get(event, "pattern_quality"),
            "conditions": _get(event, "conditions", "criteria"),
            "quality_validated": _get(event, "quality_validated", "high_quality"),
            "evidence_kind": _get(event, "evidence_kind"),
            "score_kind": str(_get(event, "score_kind", default="reference_model_score")),
            "score_confirmation": _get(event, "score_confirmation")
            or ("runtime selector confirmed" if self._selector_attestation(event) else None),
        }
        result = method(**kwargs)
        sent, message_id, chat_id = self._result_metadata(result)
        return sent, message_id, chat_id or self._target_chat(event)

    def _send_outcome(
        self,
        event: dict[str, Any],
        reply_to_message_id: int | None,
        chat_id: str | None = None,
    ) -> tuple[bool, int | None, str | None]:
        method = getattr(self.notifier, "send_v3_outcome_update_with_result", None)
        if method is None:
            method = getattr(self.notifier, "send_v3_outcome_update")
        event_type = _normalise_event_type(_get(event, "event_type", "type", "kind", "outcome_type", "status"))
        kwargs: dict[str, Any] = {
            "symbol": _get(event, "symbol", default=""),
            "outcome_type": event_type,
            "status": _get(event, "status", "outcome_status"),
            "event_time": _get(event, "event_time", "updated_at"),
            "feature_time": _get(event, "feature_time", "signal_time"),
            "average_entry": _get(event, "average_entry"),
            "exit_price": _get(event, "exit_price"),
            "filled_legs": _get(event, "filled_legs", "fill_count"),
            "actual_fill": _get(event, "actual_fill", "actual_win"),
            "price_only_post_stop": bool(
                _get(event, "price_only_post_stop", "post_stop_price_only", default=False)
                or str(_get(event, "status", default="")).lower() == "target_after_stop"
            ),
            "stop_average_entry": _get(event, "stop_average_entry", "frozen_average_at_stop"),
            "frozen_average_entry": _get(event, "frozen_average_entry"),
            "frozen_target_price": _get(event, "frozen_target_price"),
            "post_stop_return": _get(event, "post_stop_return"),
            "original_horizon_hours": int(_get(event, "original_horizon_hours", default=48) or 48),
            "horizon_time": _get(event, "horizon_time"),
            "target_time": _get(event, "target_time"),
            "operating_mode": str(_get(event, "operating_mode", default=self.operating_mode)),
            "shadow_chat_id": _get(event, "shadow_chat_id", default=self.shadow_chat_id),
            "reply_to_message_id": reply_to_message_id,
            "chat_id": chat_id,
            "web_url": _get(event, "web_url"),
            "pattern_id": _get(event, "pattern_id"),
            "pattern_type": _get(event, "pattern_type"),
            "pattern_stage": _get(event, "pattern_stage", "stage"),
            "pattern_status": _get(event, "pattern_status"),
            "pattern_quality": _get(event, "pattern_quality"),
            "evidence_kind": _get(event, "evidence_kind"),
        }
        result = method(**kwargs)
        sent, message_id, result_chat = self._result_metadata(result)
        return sent, message_id, result_chat or chat_id or self._target_chat(event)

    @staticmethod
    def _validated_conditions(event: Mapping[str, Any]) -> dict[str, Any] | None:
        raw = event.get("conditions") or event.get("criteria")
        if not raw and isinstance(event.get("progress"), Mapping):
            raw = event["progress"].get("criteria")
        if not isinstance(raw, Mapping):
            return None
        aliases = {
            "pump": ("pump",),
            "reversal": ("reversal",),
            "funding": ("funding",),
            "funding_change": ("funding_change", "funding_change_8h"),
            "score": ("score", "reference_score", "model_score"),
        }
        result: dict[str, Any] = {}
        for name, keys in aliases.items():
            value = next((raw[key] for key in keys if key in raw), None)
            if isinstance(value, Mapping):
                value = value.get("passed", value.get("met"))
            if not isinstance(value, bool):
                return None
            result[name] = value
        # Persistence is an additional Scout/Champion gate.  Preserve its
        # attestation for the renderer/audit trail when supplied, but do not
        # redefine the original five-condition signal contract around it.
        persistence = next(
            (raw[key] for key in ("funding_persistence", "funding_persistence_7d") if key in raw),
            None,
        )
        if isinstance(persistence, Mapping):
            persistence = persistence.get("passed", persistence.get("met"))
        if persistence is not None:
            if not isinstance(persistence, bool):
                return None
            result["funding_persistence"] = persistence
        return result

    @staticmethod
    def _selector_attestation(event: Mapping[str, Any]) -> bool:
        """Trust a selector-confirmed Champion below the display score gate.

        The timing selector is authoritative for confirmation.  A reference
        score below its display threshold is therefore deliverable only when
        the runtime supplies an explicit eligibility bit plus policy and source
        provenance; an arbitrary ``champion`` label alone is not sufficient.
        """
        nested = event.get("selection_attestation")
        if not isinstance(nested, Mapping):
            return False
        eligible = nested.get("eligible")
        policy = nested.get("policy_version") or nested.get("timing_policy_version")
        source = nested.get("source_id")
        return eligible is True and bool(str(policy or "").strip()) and bool(str(source or "").strip())

    def dispatch(self, event: Mapping[str, Any] | Any) -> DispatchResult:
        """Persist and deliver one signal or lifecycle event."""
        payload = _mapping(event)
        event_type = _normalise_event_type(
            payload.get("event_type") or payload.get("type") or payload.get("kind") or payload.get("outcome_type")
        )
        signal_id = str(payload.get("signal_id") or payload.get("observation_id") or payload.get("id") or "")
        if not signal_id:
            raise ValueError("V3 notification event requires signal_id or id")
        if event_type not in {"signal", *_OUTCOME_EVENTS}:
            key = _event_key(payload, event_type, signal_id)
            return DispatchResult(key, "unsupported", sent=False, error=f"unsupported event type: {event_type}")
        if event_type == "signal":
            conditions = self._validated_conditions(payload)
            core_ok = conditions is not None and all(
                bool(conditions[name]) for name in ("pump", "reversal", "funding", "funding_change")
            )
            score_ok = conditions is not None and bool(conditions.get("score"))
            selector_ok = self._selector_attestation(payload)
            if not core_ok or (not score_ok and not selector_ok):
                key = _event_key(payload, event_type, signal_id)
                error = "five-condition gate not attested" if not core_ok else "score gate not attested by selector"
                return DispatchResult(key, "rejected", sent=False, error=error)
            payload["conditions"] = conditions
            if selector_ok and not score_ok:
                payload["score_confirmation"] = "runtime selector confirmed"
        if event_type == "signal" and payload.get("outcome"):
            # The signal itself remains the root notification.  Backend outcome
            # hooks should dispatch the nested outcome separately so each state
            # gets its own deterministic key.
            payload.pop("outcome", None)
        key = _event_key(payload, event_type, signal_id)
        if not self.enabled:
            return DispatchResult(key, "disabled", sent=False, attempts=0)
        status, attempts, previous_message, previous_reply, previous_chat = self._reserve(
            event_key=key,
            signal_id=signal_id,
            event_type=event_type,
            payload=payload,
        )
        if status in _TERMINAL:
            return DispatchResult(
                key,
                status,
                sent=status == "sent",
                deduplicated=True,
                message_id=previous_message,
                reply_to_message_id=previous_reply,
                attempts=attempts,
            )
        if status == "in_progress":
            return DispatchResult(key, status, sent=False, attempts=attempts)

        reply_id = _get(payload, "reply_to_message_id")
        reply_chat = None
        if event_type != "signal":
            # Always resolve the persisted root destination, even when the
            # caller supplied a reply id.  A settings/chat change must not
            # send a valid Telegram reply id to a different chat.
            root_reply_id, root_chat = self._signal_message(signal_id)
            reply_chat = root_chat or _get(payload, "chat_id")
            if reply_id is None:
                reply_id = root_reply_id
            if reply_id is None:
                # Lifecycle updates are always threaded.  Keep them pending
                # until the root signal has a durable Telegram message id.
                self._finish(key, status="pending", attempts=attempts, error="awaiting root signal message")
                return DispatchResult(key, "pending", sent=False, attempts=attempts, error="awaiting root signal message")
            if reply_chat is None:
                self._finish(key, status="pending", attempts=attempts, error="awaiting root signal chat")
                return DispatchResult(key, "pending", sent=False, attempts=attempts, error="awaiting root signal chat")
        try:
            if event_type == "signal":
                sent, message_id, chat_id = self._send_signal(payload)
            else:
                sent, message_id, chat_id = self._send_outcome(payload, reply_id, reply_chat)
            if sent:
                self._finish(
                    key,
                    status="sent",
                    attempts=attempts,
                    message_id=message_id,
                    reply_to_message_id=reply_id,
                    chat_id=chat_id or reply_chat,
                )
                return DispatchResult(
                    key,
                    "sent",
                    sent=True,
                    message_id=message_id,
                    reply_to_message_id=reply_id,
                    attempts=attempts,
                )
            error = "notifier returned failure"
        except Exception as exc:  # delivery failures must be retriable
            error = str(exc)
            logger.warning("v3_notification_dispatch_failed", event_key=key, error=error)
        self._finish(key, status="failed", attempts=attempts, error=error, reply_to_message_id=reply_id)
        return DispatchResult(key, "failed", sent=False, reply_to_message_id=reply_id, attempts=attempts, error=error)

    def dispatch_signal(self, event: Mapping[str, Any] | Any) -> DispatchResult:
        payload = _mapping(event)
        payload["event_type"] = "signal"
        return self.dispatch(payload)

    def dispatch_outcome(self, event: Mapping[str, Any] | Any) -> DispatchResult:
        payload = _mapping(event)
        payload.setdefault("event_type", payload.get("outcome_type") or payload.get("status") or "outcome")
        return self.dispatch(payload)

    def retry_pending(self, limit: int = 100) -> list[DispatchResult]:
        """Retry failed/stale outbox rows, typically once after a restart."""
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT payload_json FROM notification_events
                   WHERE status IN ('failed', 'pending', 'sending')
                   ORDER BY updated_at LIMIT ?""",
                [max(1, int(limit))],
            ).fetchall()
        return [self.dispatch(json.loads(row["payload_json"])) for row in rows]

    def get(self, event_key: str) -> dict[str, Any] | None:
        """Read one persisted delivery record for audit/tests."""
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM notification_events WHERE event_key=?", [event_key]
            ).fetchone()
        return dict(row) if row is not None else None
