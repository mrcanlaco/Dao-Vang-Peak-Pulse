"""Đảo Vàng Updater Module.

Provides 1-Click Update, 1-Command CLI Update, and Background Auto-Updater
mechanisms with Git sync, dependency updates, UI rebuild, service restarts,
and Telegram notifications.
"""

from dao_vang.updater.auto_updater import AutoUpdaterDaemon
from dao_vang.updater.manager import (
    CommitInfo,
    UpdateManager,
    UpdateResult,
    UpdateStatus,
)

__all__ = [
    "CommitInfo",
    "UpdateManager",
    "UpdateResult",
    "UpdateStatus",
    "AutoUpdaterDaemon",
]
