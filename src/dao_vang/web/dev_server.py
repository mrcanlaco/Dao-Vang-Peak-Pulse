"""Đảo Vàng Auto-Reload Development Server.

Watches the src/ directory for any Python file changes and automatically
restarts the backend server seamlessly. Zero external dependencies required.
"""

import os
import subprocess
import sys
import time
from pathlib import Path


def get_python_mtimes(watch_dirs: list[Path]) -> dict[Path, float]:
    """Collect modification timestamps of all Python files in watched directories."""
    mtimes = {}
    for watch_dir in watch_dirs:
        if not watch_dir.exists():
            continue
        for p in watch_dir.rglob("*.py"):
            try:
                mtimes[p] = p.stat().st_mtime
            except OSError:
                pass
    return mtimes


def main() -> None:
    port = sys.argv[1] if len(sys.argv) > 1 else "8000"
    watch_dirs = [Path("src"), Path("configs")]

    print("=" * 65)
    print("      ⚡ DAO VANG AUTO-RELOAD BACKEND DEV SERVER ⚡")
    print("=" * 65)
    print(f"  * Web API Port : {port} (http://localhost:{port})")
    print("  * Auto-Reload  : ACTIVE (Tự động nạp lại khi sửa file .py)")
    print(f"  * Watch Paths  : {[str(d) for d in watch_dirs]}")
    print("  * Stop Server  : Nhấn Ctrl + C")
    print("=" * 65)
    print()

    last_mtimes = get_python_mtimes(watch_dirs)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"

    # Start child web server process
    process = subprocess.Popen(
        [sys.executable, "-m", "dao_vang.web.run", port],
        env=env,
    )

    try:
        while True:
            time.sleep(1)
            # Check if child process died unexpectedly
            if process.poll() is not None:
                print(f"\n⚠️ Backend process exited with code {process.returncode}. Restarting in 2s...")
                time.sleep(2)
                process = subprocess.Popen(
                    [sys.executable, "-m", "dao_vang.web.run", port],
                    env=env,
                )
                last_mtimes = get_python_mtimes(watch_dirs)
                continue

            current_mtimes = get_python_mtimes(watch_dirs)
            if current_mtimes != last_mtimes:
                # Find which files changed
                changed = [
                    str(p.name)
                    for p, mtime in current_mtimes.items()
                    if p not in last_mtimes or last_mtimes[p] != mtime
                ]
                print()
                print(f"🔄 [AUTO-RELOAD] Phát hiện thay đổi trong: {', '.join(changed[:3])}...")
                print("🔄 Đang khởi động lại Backend Server...")

                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()

                # Short pause to ensure socket is freed
                time.sleep(0.5)

                process = subprocess.Popen(
                    [sys.executable, "-m", "dao_vang.web.run", port],
                    env=env,
                )
                last_mtimes = current_mtimes
                print("✅ [AUTO-RELOAD] Server đã sẵn sàng! F5 lại trình duyệt để nhận dữ liệu mới.\n")

    except KeyboardInterrupt:
        print("\n🛑 Đang tắt Backend Dev Server...")
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print("👋 Đã đóng server.")


if __name__ == "__main__":
    main()
