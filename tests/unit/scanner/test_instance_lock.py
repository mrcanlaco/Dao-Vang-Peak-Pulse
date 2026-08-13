from __future__ import annotations

import pytest

from dao_vang.scanner.instance_lock import ScannerAlreadyRunning, ScannerInstanceLock


def test_instance_lock_blocks_second_owner_and_releases(tmp_path):
    path = tmp_path / "scanner.lock"
    first = ScannerInstanceLock(path)
    second = ScannerInstanceLock(path)

    first.acquire()
    try:
        with pytest.raises(ScannerAlreadyRunning):
            second.acquire()
    finally:
        first.release()

    second.acquire()
    second.release()
