"""User-curated tracking watchlist, separate from the scanner input list.

``watchlist.json`` is intentionally kept as the scanner's symbol list.  This
module stores the richer, user-facing lifecycle that starts when a Radar
observation is saved for follow-up.  It is a small atomic JSON store for the
single-user local dashboard; market/signal values are refreshed from the
existing API stores rather than duplicated here.
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dao_vang.domain.time import system_iso
from dao_vang.scanner.tracking_evidence import _timestamp

_STORE_LOCK = threading.RLock()
TRACKING_STATUSES = frozenset({"WATCHING", "IN_POSITION", "CLOSED"})
POSITION_SIDES = frozenset({"LONG", "SHORT"})
_NUMERIC_FIELDS = {
    "source_probability",
    "source_price",
    "source_target_price",
    "entry_price",
    "quantity",
    "notional",
    "leverage",
    "stop_loss",
    "take_profit",
}
_UPDATE_FIELDS = {
    "notifications_enabled",
    "feedback",
    "read_notifications",
    "status",
    "position_side",
    "entry_price",
    "quantity",
    "notional",
    "leverage",
    "stop_loss",
    "take_profit",
    "opened_at",
    "closed_at",
    "notes",
}


def _now_iso() -> str:
    return system_iso(datetime.now(timezone.utc)) or datetime.now(timezone.utc).isoformat()


def normalize_symbol(symbol: object) -> str:
    """Normalize the dashboard's default Binance USDT symbol format."""

    if not isinstance(symbol, str):
        return ""
    value = symbol.strip().upper()
    if value and not value.endswith("USDT"):
        value = f"{value}USDT"
    return value if re.fullmatch(r"[A-Z0-9]{2,30}USDT", value) else ""


def _clean_number(value: Any, field: str) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    if field in {"source_probability"} and not 0.0 <= number <= 1.0:
        raise ValueError("source_probability must be between 0 and 1")
    if field != "source_probability" and number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def calculate_position_metrics(
    *,
    current_price: Any,
    entry_price: Any,
    position_side: object,
    quantity: Any = None,
    notional: Any = None,
    leverage: Any = 1.0,
) -> dict[str, float | None]:
    """Calculate signed return, PnL in USDT, and ROI for a linear position.

    ``notional`` is the preferred PnL basis because it is already expressed in
    USDT. When it is omitted, ``quantity`` is interpreted as base-asset units
    and PnL is calculated from the entry/current price difference. Leverage
    changes ROI through the required margin; it does not multiply PnL again.
    """
    result: dict[str, float | None] = {
        "position_change_pct": None,
        "position_pnl": None,
        "position_roi_pct": None,
    }
    try:
        entry_num = float(entry_price)
        current_num = float(current_price)
        side = str(position_side or "").upper()
        if not math.isfinite(entry_num) or not math.isfinite(current_num) or entry_num <= 0 or current_num <= 0 or side not in POSITION_SIDES:
            return result

        signed_change = (
            (current_num - entry_num) / entry_num
            if side == "LONG"
            else (entry_num - current_num) / entry_num
        )
        result["position_change_pct"] = round(signed_change * 100.0, 2)

        leverage_num = float(leverage or 1.0)
        result["position_roi_pct"] = round(signed_change * 100.0 * leverage_num, 2)

        if notional not in (None, "") and float(notional) > 0:
            result["position_pnl"] = round(signed_change * float(notional), 8)
        elif quantity not in (None, "") and float(quantity) > 0:
            price_delta = current_num - entry_num
            result["position_pnl"] = round(
                price_delta * float(quantity) * (1 if side == "LONG" else -1),
                8,
            )
    except (TypeError, ValueError, OverflowError):
        return result
    return result


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Tracking journal cannot be read; existing data was preserved") from exc
    if not isinstance(raw, list):
        raise ValueError("Invalid tracking journal; existing data was preserved")
    return [item for item in raw if isinstance(item, dict)]


def _write(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


class TrackingWatchlistStore:
    """Atomic JSON persistence for user tracking entries."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def list(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        with _STORE_LOCK:
            return [dict(entry) for entry in _read(self.path)
                    if include_archived or not entry.get("archived_at")]

    def get(self, entry_id: str, *, include_archived: bool = False) -> dict[str, Any] | None:
        wanted = str(entry_id)
        return next((entry for entry in self.list(include_archived=include_archived) if str(entry.get("id")) == wanted), None)

    def add(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        symbol = normalize_symbol(payload.get("symbol"))
        if not symbol:
            raise ValueError("symbol is required")

        source_signal_time = payload.get("source_signal_time")
        if source_signal_time is not None:
            source_signal_time = str(source_signal_time).strip() or None

        with _STORE_LOCK:
            entries = _read(self.path)
            for entry in entries:
                if (
                    normalize_symbol(entry.get("symbol")) == symbol
                    and entry.get("source_signal_time") == source_signal_time
                    and entry.get("status") != "CLOSED"
                    and not entry.get("archived_at")
                ):
                    return dict(entry), False

            now = _now_iso()
            entry: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "symbol": symbol,
                "source": str(payload.get("source") or "manual").lower(),
                "source_prediction_id": str(payload.get("source_prediction_id") or "") or None,
                "source_reason": str(payload.get("source_reason") or ""),
                "source_price_time": payload.get("source_price_time"),
                "source_price_evidence": payload.get("source_price_evidence", "unverified_saved_observation"),
                "source_model_id": payload.get("source_model_id"),
                "source_label_version": payload.get("source_label_version"),
                "source_shadow_mode": payload.get("source_shadow_mode"),
                "source_stop_price": payload.get("source_stop_price"),
                "source_signal_time": source_signal_time,
                "source_probability": _clean_number(payload.get("source_probability"), "source_probability"),
                "source_risk_level": payload.get("source_risk_level"),
                "source_price": _clean_number(payload.get("source_price"), "source_price"),
                "source_target_price": _clean_number(payload.get("source_target_price"), "source_target_price"),
                "source_invalidation_time": payload.get("source_invalidation_time"),
                "status": "WATCHING",
                "position_side": None,
                "entry_price": None,
                "quantity": None,
                "notional": None,
                "leverage": 1.0,
                "stop_loss": None,
                "take_profit": None,
                "opened_at": None,
                "closed_at": None,
                "notes": str(payload.get("notes") or ""),
                "created_at": now,
                "updated_at": now,
                "archived_at": None,
                "history": [{"at": now, "event": "SAVED", "changes": {}}],
                "notifications_enabled": True,
                "notifications": [],
                "checkpoints": {},
                "paper_trade": None,
                "feedback": None,
            }
            entries.append(entry)
            _write(self.path, entries)
            return dict(entry), True

    def update(self, entry_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        unknown = set(payload) - _UPDATE_FIELDS
        if unknown:
            raise ValueError(f"Unsupported fields: {', '.join(sorted(unknown))}")

        with _STORE_LOCK:
            entries = _read(self.path)
            for entry in entries:
                if str(entry.get("id")) != str(entry_id):
                    continue
                if entry.get("archived_at") and set(payload) - {"feedback", "read_notifications"}:
                    raise ValueError("Archived observations cannot be edited")
                if "notifications_enabled" in payload:
                    if not isinstance(payload["notifications_enabled"], bool):
                        raise ValueError("notifications_enabled must be boolean")
                    entry["notifications_enabled"] = payload["notifications_enabled"]
                if "feedback" in payload:
                    if payload["feedback"] not in (None, "USEFUL", "NOISY", "UNCLEAR"):
                        raise ValueError("Invalid feedback")
                    entry["feedback"] = payload["feedback"]
                if "read_notifications" in payload:
                    if payload["read_notifications"] is not True:
                        raise ValueError("read_notifications must be true")
                    for notification in entry.get("notifications", []):
                        notification["read"] = True

                if "status" in payload:
                    status = str(payload["status"]).upper()
                    if status not in TRACKING_STATUSES:
                        raise ValueError(f"status must be one of {sorted(TRACKING_STATUSES)}")
                    entry["status"] = status
                    if status == "CLOSED" and not entry.get("closed_at"):
                        entry["closed_at"] = _now_iso()
                if "position_side" in payload:
                    side = payload["position_side"]
                    entry["position_side"] = None if side in (None, "") else str(side).upper()
                    if entry["position_side"] is not None and entry["position_side"] not in POSITION_SIDES:
                        raise ValueError("position_side must be LONG or SHORT")
                for field in _NUMERIC_FIELDS:
                    if field in payload:
                        entry[field] = _clean_number(payload[field], field)
                for field in {"opened_at", "closed_at", "notes"}:
                    if field in payload:
                        entry[field] = payload[field]

                if entry.get("status") == "IN_POSITION":
                    if not entry.get("position_side") or entry.get("entry_price") is None:
                        raise ValueError("IN_POSITION requires position_side and entry_price")
                    if not entry.get("opened_at"):
                        entry["opened_at"] = _now_iso()
                entry["updated_at"] = _now_iso()
                entry.setdefault("history", []).append({
                    "at": entry["updated_at"], "event": "UPDATED",
                    "changes": {field: entry.get(field) for field in payload},
                })
                _write(self.path, entries)
                return dict(entry)
        return None

    def remove(self, entry_id: str) -> bool:
        """Stop following without erasing the original observation or journal."""
        with _STORE_LOCK:
            entries = _read(self.path)
            for entry in entries:
                if str(entry.get("id")) == str(entry_id) and not entry.get("archived_at"):
                    if (entry.get("paper_trade") or {}).get("status") == "OPEN":
                        raise ValueError("Close the paper trade before archiving")
                    now = _now_iso()
                    entry["archived_at"] = now
                    entry["status"] = "CLOSED"
                    entry["updated_at"] = now
                    entry.setdefault("history", []).append({
                        "at": now, "event": "ARCHIVED", "changes": {},
                    })
                    _write(self.path, entries)
                    return True
            return False

    def monitor(self, entry_id: str, observation: dict[str, Any], checkpoints: dict[str, Any], *, now: datetime) -> None:
        """Persist milestones once; notify only meaningful changes, with a cooldown."""
        with _STORE_LOCK:
            entries = _read(self.path)
            for entry in entries:
                if entry["id"] != entry_id:
                    continue
                previous = entry.get("monitor") or {}
                events: list[tuple[str, str]] = []
                for horizon, result in checkpoints.items():
                    old = entry.setdefault("checkpoints", {}).get(horizon, {})
                    if old.get("status") == "READY":
                        continue
                    entry["checkpoints"][horizon] = result
                    if result.get("status") != old.get("status") and result.get("status") in {"READY", "MISSING"}:
                        events.append((f"CHECKPOINT_{horizon}_{result['status']}", f"Kết quả {horizon} giờ: " + ("đã đủ dữ liệu" if result['status'] == 'READY' else "chưa đủ dữ liệu")))
                fresh = observation.get("market_data_status") == "FRESH"
                if previous and observation.get("market_data_status") != previous.get("market_data_status"):
                    events.append(("DATA_FRESH" if fresh else "DATA_STALE", "Giá đã cập nhật trở lại" if fresh else "Giá đang cũ hoặc thiếu; cần kiểm tra trước khi đánh giá"))
                anchor = previous.get("notification_price") or previous.get("current_price")
                price = observation.get("current_price")
                last_notice = _timestamp(previous.get("price_notified_at"))
                if fresh and anchor and price and abs(price / anchor - 1) >= .05 and (last_notice is None or (now - last_notice).total_seconds() >= 7200):
                    events.append(("PRICE_MOVE", f"Giá thay đổi {(price / anchor - 1) * 100:+.1f}% so với mốc theo dõi gần nhất"))
                    anchor, last_notice = price, now
                entry["monitor"] = {**observation, "checked_at": now.isoformat(),
                                    "notification_price": anchor or (price if fresh else None),
                                    "price_notified_at": last_notice.isoformat() if last_notice else None}
                entry["monitor_checked_at"] = now.isoformat()
                if entry.get("notifications_enabled", True) and not entry.get("archived_at") and entry.get("status") != "CLOSED":
                    for code, message in events:
                        notifications = entry.setdefault("notifications", [])
                        same_code = next((n for n in reversed(notifications) if n["code"] == code), None)
                        last_code_at = _timestamp(same_code["at"]) if same_code else None
                        if code.startswith("DATA_") and last_code_at and (now - last_code_at).total_seconds() < 7200:
                            continue
                        if code.startswith("CHECKPOINT") and any(n["code"] == code for n in notifications):
                            continue
                        if notifications and notifications[-1]["code"] == code and code != "PRICE_MOVE":
                            continue
                        notifications.append({"id": uuid.uuid4().hex, "at": now.isoformat(), "code": code, "message": message, "read": False})
                _write(self.path, entries)
                return

    def paper(self, entry_id: str, *, action: str, quote: dict[str, Any], now: datetime,
              side: str = "SHORT", notional: float = 1000, fee_bps: float = 5,
              slippage_bps: float = 5, funding: dict[str, Any] | None = None) -> dict[str, Any]:
        with _STORE_LOCK:
            entries = _read(self.path)
            entry = next((item for item in entries if item["id"] == entry_id), None)
            if entry is None:
                raise ValueError("Tracking item not found")
            trade = entry.get("paper_trade")
            if action == "open" and trade:
                return dict(entry)
            if action == "close" and trade and trade["status"] == "CLOSED":
                return dict(entry)
            if action not in {"open", "close"} or entry.get("archived_at"):
                raise ValueError("Paper action unavailable")
            price = quote.get("current_price")
            at = _timestamp(quote.get("last_market_update"))
            if not price or not math.isfinite(float(price)) or float(price) <= 0 or at is None or not 0 <= (now - at).total_seconds() <= 120:
                raise ValueError("A verified price less than two minutes old is required")
            if action == "open":
                if side not in POSITION_SIDES or not all(math.isfinite(float(v)) for v in (notional, fee_bps, slippage_bps)):
                    raise ValueError("Invalid simulation parameters")
                if not 1 <= notional <= 1_000_000 or not 0 <= fee_bps <= 100 or not 0 <= slippage_bps <= 100:
                    raise ValueError("Simulation size or costs out of range")
                fill = price * (1 + slippage_bps / 10_000 * (1 if side == "LONG" else -1))
                entry["paper_trade"] = {"status": "OPEN", "side": side, "notional": notional,
                                        "quantity": notional / fill, "entry_price": fill, "entry_quote": price,
                                        "opened_at": now.isoformat(), "quote_time": at.isoformat(),
                                        "fee_bps": fee_bps, "slippage_bps": slippage_bps,
                                        "entry_fee": notional * fee_bps / 10_000,
                                        "funding": {"status": "PENDING", "cashflow": None}, "net_pnl": None}
            else:
                if not trade or trade["status"] != "OPEN":
                    raise ValueError("No open paper trade")
                fill = price * (1 + trade["slippage_bps"] / 10_000 * (-1 if trade["side"] == "LONG" else 1))
                gross = (fill - trade["entry_price"]) * trade["quantity"] * (1 if trade["side"] == "LONG" else -1)
                fees = trade["entry_fee"] + fill * trade["quantity"] * trade["fee_bps"] / 10_000
                settlement = funding or {"status": "MISSING", "cashflow": None}
                trade.update(status="CLOSED", closed_at=now.isoformat(), exit_price=fill, exit_quote=price,
                             exit_quote_time=at.isoformat(), gross_pnl=gross, fees=fees,
                             funding=settlement, net_pnl=gross - fees + settlement["cashflow"] if settlement.get("status") == "VERIFIED" else None)
            entry.setdefault("history", []).append({"at": now.isoformat(), "event": "PAPER_OPENED" if action == "open" else "PAPER_CLOSED", "changes": dict(entry["paper_trade"])})
            _write(self.path, entries)
            return dict(entry)

    def reconcile_funding(self, entry_id: str, funding: dict[str, Any], *, now: datetime) -> dict[str, Any]:
        with _STORE_LOCK:
            entries = _read(self.path)
            entry = next((item for item in entries if item['id'] == entry_id), None)
            if entry is None:
                raise ValueError("Tracking item not found")
            trade = entry.get('paper_trade')
            if not trade or trade['status'] != 'CLOSED':
                raise ValueError("No closed paper trade")
            if trade['funding'].get('status') != 'VERIFIED':
                trade['funding'] = funding
                trade['funding_checked_at'] = now.isoformat()
                if funding.get('status') == 'VERIFIED':
                    trade['net_pnl'] = trade['gross_pnl'] - trade['fees'] + funding['cashflow']
                    entry.setdefault('history', []).append({'at': now.isoformat(), 'event': 'FUNDING_UPDATED', 'changes': dict(funding)})
                _write(self.path, entries)
            return dict(entry)
