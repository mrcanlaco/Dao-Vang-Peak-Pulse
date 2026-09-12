"""Safety checks for the destructive local-retention script."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="The production retention script runs on Linux",
)
ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prune_old_data.sh"


def _run(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "DAO_VANG_PROJECT_DIR": str(project),
            "DAO_VANG_LOCAL_RETENTION_DAYS": "7",
            "DAO_VANG_MAX_BACKUP_AGE_HOURS": "36",
        }
    )
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )


def _expired_partition(project: Path) -> Path:
    data_dir = project / "data"
    partition = data_dir / "raw" / "BTCUSDT" / "date=2026-01-01"
    partition.mkdir(parents=True)
    (data_dir / "last_successful_backup.json").write_text(
        "{}\n",
        encoding="utf-8",
    )
    old = time.time() - 10 * 24 * 60 * 60
    os.utime(partition, (old, old))
    return partition


def test_prune_is_dry_run_by_default_and_requires_apply(tmp_path: Path):
    project = tmp_path / "project"
    partition = _expired_partition(project)

    preview = _run(project)
    assert preview.returncode == 0
    assert "DRY RUN" in preview.stdout
    assert partition.is_dir()

    applied = _run(project, "--apply")
    assert applied.returncode == 0
    assert "Deleted 1" in applied.stdout
    assert not partition.exists()


def test_prune_refuses_to_run_without_verified_backup_marker(tmp_path: Path):
    project = tmp_path / "project"
    (project / "data" / "raw").mkdir(parents=True)

    result = _run(project, "--apply")
    assert result.returncode != 0
    assert "verified-backup marker is missing" in result.stderr
