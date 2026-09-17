"""One source-file inventory per pass, with reusable legacy backfill metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import pyarrow.parquet as pq


@lru_cache(maxsize=65536)
def _backfill_metadata(path: str, size: int, modified: int) -> tuple[str | None, float | None]:
    """Old hashed filenames have no symbol: inspect their footer once per version.

    Unknown/mixed/corrupt files stay eligible, never silently discard evidence.
    Size + nanosecond mtime invalidate this process-local cache on replacement.
    """
    try:
        metadata = pq.read_metadata(path)
        names = metadata.schema.names
        symbols, collected = set(), []
        for row_index in range(metadata.num_row_groups):
            group = metadata.row_group(row_index)
            symbol = group.column(names.index("symbol")).statistics
            receipt = group.column(names.index("collected_at")).statistics
            if not symbol or not symbol.has_min_max or symbol.min != symbol.max:
                return None, None
            symbols.add(str(symbol.min))
            if not receipt or not receipt.has_min_max or receipt.null_count:
                return None, None
            value = receipt.max
            if isinstance(value, datetime):
                collected.append(value.replace(tzinfo=value.tzinfo or timezone.utc).timestamp())
            else:
                return None, None
        if len(symbols) == 1 and collected:
            return symbols.pop(), max(collected)
    except (OSError, ValueError, TypeError):
        pass
    return None, None


class SourceCatalog:
    """Inventory each kind once; register new downloads without rescanning it."""

    def __init__(self, data_dir: Path):
        self.root = data_dir.resolve() / "normalized"
        self._kinds: dict[str, dict[str | None, list[tuple[str, float | None]]]] = {}

    def _load(self, kind: str) -> dict[str | None, list[tuple[str, float | None]]]:
        if kind not in self._kinds:
            groups: dict[str | None, list[tuple[str, float | None]]] = {}
            for path in (self.root / kind).rglob("*.parquet"):
                symbol, collected = None, None
                parts = path.stem.split("_", 3)
                if len(parts) == 4 and parts[0] == "scan" and parts[1].isdigit() and parts[2].isdigit():
                    symbol, collected = parts[3], float(parts[1])
                elif path.name.startswith("v3bf_"):
                    try:
                        stat = path.stat()
                        symbol, collected = _backfill_metadata(path.as_posix(), stat.st_size, stat.st_mtime_ns)
                    except OSError:
                        pass
                groups.setdefault(symbol, []).append((path.as_posix(), collected))
            self._kinds[kind] = groups
        return self._kinds[kind]

    def paths(self, kind: str, symbol: str, cutoff: float) -> list[str]:
        groups = self._load(kind)
        return [path for path, collected in groups.get(symbol, []) + groups.get(None, [])
                if collected is None or collected >= cutoff]

    def add(self, kind: str, symbol: str, path: Path) -> None:
        if kind in self._kinds:
            value = path.resolve().as_posix()
            rows = self._kinds[kind].setdefault(symbol, [])
            if not any(existing == value for existing, _ in rows):
                rows.append((value, None))
