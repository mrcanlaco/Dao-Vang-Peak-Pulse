"""Core update manager for Đảo Vàng PeakPulse.

Handles checking for remote updates, pulling git commits, updating Python
and frontend dependencies, restarting background services, and sending Telegram
alerts.
"""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dao_vang.alerts.telegram import TelegramNotifier
from dao_vang.config.settings import AppSettings

logger = logging.getLogger("dao_vang.updater")

# In-memory record of the last update result and live update status
_LAST_UPDATE_RESULT: dict[str, Any] | None = None
_IS_UPDATING: bool = False
_UPDATE_LOGS: list[str] = []


def _get_system_time_iso() -> str:
    """Return local ISO timestamp in UTC+7."""
    try:
        from dao_vang.domain.time import system_iso
        return system_iso(datetime.now(timezone.utc).isoformat())
    except Exception:
        return datetime.now(timezone.utc).isoformat()


@dataclass
class CommitInfo:
    hash: str
    short_hash: str
    author: str
    date: str
    message: str
    type: str = "other"
    scope: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UpdateStatus:
    update_available: bool
    current_branch: str
    local_commit: str
    local_commit_short: str
    local_commit_message: str
    remote_commit: str
    remote_commit_short: str
    remote_commit_message: str
    commits_behind: int
    commits_ahead: int
    new_commits: list[dict[str, Any]] = field(default_factory=list)
    has_dependency_changes: bool = False
    has_frontend_changes: bool = False
    last_checked_at: str = field(default_factory=_get_system_time_iso)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UpdateResult:
    success: bool
    message: str
    previous_commit: str
    current_commit: str
    commits_applied: list[dict[str, Any]] = field(default_factory=list)
    dependencies_updated: bool = False
    frontend_rebuilt: bool = False
    services_restarted: bool = False
    logs: list[str] = field(default_factory=list)
    completed_at: str = field(default_factory=_get_system_time_iso)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UpdateManager:
    """Manages Git updates, dependency installations, and service restarts."""

    def __init__(
        self,
        repo_root: Path | str | None = None,
        settings: AppSettings | None = None,
    ) -> None:
        if repo_root is None:
            # Locate repo root by walking up from current file
            current_dir = Path(__file__).resolve().parent
            # parent: updater -> dao_vang -> src -> root
            candidate = current_dir.parent.parent.parent
            if (candidate / ".git").exists():
                self.repo_root = candidate
            else:
                self.repo_root = Path(".").resolve()
        else:
            self.repo_root = Path(repo_root).resolve()

        self.settings = settings or AppSettings()

    def _run_cmd(
        self,
        cmd: list[str] | str,
        cwd: Path | None = None,
        check: bool = False,
        timeout: int = 120,
    ) -> tuple[int, str, str]:
        """Execute a shell command safely and return (returncode, stdout, stderr)."""
        target_cwd = cwd or self.repo_root
        use_shell = isinstance(cmd, str)
        try:
            res = subprocess.run(
                cmd,
                cwd=str(target_cwd),
                capture_output=True,
                text=True,
                shell=use_shell,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except Exception as exc:
            logger.error("cmd_execution_failed cmd=%s error=%s", cmd, exc)
            return -1, "", str(exc)

    def _parse_commit_type(self, message: str) -> tuple[str, str]:
        """Extract conventional commit type and scope (e.g. feat(scanner): ...)."""
        match = re.match(r"^(\w+)(?:\(([^)]+)\))?!?:", message.strip())
        if match:
            c_type = match.group(1).lower()
            scope = match.group(2) or ""
            return c_type, scope
        return "other", ""

    def check_for_updates(
        self,
        remote: str | None = None,
        branch: str | None = None,
    ) -> UpdateStatus:
        """Fetch remote git metadata and return detailed update status."""
        remote_name = remote or self.settings.updater.remote_name or "origin"
        branch_name = branch or self.settings.updater.branch_name or "main"

        # 1. Check current branch
        code, current_branch, _ = self._run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if code != 0 or not current_branch:
            current_branch = branch_name

        # 2. Get local HEAD commit info
        _, local_hash, _ = self._run_cmd(["git", "rev-parse", "HEAD"])
        _, local_short, _ = self._run_cmd(["git", "rev-parse", "--short", "HEAD"])
        _, local_msg, _ = self._run_cmd(["git", "log", "-1", "--pretty=%s", "HEAD"])

        # 3. Fetch remote silently
        fetch_cmd = ["git", "fetch", remote_name, branch_name, "--quiet"]
        fetch_code, _, fetch_err = self._run_cmd(fetch_cmd, timeout=30)
        if fetch_code != 0:
            logger.warning("git_fetch_failed remote=%s branch=%s error=%s", remote_name, branch_name, fetch_err)
            return UpdateStatus(
                update_available=False,
                current_branch=current_branch,
                local_commit=local_hash or "UNKNOWN",
                local_commit_short=local_short or "UNKNOWN",
                local_commit_message=local_msg or "",
                remote_commit="UNKNOWN",
                remote_commit_short="UNKNOWN",
                remote_commit_message="",
                commits_behind=0,
                commits_ahead=0,
                error=f"Không thể kết nối tới GitHub ({fetch_err or 'Git fetch failed'})",
            )

        # 4. Get remote HEAD commit info
        remote_ref = f"{remote_name}/{branch_name}"
        _, remote_hash, _ = self._run_cmd(["git", "rev-parse", remote_ref])
        _, remote_short, _ = self._run_cmd(["git", "rev-parse", "--short", remote_ref])
        _, remote_msg, _ = self._run_cmd(["git", "log", "-1", "--pretty=%s", remote_ref])

        # 5. Calculate commits behind / ahead
        _, rev_count, _ = self._run_cmd(["git", "rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"])
        ahead, behind = 0, 0
        if rev_count and "\t" in rev_count:
            parts = rev_count.split("\t")
            ahead = int(parts[0]) if parts[0].isdigit() else 0
            behind = int(parts[1]) if parts[1].isdigit() else 0

        # 6. Parse new commits if behind
        new_commits: list[dict[str, Any]] = []
        has_dep_changes = False
        has_fe_changes = False

        if behind > 0:
            log_format = "%H%x1f%h%x1f%an%x1f%ad%x1f%s"
            cmd = ["git", "log", f"--pretty=format:{log_format}", f"HEAD..{remote_ref}"]
            code, stdout, _ = self._run_cmd(cmd)
            if code == 0 and stdout:
                for line in stdout.strip().split("\n"):
                    if not line:
                        continue
                    fields = line.split("\x1f")
                    if len(fields) >= 5:
                        c_hash, c_short, c_author, c_date, c_msg = fields[:5]
                        c_type, c_scope = self._parse_commit_type(c_msg)
                        new_commits.append({
                            "hash": c_hash,
                            "short_hash": c_short,
                            "author": c_author,
                            "date": c_date,
                            "message": c_msg,
                            "type": c_type,
                            "scope": c_scope,
                        })

            # Check file diffs for dependency or frontend changes
            diff_cmd = ["git", "diff", "--name-only", f"HEAD..{remote_ref}"]
            code, diff_files_str, _ = self._run_cmd(diff_cmd)
            if code == 0 and diff_files_str:
                changed_files = diff_files_str.split("\n")
                for f in changed_files:
                    f = f.strip().lower()
                    if f in ("pyproject.toml", "uv.lock", "requirements.txt", "package.json", "package-lock.json"):
                        has_dep_changes = True
                    if f.startswith("frontend/"):
                        has_fe_changes = True

        update_available = behind > 0 or (local_hash != remote_hash and local_hash != "")

        return UpdateStatus(
            update_available=update_available,
            current_branch=current_branch,
            local_commit=local_hash or "",
            local_commit_short=local_short or "",
            local_commit_message=local_msg or "",
            remote_commit=remote_hash or "",
            remote_commit_short=remote_short or "",
            remote_commit_message=remote_msg or "",
            commits_behind=behind,
            commits_ahead=ahead,
            new_commits=new_commits,
            has_dependency_changes=has_dep_changes,
            has_frontend_changes=has_fe_changes,
        )

    def apply_update(
        self,
        force: bool = False,
        restart_services: bool = True,
        rebuild_frontend: bool = True,
        notify_telegram: bool = True,
        remote_deploy: bool = False,
    ) -> UpdateResult:
        """Perform the complete update process safely."""
        global _IS_UPDATING, _UPDATE_LOGS, _LAST_UPDATE_RESULT

        if _IS_UPDATING:
            return UpdateResult(
                success=False,
                message="Tiến trình cập nhật đang chạy, vui lòng đợi hoàn tất.",
                previous_commit="",
                current_commit="",
                error="Update process already in progress",
            )

        _IS_UPDATING = True
        _UPDATE_LOGS.clear()

        def log_msg(msg: str) -> None:
            timestamp = _get_system_time_iso()[:19].replace("T", " ")
            formatted = f"[{timestamp}] {msg}"
            _UPDATE_LOGS.append(formatted)
            logger.info("updater_step: %s", msg)

        try:
            log_msg("=== BẮT ĐẦU CẬP NHẬT ĐẢO VÀNG PEAKPULSE ===")
            remote_name = self.settings.updater.remote_name or "origin"
            branch_name = self.settings.updater.branch_name or "main"

            # 1. Check pre-update status
            status = self.check_for_updates(remote=remote_name, branch=branch_name)
            prev_commit = status.local_commit_short
            log_msg(f"Phiên bản hiện tại: {prev_commit} (nhánh {status.current_branch})")

            # 2. Handle unmerged conflict state & dirty git state safely
            git_dir = self.repo_root / ".git"
            if (git_dir / "MERGE_HEAD").exists():
                log_msg("Phát hiện trạng thái merge xung đột dở dang (MERGE_HEAD). Đang hủy merge cũ (git merge --abort)...")
                self._run_cmd(["git", "merge", "--abort"])
            if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
                log_msg("Phát hiện trạng thái rebase dở dang. Đang hủy rebase (git rebase --abort)...")
                self._run_cmd(["git", "rebase", "--abort"])

            code, dirty_status, _ = self._run_cmd(["git", "status", "--porcelain"])
            has_stashed = False
            if dirty_status:
                log_msg("Phát hiện thay đổi chưa commit trong thư mục làm việc.")
                # Check for unmerged files (lines starting with U, AA, DD, etc.)
                has_unmerged = any(line.strip().startswith(('U', 'AA', 'DD', 'DU', 'UD')) for line in dirty_status.splitlines())
                if has_unmerged:
                    log_msg("Phát hiện file xung đột chưa giải quyết (unmerged files). Đang reset để sẵn sàng cập nhật...")
                    self._run_cmd(["git", "reset", "--hard", "HEAD"])
                else:
                    log_msg("Tự động lưu trữ thay đổi tạm thời (git stash) để tránh xung đột...")
                    self._run_cmd(["git", "stash", "save", "auto-stash-before-update"])
                    has_stashed = True

            # 3. Pull latest code
            log_msg(f"Đang tải mã nguồn mới từ {remote_name}/{branch_name}...")
            self._run_cmd(["git", "fetch", remote_name, branch_name, "--prune"], timeout=60)
            pull_cmd = ["git", "pull", "--no-rebase", remote_name, branch_name]
            pull_code, pull_out, pull_err = self._run_cmd(pull_cmd, timeout=60)
            log_msg(f"Git pull output:\n{pull_out}")

            if pull_code != 0:
                log_msg(f"Git pull thông thường gặp cảnh báo/xung đột: {pull_err or pull_out}")
                log_msg("Đang tự động áp dụng bản chuẩn sạch từ GitHub (git reset --hard)...")
                reset_code, reset_out, reset_err = self._run_cmd(["git", "reset", "--hard", f"{remote_name}/{branch_name}"], timeout=60)
                if reset_code == 0:
                    pull_code = 0
                    log_msg(f"✅ Đã đồng bộ mã nguồn sạch về {remote_name}/{branch_name} thành công.")
                else:
                    err_msg = f"Lỗi khi kéo mã nguồn git: {reset_err or reset_out or pull_err}"
                    log_msg(f"❌ {err_msg}")
                    res = UpdateResult(
                        success=False,
                        message="Cập nhật thất bại khi git pull / reset.",
                        previous_commit=prev_commit,
                        current_commit=prev_commit,
                        logs=list(_UPDATE_LOGS),
                        error=err_msg,
                    )
                    _LAST_UPDATE_RESULT = res.to_dict()
                    return res

            # Restore stash if needed
            if has_stashed:
                log_msg("Khôi phục lại thay đổi cục bộ từ stash...")
                self._run_cmd(["git", "stash", "pop"])

            # 4. Get new current commit
            _, new_hash, _ = self._run_cmd(["git", "rev-parse", "HEAD"])
            _, new_short, _ = self._run_cmd(["git", "rev-parse", "--short", "HEAD"])
            _, new_msg, _ = self._run_cmd(["git", "log", "-1", "--pretty=%s", "HEAD"])
            log_msg(f"✅ Đã kéo mã nguồn mới thành công! Commit hiện tại: {new_short} ({new_msg})")

            # 5. Dependency sync
            deps_updated = False
            if status.has_dependency_changes or force:
                log_msg("Phát hiện thay đổi phụ thuộc Python. Đang đồng bộ thư viện...")
                # Try uv sync first, fallback to pip
                uv_path = shutil.which("uv")
                if uv_path:
                    log_msg("Đang chạy 'uv sync'...")
                    uv_code, uv_out, _ = self._run_cmd(["uv", "sync"], timeout=180)
                    if uv_code == 0:
                        deps_updated = True
                        log_msg("✅ Đồng bộ thư viện qua uv thành công.")
                    else:
                        log_msg(f"uv sync gặp cảnh báo: {uv_out}. Thử tiếp qua pip install...")

                if not deps_updated:
                    py_exe = sys.executable
                    log_msg(f"Đang chạy '{py_exe} -m pip install -e .'...")
                    pip_code, pip_out, pip_err = self._run_cmd([py_exe, "-m", "pip", "install", "-e", "."], timeout=180)
                    if pip_code == 0:
                        deps_updated = True
                        log_msg("✅ Cài đặt gói dao-vang thành công qua pip.")
                    else:
                        log_msg(f"⚠️ Cảnh báo khi cài đặt pip: {pip_err or pip_out}")
            else:
                log_msg("Không có thay đổi về thư viện phụ thuộc Python.")

            # 6. Rebuild frontend if needed
            fe_rebuilt = False
            fe_dir = self.repo_root / "frontend"
            if (status.has_frontend_changes or force) and rebuild_frontend and fe_dir.exists():
                npm_path = shutil.which("npm")
                if npm_path:
                    log_msg("Phát hiện thay đổi giao diện Frontend. Đang build lại bằng npm run build...")
                    npm_code, npm_out, npm_err = self._run_cmd(["npm", "run", "build"], cwd=fe_dir, timeout=180)
                    if npm_code == 0:
                        fe_rebuilt = True
                        log_msg("✅ Build giao diện React / Vite thành công.")
                    else:
                        log_msg(f"⚠️ Cảnh báo khi build frontend: {npm_err or npm_out}")
                else:
                    log_msg("⚠️ Không tìm thấy lệnh npm trên máy để build frontend.")
            else:
                log_msg("Không cần build lại frontend.")

            # 7. Clean stale lock files
            cleaned_locks = self._clean_locks()
            if cleaned_locks:
                log_msg(f"Đã dọn dẹp các file lock cũ: {', '.join(cleaned_locks)}")

            # 8. Restart background services if requested
            services_restarted = False
            if restart_services:
                log_msg("Đang khởi động lại các dịch vụ nền (Scanner daemon & Web server)...")
                if platform.system() == "Windows":
                    services_restarted, s_logs = self._restart_services_windows()
                    for sl in s_logs:
                        log_msg(sl)
                else:
                    # Linux / Docker restart
                    services_restarted, s_logs = self._restart_services_linux()
                    for sl in s_logs:
                        log_msg(sl)

            # 9. Remote MSI Deployment if requested
            if remote_deploy or self.settings.updater.auto_deploy_remote:
                log_msg("Đang kích hoạt triển khai cập nhật lên server Ubuntu MSI...")
                msi_script = self.repo_root / "scripts" / "deploy_msi.py"
                if msi_script.exists():
                    py_exe = sys.executable
                    code, msi_out, msi_err = self._run_cmd([py_exe, str(msi_script)], timeout=300)
                    if code == 0:
                        log_msg("✅ Triển khai cập nhật lên server MSI từ xa thành công!")
                    else:
                        log_msg(f"⚠️ Triển khai MSI gặp lỗi: {msi_err or msi_out}")

            # 10. Check health
            log_msg("Đang kiểm tra sức khỏe hệ thống sau cập nhật...")
            health = self.check_system_health()
            log_msg(f"Trạng thái hệ thống: {health.get('summary', 'OK')}")

            # 11. Send Telegram Notification
            result = UpdateResult(
                success=True,
                message=f"Đã cập nhật Đảo Vàng thành công lên bản {new_short}!",
                previous_commit=prev_commit,
                current_commit=new_short,
                commits_applied=status.new_commits,
                dependencies_updated=deps_updated,
                frontend_rebuilt=fe_rebuilt,
                services_restarted=services_restarted,
                logs=list(_UPDATE_LOGS),
            )
            _LAST_UPDATE_RESULT = result.to_dict()

            if notify_telegram and self.settings.updater.telegram_notify:
                self._send_telegram_notification(result, new_short, new_msg, health)

            log_msg(f"=== HOÀN TẤT CẬP NHẬT THÀNH CÔNG: {new_short} ===")
            return result

        except Exception as exc:
            err_msg = f"Ngoại lệ không mong muốn khi cập nhật: {exc}"
            log_msg(f"❌ {err_msg}")
            logger.exception("update_apply_failed")
            result = UpdateResult(
                success=False,
                message="Quá trình cập nhật gặp sự cố.",
                previous_commit=status.local_commit_short if 'status' in locals() else "",
                current_commit="",
                logs=list(_UPDATE_LOGS),
                error=err_msg,
            )
            _LAST_UPDATE_RESULT = result.to_dict()
            return result
        finally:
            _IS_UPDATING = False

    def _clean_locks(self) -> list[str]:
        """Remove any stale lock files that could block supervisors."""
        cleaned = []
        lock_paths = [
            self.repo_root / "data_live" / "web.lock",
            self.repo_root / "data_live" / "scanner.lock",
            self.repo_root / "data" / "web.lock",
            self.repo_root / "data" / "scanner.lock",
        ]
        for lp in lock_paths:
            if lp.exists():
                try:
                    lp.unlink()
                    cleaned.append(lp.name)
                except Exception as exc:
                    logger.debug("cannot_unlink_lock path=%s error=%s", lp, exc)
        return cleaned

    def _restart_services_windows(self) -> tuple[bool, list[str]]:
        """Restart Windows Scheduled Tasks and supervisor loops."""
        logs = []
        tasks = ["DaoVangScanner", "DaoVangWebUI"]
        restarted_count = 0

        for task_name in tasks:
            # Stop task
            stop_cmd = f"powershell.exe -NoProfile -Command \"Stop-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue\""
            self._run_cmd(stop_cmd, timeout=15)

            # Start task
            start_cmd = f"powershell.exe -NoProfile -Command \"Start-ScheduledTask -TaskName '{task_name}' -ErrorAction SilentlyContinue\""
            code, _, _ = self._run_cmd(start_cmd, timeout=15)
            if code == 0:
                restarted_count += 1
                logs.append(f"✅ Đã khởi động lại Scheduled Task: {task_name}")
            else:
                logs.append(f"ℹ️ Không có Scheduled Task '{task_name}' hoặc chưa kích hoạt.")

        return restarted_count > 0, logs

    def _restart_services_linux(self) -> tuple[bool, list[str]]:
        """Restart Linux Docker / systemd services."""
        logs = []
        compose_file = self.repo_root / "docker-compose.yml"
        if compose_file.exists():
            code, stdout, _ = self._run_cmd(["docker", "compose", "restart"], timeout=60)
            if code == 0:
                logs.append("✅ Đã khởi động lại Docker Compose services thành công.")
                return True, logs
        logs.append("ℹ️ Không tìm thấy Docker compose trên Linux.")
        return False, logs

    def check_system_health(self) -> dict[str, Any]:
        """Perform a quick health probe on DuckDB and Web API."""
        status: dict[str, Any] = {
            "web_api": "UNKNOWN",
            "duckdb": "UNKNOWN",
            "scanner_heartbeat": "UNKNOWN",
            "summary": "OK",
        }

        # Check DuckDB
        db_path = self.repo_root / "data_live" / "live.duckdb"
        if not db_path.exists():
            db_path = self.repo_root / "data" / "dev.duckdb"

        if db_path.exists():
            try:
                from dao_vang.data.storage.duckdb import DuckDBQueryLayer
                ql = DuckDBQueryLayer(str(db_path))
                ql.query("SELECT 1")
                status["duckdb"] = "HEALTHY"
            except Exception as e:
                status["duckdb"] = f"ACCESSIBLE ({e})"
        else:
            status["duckdb"] = "NOT_CREATED_YET"

        # Check Scanner Heartbeat
        heartbeat_file = self.repo_root / "data_live" / "scanner_heartbeat.json"
        if not heartbeat_file.exists():
            heartbeat_file = self.repo_root / "data" / "scanner_heartbeat.json"

        if heartbeat_file.exists():
            try:
                import json
                with open(heartbeat_file, "r", encoding="utf-8") as f:
                    hb = json.load(f)
                status["scanner_heartbeat"] = f"ACTIVE ({hb.get('last_cycle_time', 'N/A')})"
            except Exception:
                status["scanner_heartbeat"] = "PARSE_ERROR"
        else:
            status["scanner_heartbeat"] = "IDLE / WAITING"

        return status

    def _send_telegram_notification(
        self,
        result: UpdateResult,
        new_commit_short: str,
        new_commit_msg: str,
        health: dict[str, Any],
    ) -> bool:
        """Send formatted update summary to Telegram."""
        try:
            tg_notifier = TelegramNotifier(self.settings.telegram)
            if not tg_notifier.is_configured:
                return False

            now_str = _get_system_time_iso()[:19].replace("T", " ")
            lines = [
                "🚀 *[ĐẢO VÀNG AUTO-UPDATE]*",
                "Hệ thống đã cập nhật thành công lên bản mới nhất!",
                "━━━━━━━━━━━━━━━━━━━━━",
                f"📦 *Commit:* `{new_commit_short}` (origin/main)",
                f"📝 *Nội dung:* {new_commit_msg}",
                f"🕒 *Thời gian:* `{now_str} UTC+7`",
                f"⚙️ *Thư viện Python:* {'Đã cập nhật' if result.dependencies_updated else 'Không đổi'}",
                f"🎨 *Giao diện Web:* {'Đã build mới' if result.frontend_rebuilt else 'Không đổi'}",
                f"🔄 *Dịch vụ nền:* {'Đã khởi động lại' if result.services_restarted else 'Đang chạy'}",
                f"📊 *DuckDB:* `{health.get('duckdb', 'OK')}`",
                "━━━━━━━━━━━━━━━━━━━━━",
                "_Hệ thống sẵn sàng phục vụ tín hiệu và giao dịch 24/7._",
            ]
            return tg_notifier.send_message("\n".join(lines))
        except Exception as exc:
            logger.error("telegram_update_notify_failed error=%s", exc)
            return False


def get_update_status() -> dict[str, Any]:
    """Helper for API server to get current status without blocking long."""
    manager = UpdateManager()
    status = manager.check_for_updates()
    res = status.to_dict()
    res["is_updating"] = _IS_UPDATING
    res["last_update_result"] = _LAST_UPDATE_RESULT
    return res


def get_update_logs() -> list[str]:
    """Retrieve in-memory update logs."""
    return list(_UPDATE_LOGS)
