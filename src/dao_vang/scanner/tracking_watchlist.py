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
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dao_vang.domain.time import system_iso

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
    return value


def _clean_number(value: object, field: str) -> float | None:
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
    if field in {"quantity", "notional", "leverage"} and number < 0:
        raise ValueError(f"{field} must not be negative")
    return number


def calculate_position_metrics(
    *,
    current_price: object,
    entry_price: object,
    position_side: object,
    quantity: object = None,
    notional: object = None,
    leverage: object = 1.0,
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
        if entry_num <= 0 or current_num < 0 or side not in POSITION_SIDES:
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
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
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

    def list(self) -> list[dict[str, Any]]:
        with _STORE_LOCK:
            return [dict(entry) for entry in _read(self.path)]

    def get(self, entry_id: str) -> dict[str, Any] | None:
        wanted = str(entry_id)
        return next((entry for entry in self.list() if str(entry.get("id")) == wanted), None)

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
                ):
                    return dict(entry), False

            now = _now_iso()
            entry: dict[str, Any] = {
                "id": uuid.uuid4().hex,
                "symbol": symbol,
                "source": str(payload.get("source") or "manual").lower(),
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
                _write(self.path, entries)
                return dict(entry)
        return None

    def remove(self, entry_id: str) -> bool:
        with _STORE_LOCK:
            entries = _read(self.path)
            kept = [entry for entry in entries if str(entry.get("id")) != str(entry_id)]
            if len(kept) == len(entries):
                return False
            _write(self.path, kept)
            return True
