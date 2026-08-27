"""Integration tests for updater API endpoints."""

from dao_vang.updater.manager import get_update_logs, get_update_status


def test_get_update_status_structure():
    """Verify get_update_status helper returns expected keys."""
    status_dict = get_update_status()
    assert isinstance(status_dict, dict)
    assert "update_available" in status_dict
    assert "current_branch" in status_dict
    assert "local_commit_short" in status_dict
    assert "is_updating" in status_dict
    assert "enabled" in status_dict


def test_get_update_logs_structure():
    """Verify get_update_logs returns list of strings."""
    logs = get_update_logs()
    assert isinstance(logs, list)
