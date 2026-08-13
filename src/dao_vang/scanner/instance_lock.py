"""Single-process guard for one scanner deployment.

The scanner owns a DuckDB writer connection.  A second scanner process using
the same data directory can corrupt the operational picture and will usually
fail with a DuckDB file-lock error.  This module uses an OS-level advisory
lock, so the lock is released automatically when the owning process dies.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import BinaryIO

from dao_vang.domain.time import system_now


class ScannerAlreadyRunning(RuntimeError):
    """Raised when another scanner already owns the deployment lock."""


class ScannerInstanceLock:
    """Hold an advisory lock for the lifetime of one scanner process."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._handle: BinaryIO | None = None

    def acquire(self) -> None:
        if self._handle is not None:
            raise RuntimeError("scanner instance lock is already held")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            # Windows byte-range locking requires an existing byte.  The same
            # byte is sufficient as a cross-process mutex on every platform.
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            self._lock_file(handle)
            handle.seek(0)
            handle.truncate()
            handle.write(
                json.dumps(
                    {
                        "pid": os.getpid(),
                        "started_at": system_now().isoformat(),
                    },
                    sort_keys=True,
                ).encode("utf-8")
            )
            handle.flush()
            self._handle = handle
        except OSError as exc:
            handle.close()
            owner = self._read_owner()
            detail = f" ({owner})" if owner else ""
            raise ScannerAlreadyRunning(
                f"another scanner already owns {self.path}{detail}"
            ) from exc
        except Exception:
            handle.close()
            raise

    def release(self) -> None:
        handle = self._handle
        self._handle = None
        if handle is None:
            return
        try:
            self._unlock_file(handle)
        finally:
            handle.close()

    def __enter__(self) -> "ScannerInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.release()

    @staticmethod
    def _lock_file(handle: BinaryIO) -> None:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    @staticmethod
    def _unlock_file(handle: BinaryIO) -> None:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def _read_owner(self) -> str:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("pid"):
                return (
                    f"pid={payload['pid']} "
                    f"started_at={payload.get('started_at', '?')}"
                )
        except (OSError, ValueError, json.JSONDecodeError):
            pass
        return ""
