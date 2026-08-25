"""Unit tests for version history and GitHub development timeline extraction."""

from pathlib import Path
import pytest

from dao_vang.web.version_history import (
    _parse_conventional_commit,
    _parse_shortstat,
    compute_version_history_data,
    refresh_version_history,
    MILESTONES,
)


def test_parse_conventional_commit():
    # feat with scope
    c_type, scope, desc = _parse_conventional_commit("feat(i18n): refine deep 4-language localization")
    assert c_type == "feat"
    assert scope == "i18n"
    assert desc == "refine deep 4-language localization"

    # fix with multiple scopes
    c_type, scope, desc = _parse_conventional_commit("fix(web,telemetry): resolve 524 timeout and blank screen")
    assert c_type == "fix"
    assert scope == "web,telemetry"
    assert desc == "resolve 524 timeout and blank screen"

    # perf without scope
    c_type, scope, desc = _parse_conventional_commit("perf: Add fast TTL cache for status and signals endpoints")
    assert c_type == "perf"
    assert scope is None
    assert desc == "Add fast TTL cache for status and signals endpoints"

    # other/unconventional commit
    c_type, scope, desc = _parse_conventional_commit("Initial commit of raw dataset")
    assert c_type == "other"
    assert scope is None
    assert desc == "Initial commit of raw dataset"


def test_parse_shortstat():
    stat_str = " 3 files changed, 120 insertions(+), 45 deletions(-)"
    stats = _parse_shortstat(stat_str)
    assert stats["files_changed"] == 3
    assert stats["insertions"] == 120
    assert stats["deletions"] == 45

    empty_stats = _parse_shortstat("")
    assert empty_stats["files_changed"] == 0
    assert empty_stats["insertions"] == 0
    assert empty_stats["deletions"] == 0


def test_compute_version_history():
    repo_root = Path(".").resolve()
    data = compute_version_history_data(repo_root, force_refresh=True)

    assert "repo" in data
    assert "stats" in data
    assert "milestones" in data
    assert "daily_velocity" in data
    assert "commits" in data

    assert data["repo"]["name"] == "dao_vang"
    assert data["repo"]["owner"] == "mrcanlaco"
    assert data["stats"]["total_commits"] > 0
    assert len(data["milestones"]) >= 5
    assert len(data["commits"]) > 0

    first_commit = data["commits"][0]
    assert "hash" in first_commit
    assert "short_hash" in first_commit
    assert "author" in first_commit
    assert "subject" in first_commit
    assert "type" in first_commit
    assert "github_url" in first_commit


def test_refresh_version_history():
    repo_root = Path(".").resolve()
    data = refresh_version_history(repo_root)
    assert data["stats"]["total_commits"] > 0
