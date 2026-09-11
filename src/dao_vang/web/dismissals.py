"""Durable UI dismissals without writing to the scanner-owned DuckDB."""
import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


class SignalDismissals:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    @staticmethod
    def key(symbol: str, signal_time: str) -> str:
        stamp = datetime.fromisoformat(signal_time.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return symbol.upper() + "|" + stamp.astimezone(timezone.utc).isoformat()

    def _read(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Invalid dismissal state")
        return value

    def dismiss(self, symbol: str, signal_time: str) -> None:
        key = self.key(symbol, signal_time)
        now = datetime.now(timezone.utc)
        with self._lock:
            items = self._read()
            cutoff = (now - timedelta(days=8)).isoformat()
            items = {key: stamp for key, stamp in items.items() if stamp >= cutoff}
            items[key] = now.isoformat()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(items), encoding="utf-8")
            temporary.replace(self.path)

    def filter(self, signals: list[dict]) -> list[dict]:
        with self._lock:
            items = self._read()
        return [signal for signal in signals
                if self.key(signal["symbol"], str(signal["signal_time"])) not in items]
