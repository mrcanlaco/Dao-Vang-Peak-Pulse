"""Unit tests for dao_vang.updater module."""

from pathlib import Path
from unittest.mock import patch

from dao_vang.config.settings import AppSettings, UpdaterConfig
from dao_vang.updater.auto_updater import AutoUpdaterDaemon
from dao_vang.updater.manager import (
    CommitInfo,
    UpdateManager,
    UpdateResult,
    UpdateStatus,
)


def test_updater_config_defaults():
    """Verify default values in UpdaterConfig."""
    config = UpdaterConfig()
    assert config.enabled is False
    assert config.poll_interval_minutes == 10
    assert config.remote_name == "origin"
    assert config.branch_name == "main"
    assert config.auto_restart_services is False
    assert config.rebuild_frontend is True
    assert config.telegram_notify is False
    assert config.auto_deploy_remote is False


def test_app_settings_includes_updater():
    """Verify AppSettings initializes with updater configuration."""
    settings = AppSettings()
    assert hasattr(settings, "updater")
    assert isinstance(settings.updater, UpdaterConfig)


def test_commit_info_dataclass():
    """Verify CommitInfo serialization."""
    info = CommitInfo(
        hash="abc1234567890",
        short_hash="abc1234",
        author="mrcanlaco",
        date="2026-08-25",
        message="feat(scanner): test feature",
        type="feat",
        scope="scanner",
    )
    d = info.to_dict()
    assert d["hash"] == "abc1234567890"
    assert d["short_hash"] == "abc1234"
    assert d["type"] == "feat"
    assert d["scope"] == "scanner"


def test_update_manager_parse_commit_type():
    """Verify conventional commit message parsing."""
    manager = UpdateManager()
    c_type, scope = manager._parse_commit_type("feat(updater): 1-click update support")
    assert c_type == "feat"
    assert scope == "updater"

    c_type2, scope2 = manager._parse_commit_type("fix: resolve lock issue")
    assert c_type2 == "fix"
    assert scope2 == ""

    c_type3, scope3 = manager._parse_commit_type("Random commit message")
    assert c_type3 == "other"
    assert scope3 == ""


@patch.object(UpdateManager, "_run_cmd")
def test_check_for_updates_up_to_date(mock_run_cmd):
    """Test check_for_updates when repo is already up to date."""
    manager = UpdateManager()

    # Simulate git commands
    def side_effect(cmd, **kwargs):
        if isinstance(cmd, list):
            if "rev-parse" in cmd and "--abbrev-ref" in cmd:
                return (0, "main", "")
            if "rev-parse" in cmd and "--short" in cmd and "HEAD" in cmd:
                return (0, "abc1234", "")
            if "rev-parse" in cmd and "HEAD" in cmd:
                return (0, "abc1234567890", "")
            if "log" in cmd and "HEAD" in cmd:
                return (0, "Current commit", "")
            if "fetch" in cmd:
                return (0, "", "")
            if "rev-parse" in cmd and "origin/main" in cmd:
                return (0, "abc1234567890", "")
            if "rev-list" in cmd:
                return (0, "0\t0", "")
        return (0, "", "")

    mock_run_cmd.side_effect = side_effect

    status = manager.check_for_updates()
    assert isinstance(status, UpdateStatus)
    assert status.update_available is False
    assert status.commits_behind == 0
    assert status.local_commit_short == "abc1234"


@patch.object(UpdateManager, "_run_cmd")
def test_check_for_updates_behind(mock_run_cmd):
    """Test check_for_updates when repo is behind remote."""
    manager = UpdateManager()

    def side_effect(cmd, **kwargs):
        if isinstance(cmd, list):
            if "rev-parse" in cmd and "--abbrev-ref" in cmd:
                return (0, "main", "")
            if "rev-parse" in cmd and "--short" in cmd and "HEAD" in cmd:
                return (0, "abc1234", "")
            if "rev-parse" in cmd and "HEAD" in cmd:
                return (0, "abc1234567890", "")
            if "log" in cmd and "HEAD" in cmd:
                return (0, "Local commit", "")
            if "fetch" in cmd:
                return (0, "", "")
            if "rev-parse" in cmd and "--short" in cmd and "origin/main" in cmd:
                return (0, "def5678", "")
            if "rev-parse" in cmd and "origin/main" in cmd:
                return (0, "def5678901234", "")
            if "log" in cmd and "origin/main" in cmd:
                return (0, "New remote commit", "")
            if "rev-list" in cmd:
                return (0, "0\t1", "")
            if "git" in cmd and "HEAD..origin/main" in cmd and "format:" in str(cmd):
                return (0, "def5678901234\x1fdef5678\x1fmrcanlaco\x1f2026-08-25\x1ffeat: new feature", "")
            if "diff" in cmd:
                return (0, "pyproject.toml\nfrontend/src/App.tsx", "")
        return (0, "", "")

    mock_run_cmd.side_effect = side_effect

    status = manager.check_for_updates()
    assert isinstance(status, UpdateStatus)
    assert status.update_available is True
    assert status.commits_behind == 1
    assert status.remote_commit_short == "def5678"
    assert status.has_dependency_changes is True
    assert status.has_frontend_changes is True
    assert len(status.new_commits) == 1
    assert status.new_commits[0]["short_hash"] == "def5678"


@patch.object(UpdateManager, "_fetch_remote_github_api")
@patch.object(UpdateManager, "_run_cmd")
def test_check_for_updates_fetch_failed_fallback_success(mock_run_cmd, mock_fetch_gh):
    """When git fetch fails (e.g. read-only filesystem), fallback to API/ls-remote."""
    manager = UpdateManager()

    def side_effect(cmd, **kwargs):
        if isinstance(cmd, list):
            if "rev-parse" in cmd and "--abbrev-ref" in cmd:
                return (0, "main", "")
            if "rev-parse" in cmd and "--short" in cmd and "HEAD" in cmd:
                return (0, "d1cecc2", "")
            if "rev-parse" in cmd and "HEAD" in cmd:
                return (0, "d1cecc269d89c0ed62d2ea11b15611686dd087b8", "")
            if "log" in cmd and "HEAD" in cmd:
                return (0, "fix: old commit", "")
            if "fetch" in cmd:
                return (1, "", "cannot open '.git/FETCH_HEAD': Read-only file system")
            if "ls-remote" in cmd:
                return (0, "133f7ba410ca20fe507f5bdb66fa5ec0b3bc866f\trefs/heads/main", "")
        return (0, "", "")

    mock_run_cmd.side_effect = side_effect
    mock_fetch_gh.return_value = (
        "133f7ba410ca20fe507f5bdb66fa5ec0b3bc866f",
        "133f7ba",
        "feat: new commit",
        1,
        [{
            "hash": "133f7ba410ca20fe507f5bdb66fa5ec0b3bc866f",
            "short_hash": "133f7ba",
            "author": "Mrcanlaco",
            "date": "2026-08-28T20:09:55Z",
            "message": "feat: new commit",
            "type": "feat",
            "scope": "",
        }],
        False,
        True,
        None,
    )

    status = manager.check_for_updates()
    assert isinstance(status, UpdateStatus)
    assert status.update_available is True
    assert status.commits_behind == 1
    assert status.remote_commit_short == "133f7ba"
    assert status.has_frontend_changes is True
    assert status.error is None
    assert len(status.new_commits) == 1

@patch.object(UpdateManager, "_run_cmd")
@patch.object(UpdateManager, "_restart_services_windows")
@patch.object(UpdateManager, "_send_telegram_notification")
def test_apply_update_success(mock_tg, mock_restart, mock_run_cmd):
    """Test apply_update flow succeeding."""
    mock_restart.return_value = (True, ["Restarted task"])
    mock_tg.return_value = True

    def side_effect(cmd, **kwargs):
        if isinstance(cmd, list):
            if "rev-parse" in cmd:
                return (0, "new1234", "")
            if "fetch" in cmd or "pull" in cmd:
                return (0, "Already up to date.", "")
            if "status" in cmd:
                return (0, "", "")
            if "log" in cmd:
                return (0, "Commit message", "")
            if "rev-list" in cmd:
                return (0, "0\t0", "")
        return (0, "", "")

    mock_run_cmd.side_effect = side_effect

    manager = UpdateManager(settings=AppSettings(updater={"enabled": True}))
    res = manager.apply_update(restart_services=True, rebuild_frontend=False, notify_telegram=False)

    assert isinstance(res, UpdateResult)
    assert res.success is True
    assert res.current_commit == "new1234"


def _update_available_status() -> UpdateStatus:
    return UpdateStatus(
        update_available=True,
        current_branch="main",
        local_commit="old123456789",
        local_commit_short="old1234",
        local_commit_message="Old commit",
        remote_commit="new123456789",
        remote_commit_short="new1234",
        remote_commit_message="New commit",
        commits_behind=1,
        commits_ahead=0,
    )


@patch.object(UpdateManager, "check_for_updates")
@patch.object(UpdateManager, "_restart_services_windows")
def test_apply_update_stops_and_restores_upstream_file_on_stash_conflict(
    mock_restart,
    mock_check,
):
    """A stash conflict must never reach frontend build or service restart."""
    mock_check.return_value = _update_available_status()
    commands: list[list[str]] = []
    stash_ref_reads = 0

    def side_effect(cmd, **kwargs):
        nonlocal stash_ref_reads
        commands.append(cmd)
        if cmd == ["git", "status", "--porcelain"]:
            return (0, " M frontend/dist/index.html", "")
        if cmd[:3] == ["git", "stash", "push"]:
            return (0, "Saved working directory and index state", "")
        if cmd == ["git", "rev-parse", "--verify", "--quiet", "refs/stash"]:
            stash_ref_reads += 1
            if stash_ref_reads == 1:
                return (1, "", "")
            return (0, "stash123456789", "")
        if cmd[:2] in (["git", "fetch"], ["git", "pull"]):
            return (0, "Updated", "")
        if cmd[:3] == ["git", "stash", "apply"]:
            return (1, "CONFLICT (content): Merge conflict", "")
        if cmd == ["git", "diff", "--name-only", "--diff-filter=U"]:
            return (0, "frontend/dist/index.html", "")
        if cmd[:3] == ["git", "restore", "--source=HEAD"]:
            return (0, "", "")
        if cmd == ["git", "rev-parse", "--short", "HEAD"]:
            return (0, "new1234", "")
        return (0, "", "")

    manager = UpdateManager(settings=AppSettings(updater={"enabled": True}))
    with patch.object(manager, "_run_cmd", side_effect=side_effect):
        result = manager.apply_update(
            restart_services=True,
            rebuild_frontend=True,
            notify_telegram=False,
        )

    assert result.success is False
    assert "stash" in (result.error or "").lower()
    assert [
        "git",
        "restore",
        "--source=HEAD",
        "--staged",
        "--worktree",
        "--",
        "frontend/dist/index.html",
    ] in commands
    assert not any(cmd[:3] == ["npm", "run", "build"] for cmd in commands)
    mock_restart.assert_not_called()


def test_frontend_conflict_marker_scan_covers_source_and_build(tmp_path: Path):
    """Both source HTML and the served build are release blockers."""
    source = tmp_path / "frontend" / "index.html"
    build = tmp_path / "frontend" / "dist" / "index.html"
    build.parent.mkdir(parents=True)
    source.write_text("<!doctype html><html></html>\n", encoding="utf-8")
    build.write_text(
        "<<<<<<< Updated upstream\n<html></html>\n=======\n<html></html>\n"
        ">>>>>>> Stashed changes\n",
        encoding="utf-8",
    )

    manager = UpdateManager(repo_root=tmp_path)

    assert manager._frontend_files_with_conflict_markers() == [
        "frontend/dist/index.html"
    ]


def test_auto_updater_daemon_init():
    """Verify AutoUpdaterDaemon instantiation."""
    daemon = AutoUpdaterDaemon(poll_interval_minutes=5)
    assert daemon.poll_interval_seconds == 300
    assert daemon._running is False
