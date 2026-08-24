import atexit
import os
import shutil
import tempfile
import threading
import time
from pathlib import Path

import duckdb

_SNAPSHOT_TTL_SECONDS = max(
    5.0, float(os.getenv("DAO_VANG_DUCKDB_SNAPSHOT_TTL_SECONDS", "30"))
)
_SNAPSHOT_LOCK = threading.Lock()
_SNAPSHOT_CACHE: dict[str, tuple[Path, float]] = {}
_SNAPSHOT_FALLBACK_WARNED: set[str] = set()


def _duckdb_memory_limit() -> str:
    """Return a conservative, configurable memory limit for DuckDB."""

    value = os.getenv("DAO_VANG_DUCKDB_MEMORY_LIMIT", "2GB").strip().upper()
    units = ("B", "KB", "MB", "GB", "TB")
    for unit in units:
        number = value[: -len(unit)] if unit else value
        if value.endswith(unit) and number.replace(".", "", 1).isdigit():
            return value
    return "2GB"


def _duckdb_thread_count() -> int:
    try:
        return max(1, min(8, int(os.getenv("DAO_VANG_DUCKDB_THREADS", "2"))))
    except ValueError:
        return 2


def configure_connection(conn: duckdb.DuckDBPyConnection, db_path: str) -> None:
    """Bound DuckDB's resource usage so one query cannot consume the host."""

    # DuckDB otherwise inherits the host timezone. Aware
    # UTC datetimes inserted into TIMESTAMP columns are then converted to
    # local wall time, which makes API age calculations appear 7 hours in the
    # future. Keep all database timestamps in UTC at the storage boundary.
    try:
        conn.execute("SET TimeZone='UTC'")
    except duckdb.Error:
        pass

    db_file = Path(db_path).resolve() if db_path != ":memory:" else None
    temp_dir = (
        db_file.parent / "duckdb_temp"
        if db_file is not None
        else Path("data/duckdb_temp").resolve()
    )
    temp_dir.mkdir(parents=True, exist_ok=True)
    try:
        conn.execute(f"PRAGMA temp_directory='{temp_dir.as_posix()}'")
    except duckdb.Error as exc:
        # DuckDB 1.5 rejects changing the temporary directory after a
        # connection/database has already used its current one. This can
        # happen when the live writer and read-only API snapshots use the
        # same database from different path representations. Keep the
        # existing setting and still apply the memory/thread limits below.
        if "Cannot switch temporary directory" not in str(exc):
            raise
    conn.execute(f"PRAGMA memory_limit='{_duckdb_memory_limit()}'")
    conn.execute(f"PRAGMA threads={_duckdb_thread_count()}")
    try:
        conn.execute("PRAGMA preserve_insertion_order=false")
    except duckdb.Error:
        pass


def _snapshot_path(source: Path) -> Path:
    return source.with_name(f".{source.name}.{os.getpid()}.ro_copy")


def _cleanup_snapshots() -> None:
    for path, _ in tuple(_SNAPSHOT_CACHE.values()):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


atexit.register(_cleanup_snapshots)


def _get_read_snapshot(source: Path) -> Path:
    """Create at most one short-lived read snapshot per process.

    Windows can reject a read-only open while another process owns the
    DuckDB writer lock. The previous workaround copied the whole database for
    every API query. A process-local snapshot bounds that copy rate.
    """

    source = source.resolve()
    key = str(source)
    now = time.monotonic()
    target = _snapshot_path(source)

    with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_CACHE.get(key)
        if cached and cached[0].exists() and now - cached[1] < _SNAPSHOT_TTL_SECONDS:
            return cached[0]

        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{source.name}.{os.getpid()}.",
            suffix=".ro_copy.tmp",
            dir=source.parent,
        )
        os.close(fd)
        temporary = Path(temporary_name)
        try:
            shutil.copy2(source, temporary)
            try:
                os.replace(temporary, target)
            except OSError:
                # An in-flight request may still hold the previous snapshot.
                # Reuse it instead of copying again or failing the request.
                if not target.exists():
                    raise
                temporary.unlink(missing_ok=True)
            _SNAPSHOT_CACHE[key] = (target, now)
            return target
        except Exception:
            temporary.unlink(missing_ok=True)
            raise


def open_read_only_connection(
    db_path: Path | str,
    *,
    prefer_snapshot: bool = False,
) -> duckdb.DuckDBPyConnection:
    """Open a read-only connection with a bounded lock fallback.

    Always attempts a direct read-only connection first (instantaneous on Linux
    and multi-reader POSIX environments). Falls back to a process-local snapshot
    copy only when a lock collision occurs (e.g. Windows exclusive file locks).
    """

    path = str(db_path)
    try:
        conn = duckdb.connect(path, read_only=True)
        configure_connection(conn, path)
        return conn
    except (duckdb.IOException, duckdb.Error, OSError):
        source = Path(path)
        try:
            snapshot = _get_read_snapshot(source)
            conn = duckdb.connect(str(snapshot), read_only=True)
            configure_connection(conn, str(snapshot))
            return conn
        except (OSError, duckdb.Error):
            fallback_candidates = [
                _snapshot_path(source),
                source.with_name(f"{source.name}.ro_copy"),
            ]
            fallback_candidates.extend(
                source.parent.glob(f".{source.name}.*.ro_copy")
            )
            for fallback in sorted(
                {candidate.resolve() for candidate in fallback_candidates if candidate.exists()},
                key=lambda candidate: candidate.stat().st_mtime,
                reverse=True,
            ):
                try:
                    conn = duckdb.connect(str(fallback), read_only=True)
                    configure_connection(conn, str(fallback))
                    return conn
                except (OSError, duckdb.Error):
                    continue
            raise


class DuckDBQueryLayer:
    """A thin wrapper around DuckDB for querying normalized Parquet datasets."""

    def __init__(
        self,
        db_path: Path | str = ":memory:",
        *,
        read_only: bool = False,
        connect_retries: int = 30,
    ):
        self._db_path = str(db_path)
        self._temporary_copy: Path | None = None
        attempts = max(1, int(connect_retries))

        if read_only:
            self.conn = open_read_only_connection(self._db_path)
        else:
            last_error: duckdb.IOException | None = None
            for attempt in range(attempts):
                try:
                    self.conn = duckdb.connect(self._db_path, read_only=False)
                    break
                except duckdb.IOException as exc:
                    last_error = exc
                    if attempt + 1 < attempts:
                        time.sleep(0.5)
            else:
                raise last_error or duckdb.IOException(
                    f"Could not open DuckDB database: {self._db_path}"
                )
            configure_connection(self.conn, self._db_path)

    def query(self, sql: str) -> duckdb.DuckDBPyRelation:
        """Execute a SQL query and return a DuckDB relation."""
        return self.conn.query(sql)

    def register_parquet_view(self, view_name: str, parquet_path: Path | str):
        """Register a Parquet file or glob pattern as a view."""
        sql = (
            f"CREATE OR REPLACE VIEW {view_name} "
            f"AS SELECT * FROM read_parquet('{parquet_path}', union_by_name=true)"
        )
        self.conn.execute(sql)

    def close(self):
        """Close the DuckDB connection."""
        try:
            self.conn.close()
        finally:
            if self._temporary_copy is not None:
                self._temporary_copy.unlink(missing_ok=True)
                self._temporary_copy = None
