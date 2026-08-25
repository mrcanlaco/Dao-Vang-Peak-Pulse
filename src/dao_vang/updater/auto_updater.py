"""Auto-updater background daemon for Đảo Vàng PeakPulse.

Periodically queries GitHub origin/main for new commits. When a new commit
is published, automatically pulls changes, syncs dependencies, rebuilds UI,
restarts live services, and notifies via Telegram.
"""

from __future__ import annotations

import logging
import signal
import sys
import time
from pathlib import Path

from dao_vang.config.settings import AppSettings
from dao_vang.updater.manager import UpdateManager

logger = logging.getLogger("dao_vang.updater.auto")


class AutoUpdaterDaemon:
    """Daemon that continuously monitors git remote and applies updates."""

    def __init__(
        self,
        repo_root: Path | str | None = None,
        settings: AppSettings | None = None,
        poll_interval_minutes: int | None = None,
    ) -> None:
        self.settings = settings or AppSettings()
        self.manager = UpdateManager(repo_root=repo_root, settings=self.settings)
        self.poll_interval_seconds = (
            (poll_interval_minutes or self.settings.updater.poll_interval_minutes or 10) * 60
        )
        self._running = False

    def start(self) -> None:
        """Start the auto-updater monitoring loop."""
        self._running = True

        def _handle_signal(signum, frame):
            logger.info("auto_updater_stopping signal=%s", signum)
            self._running = False

        try:
            signal.signal(signal.SIGINT, _handle_signal)
            signal.signal(signal.SIGTERM, _handle_signal)
        except Exception:
            pass

        logger.info(
            "auto_updater_started interval_sec=%d remote=%s branch=%s",
            self.poll_interval_seconds,
            self.settings.updater.remote_name,
            self.settings.updater.branch_name,
        )
        print(
            f"🚀 [ĐẢO VÀNG AUTO-UPDATER] Khởi chạy giám sát GitHub (Chu kỳ: {self.poll_interval_seconds // 60} phút)..."
        )

        while self._running:
            try:
                self.run_once()
            except Exception as exc:
                logger.error("auto_updater_cycle_error error=%s", exc)

            # Sleep with 1-second ticks for clean shutdown responsiveness
            for _ in range(self.poll_interval_seconds):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("auto_updater_stopped")
        print("🛑 [ĐẢO VÀNG AUTO-UPDATER] Đã dừng tiến trình giám sát.")

    def run_once(self) -> bool:
        """Check once and apply update if new commits are found. Returns True if updated."""
        logger.debug("auto_updater_checking_github")
        status = self.manager.check_for_updates()

        if status.error:
            logger.warning("auto_updater_check_failed error=%s", status.error)
            return False

        if not status.update_available:
            logger.debug(
                "auto_updater_up_to_date commit=%s behind=%d",
                status.local_commit_short,
                status.commits_behind,
            )
            return False

        logger.info(
            "auto_updater_new_version_found current=%s remote=%s behind=%d",
            status.local_commit_short,
            status.remote_commit_short,
            status.commits_behind,
        )
        print(
            f"\n🔔 [ĐẢO VÀNG] Phát hiện {status.commits_behind} commit mới trên GitHub ({status.remote_commit_short})!"
        )
        print(f"   Tiến hành tự động cập nhật hệ thống...")

        res = self.manager.apply_update(
            force=False,
            restart_services=self.settings.updater.auto_restart_services,
            rebuild_frontend=self.settings.updater.rebuild_frontend,
            notify_telegram=self.settings.updater.telegram_notify,
            remote_deploy=self.settings.updater.auto_deploy_remote,
        )

        if res.success:
            logger.info("auto_updater_update_success new_commit=%s", res.current_commit)
            print(f"✅ [ĐẢO VÀNG] Cập nhật thành công lên bản {res.current_commit}!\n")
            return True
        else:
            logger.error("auto_updater_update_failed error=%s", res.error)
            print(f"❌ [ĐẢO VÀNG] Cập nhật thất bại: {res.error}\n")
            return False


def run_auto_updater(interval_minutes: int | None = None) -> None:
    """Entry point for CLI or script."""
    daemon = AutoUpdaterDaemon(poll_interval_minutes=interval_minutes)
    daemon.start()
