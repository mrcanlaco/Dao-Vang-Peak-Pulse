"""Version history & GitHub development timeline extraction service.

Provides structured commit logs, release milestones, development velocity metrics,
and changelog data from local Git and GitHub repository.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dao_vang import __version__

logger = logging.getLogger("dao_vang.version_history")

# In-memory cache with 5-minute TTL
_CACHE: dict[str, Any] | None = None
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS = 300.0  # 5 minutes

REPO_OWNER = "mrcanlaco"
REPO_NAME = "Dao-Vang-Peak-Pulse"
GITHUB_REPO_URL = f"https://github.com/{REPO_OWNER}/{REPO_NAME}"

# Known architectural milestones for Đảo Vàng PeakPulse
MILESTONES = [
    {
        "id": "v2.0-pro-gui",
        "tag": "v2.0.0-pro",
        "title": "GUI V2 Pro Mobile & 2-Tier Climax Engine",
        "date": "2026-08-20",
        "status": "COMPLETED",
        "description": "Binance/OKX-style Pro trading flow, TradingView chart, 2-Tier Climax scoring (ARMED/FIRED), Multi-language i18n (VI/EN/ZH/KO), PWA offline support.",
        "highlights": [
            "2-Tier Climax Engine with Adaptive SL & Multi-Tier TP",
            "Deep 4-Language localization (Tiếng Việt, English, 简体中文, 한국어)",
            "Progressive Web App (PWA) with offline caching & install prompt",
            "DuckDB direct RO connection with CTE partitions for zero-copy queries",
        ],
    },
    {
        "id": "v1.0-release-candidate",
        "tag": "v1.0.0-rc.1",
        "title": "V1.0.0 Release Candidate & 24/7 Scanner",
        "date": "2026-08-01",
        "status": "COMPLETED",
        "description": "Full end-to-end quant pipeline with continuous 24/7 scanning daemon, Telegram multi-tier alerts, and DuckDB storage.",
        "highlights": [
            "24/7 Automated scanner daemon with Telegram cycle digests",
            "Multi-coin scanner with dynamic volatility filter",
            "Candidate Filter V2 promoted to champion production lane",
            "Forward-test evaluation and model validation harness",
        ],
    },
    {
        "id": "m6-shell-cli",
        "tag": "M6",
        "title": "M6: Shell Orchestration & CLI",
        "date": "2026-07-25",
        "status": "COMPLETED",
        "description": "Typer CLI application to orchestrate data collection, labels, features, experiments, and automated reports.",
        "highlights": [
            "Unified CLI commands for all pipeline stages",
            "Experiment tracking & automated markdown report generator",
        ],
    },
    {
        "id": "m5-validation",
        "tag": "M5",
        "title": "M5: Target Validation & Model Backtesting",
        "date": "2026-07-15",
        "status": "COMPLETED",
        "description": "Walk-forward validation, Brier score calibration, 95% Bootstrap CI, and 100% data leakage prevention tests.",
        "highlights": [
            "Purged & Embargoed walk-forward cross validation",
            "Calibration curve & empirical precision testing",
        ],
    },
    {
        "id": "m4-features",
        "tag": "M4",
        "title": "M4: Feature Engineering Engine",
        "date": "2026-07-01",
        "status": "COMPLETED",
        "description": "Pure DuckDB SQL-based feature computation: Price, Open Interest, Funding Rate, and Taker Buy/Sell volume dynamics.",
        "highlights": [
            "100% SQL window functions for zero lookahead bias",
            "Dynamic ATR volatility adjustments",
        ],
    },
    {
        "id": "m3-labels",
        "tag": "M3",
        "title": "M3: Label Generation Engine",
        "date": "2026-06-20",
        "status": "COMPLETED",
        "description": "Fixed-horizon, fixed-stop, and dynamic ATR labeling engine for detecting market distribution tops.",
        "highlights": [
            "Deterministic event definition without future peek",
            "Multi-horizon labeling configurations",
        ],
    },
    {
        "id": "m2-normalization",
        "tag": "M2",
        "title": "M2: Data Normalization with DuckDB",
        "date": "2026-06-10",
        "status": "COMPLETED",
        "description": "DuckDB-based timeline alignment and ASOF joins with zero dependency on Pandas/Polars.",
        "highlights": [
            "Sub-second timeline alignment over 10M+ rows",
            "Memory-efficient columnar storage",
        ],
    },
    {
        "id": "m1-raw-data",
        "tag": "M1",
        "title": "M1: Raw Data Collection",
        "date": "2026-06-01",
        "status": "COMPLETED",
        "description": "High-throughput Binance collectors for K-lines, Funding Rates, Global Accounts, and Top Trader Sentiment.",
        "highlights": [
            "Async rate-limited Binance Futures REST & WebSocket collectors",
            "Automatic retry & backoff with disk checkpointing",
        ],
    },
]


def _parse_conventional_commit(subject: str) -> tuple[str, str | None, str]:
    """Parse conventional commit string into (type, scope, clean_description)."""
    match = re.match(r"^([a-zA-Z0-9_-]+)(?:\(([^)]+)\))?!?: (.+)$", subject.strip())
    if match:
        c_type = match.group(1).lower()
        scope = match.group(2).lower() if match.group(2) else None
        desc = match.group(3).strip()
        if not desc:
            desc = subject.strip()
        # Normalize common types
        type_mapping = {
            "feat": "feat",
            "feature": "feat",
            "fix": "fix",
            "bugfix": "fix",
            "perf": "perf",
            "performance": "perf",
            "refactor": "refactor",
            "build": "build",
            "chore": "chore",
            "docs": "docs",
            "doc": "docs",
            "test": "test",
            "tests": "test",
            "ci": "ci",
            "style": "style",
        }
        c_type = type_mapping.get(c_type, "other")
        return c_type, scope, desc
    return "other", None, subject.strip()


def _parse_shortstat(stat_str: str) -> dict[str, int]:
    """Parse git shortstat output into {files_changed, insertions, deletions}."""
    stats = {"files_changed": 0, "insertions": 0, "deletions": 0}
    if not stat_str:
        return stats

    files_match = re.search(r"(\d+)\s+file", stat_str)
    ins_match = re.search(r"(\d+)\s+insertion", stat_str)
    del_match = re.search(r"(\d+)\s+deletion", stat_str)

    if files_match:
        stats["files_changed"] = int(files_match.group(1))
    if ins_match:
        stats["insertions"] = int(ins_match.group(1))
    if del_match:
        stats["deletions"] = int(del_match.group(1))

    return stats


def _get_current_git_info(cwd: Path) -> dict[str, str]:
    """Get active branch and latest tag/commit info."""
    info = {
        "branch": "main",
        "current_tag": f"v{__version__}",
        "head_hash": "",
        "repo_url": GITHUB_REPO_URL,
    }
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            info["branch"] = res.stdout.strip()
    except Exception:
        pass

    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            info["head_hash"] = res.stdout.strip()
    except Exception:
        pass

    # If git repo info is missing (e.g. inside Docker without .git), fetch latest commit from GitHub API
    if not info["head_hash"]:
        try:
            import json
            import urllib.request
            gh_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits/main"
            req = urllib.request.Request(gh_url, headers={"User-Agent": "DaoVang-App"})
            with urllib.request.urlopen(req, timeout=3) as response:
                if response.status == 200:
                    gh_commit = json.loads(response.read().decode("utf-8"))
                    info["head_hash"] = gh_commit.get("sha", "")
        except Exception:
            pass

    try:
        res = subprocess.run(
            ["git", "describe", "--tags"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            info["current_tag"] = res.stdout.strip()
            # Try to read latest version from CHANGELOG.md
            changelog_file = cwd / "CHANGELOG.md"
            if changelog_file.exists():
                text = changelog_file.read_text(encoding="utf-8")
                match = re.search(r"##\s*\[([^\]]+)\]", text)
                if match:
                    ver = match.group(1).strip()
                    info["current_tag"] = f"v{ver}" if not ver.startswith("v") else ver
    except Exception:
        pass

    return info


def _read_changelog(repo_root: Path) -> str:
    """Read CHANGELOG.md if present."""
    changelog_path = repo_root / "CHANGELOG.md"
    if changelog_path.exists():
        try:
            return changelog_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read CHANGELOG.md: %s", e)
    return ""


def extract_git_commits(repo_root: Path, limit: int = 500) -> list[dict[str, Any]]:
    """Extract full structured git commit history using git log."""
    delimiter = "---DAO_VANG_COMMIT_SEP---"
    cmd = [
        "git",
        "log",
        f"-n{limit}",
        f"--format={delimiter}%H|||%h|||%an|||%ae|||%aI|||%s|||%D",
    ]

    raw_output = ""
    try:
        res = subprocess.run(
            cmd,
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            raw_output = res.stdout
    except Exception as e:
        logger.warning("Local git log failed: %s", e)
    # Fallback to GitHub Public API if local git is unavailable (e.g. inside Docker container)
    if not raw_output:
        try:
            import urllib.request
            gh_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/commits?per_page={min(limit, 100)}"
            req = urllib.request.Request(gh_url, headers={"User-Agent": "DaoVang-App"})
            with urllib.request.urlopen(req, timeout=10) as response:
                if response.status == 200:
                    gh_data = json.loads(response.read().decode("utf-8"))
                    gh_commits = []
                    for item in gh_data:
                        c_sha = item.get("sha", "")
                        c_commit = item.get("commit", {})
                        c_author = c_commit.get("author", {})
                        c_msg = c_commit.get("message", "").split("\n")[0]
                        c_date = c_author.get("date", "")
                        c_type, scope, clean_desc = _parse_conventional_commit(c_msg)
                        gh_commits.append({
                            "hash": c_sha,
                            "short_hash": c_sha[:7],
                            "author": c_author.get("name", "Unknown"),
                            "author_email": c_author.get("email", ""),
                            "date": c_date,
                            "subject": c_msg,
                            "type": c_type,
                            "scope": scope,
                            "description": clean_desc,
                            "github_url": f"{GITHUB_REPO_URL}/commit/{c_sha}",
                            "stats": {"files_changed": 1, "insertions": 0, "deletions": 0},
                        })
                    if gh_commits:
                        return gh_commits
        except Exception as exc:
            logger.warning("GitHub API commits fallback failed: %s", exc)

    if not raw_output:
        return []

    commits: list[dict[str, Any]] = []
    blocks = raw_output.split(delimiter)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.splitlines()
        header_line = lines[0] if lines else ""
        stats_line = ""
        for line in lines[1:]:
            if "changed" in line and ("insertion" in line or "deletion" in line):
                stats_line = line.strip()
                break

        parts = header_line.split("|||")
        if len(parts) < 6:
            continue

        full_hash = parts[0].strip()
        short_hash = parts[1].strip()
        author_name = parts[2].strip()
        author_email = parts[3].strip()
        date_iso = parts[4].strip()
        subject = parts[5].strip()
        ref_names = parts[6].strip() if len(parts) > 6 else ""

        c_type, scope, clean_desc = _parse_conventional_commit(subject)
        stats = _parse_shortstat(stats_line)

        commits.append({
            "hash": full_hash,
            "short_hash": short_hash,
            "author": author_name,
            "author_email": author_email,
            "date": date_iso,
            "subject": subject,
            "type": c_type,
            "scope": scope,
            "description": clean_desc,
            "ref_names": ref_names,
            "stats": stats,
            "github_url": f"{GITHUB_REPO_URL}/commit/{full_hash}",
        })

    return commits


def compute_version_history_data(repo_root: Path, force_refresh: bool = False) -> dict[str, Any]:
    """Compute and cache complete version history and development velocity metrics."""
    global _CACHE, _CACHE_TIMESTAMP

    now = time.time()
    if not force_refresh and _CACHE is not None and (now - _CACHE_TIMESTAMP) < _CACHE_TTL_SECONDS:
        return _CACHE

    git_info = _get_current_git_info(repo_root)
    commits = extract_git_commits(repo_root, limit=500)
    changelog_raw = _read_changelog(repo_root)

    total_commits = len(commits)
    type_counts: dict[str, int] = {}
    scope_counts: dict[str, int] = {}
    authors_map: dict[str, int] = {}
    daily_map: dict[str, dict[str, Any]] = {}

    total_insertions = 0
    total_deletions = 0
    total_files_changed = 0

    for c in commits:
        t = c["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

        s = c.get("scope")
        if s:
            for single_scope in s.split(","):
                single_scope = single_scope.strip()
                if single_scope:
                    scope_counts[single_scope] = scope_counts.get(single_scope, 0) + 1

        author = c["author"]
        authors_map[author] = authors_map.get(author, 0) + 1

        day = c["date"][:10] if len(c["date"]) >= 10 else "Unknown"
        if day not in daily_map:
            daily_map[day] = {"date": day, "commits": 0, "feat": 0, "fix": 0, "perf": 0, "other": 0}
        daily_map[day]["commits"] += 1
        if t == "feat":
            daily_map[day]["feat"] += 1
        elif t == "fix":
            daily_map[day]["fix"] += 1
        elif t == "perf":
            daily_map[day]["perf"] += 1
        else:
            daily_map[day]["other"] += 1

        stats = c.get("stats", {})
        total_insertions += stats.get("insertions", 0)
        total_deletions += stats.get("deletions", 0)
        total_files_changed += stats.get("files_changed", 0)

    # Sort daily activity chronologically
    daily_velocity = sorted(daily_map.values(), key=lambda x: x["date"])

    # Top scopes sorted
    top_scopes = [
        {"scope": k, "count": v}
        for k, v in sorted(scope_counts.items(), key=lambda item: item[1], reverse=True)[:15]
    ]

    # Top authors
    top_authors = [
        {"name": k, "commits": v}
        for k, v in sorted(authors_map.items(), key=lambda item: item[1], reverse=True)
    ]

    last_commit_date = commits[0]["date"] if commits else datetime.now(timezone.utc).isoformat()
    latest_version = git_info["current_tag"] or f"v{__version__}"

    payload: dict[str, Any] = {
        "repo": {
            "name": REPO_NAME,
            "owner": REPO_OWNER,
            "url": GITHUB_REPO_URL,
            "branch": git_info["branch"],
            "current_tag": latest_version,
            "head_hash": git_info["head_hash"],
        },
        "stats": {
            "total_commits": total_commits,
            "total_insertions": total_insertions,
            "total_deletions": total_deletions,
            "total_files_changed": total_files_changed,
            "last_commit_date": last_commit_date,
            "type_counts": type_counts,
            "active_days": len(daily_map),
        },
        "top_scopes": top_scopes,
        "top_authors": top_authors,
        "daily_velocity": daily_velocity,
        "milestones": MILESTONES,
        "changelog_raw": changelog_raw,
        "commits": commits,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }

    _CACHE = payload
    _CACHE_TIMESTAMP = now
    return payload


def refresh_version_history(repo_root: Path) -> dict[str, Any]:
    """Force-refresh and rebuild the version history cache."""
    return compute_version_history_data(repo_root, force_refresh=True)
