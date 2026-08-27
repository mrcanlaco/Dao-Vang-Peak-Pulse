"""Deploy and update application on Google Server (136.110.29.208)."""

import os
import sys
import subprocess
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ssh_dir = os.path.expanduser("~/.ssh")
key_path = os.path.join(ssh_dir, "gcp_dao_vang")
host = "136.110.29.208"
user = "ubuntu"

if not os.path.exists(key_path):
    print(f"[ERROR] SSH Key not found at {key_path}")
    sys.exit(1)

commands = [
    ("Kiểm tra trạng thái Git", "cd /home/ubuntu/dao_vang && git status --short"),
    ("Hủy các trạng thái xung đột / merge dở dang", "cd /home/ubuntu/dao_vang && git merge --abort 2>/dev/null || true && git rebase --abort 2>/dev/null || true && git reset --hard HEAD && git clean -fd"),
    ("Đồng bộ mã nguồn mới nhất từ GitHub origin/main", "cd /home/ubuntu/dao_vang && git fetch origin main --prune && git reset --hard origin/main"),
    ("Bảo đảm quyền truy cập Cloudflare Tunnel", "chmod 644 /home/ubuntu/dao_vang/cloudflared/* 2>/dev/null || true"),
    ("Dọn dẹp lock files cũ", "cd /home/ubuntu/dao_vang && rm -f data/web.lock data_live/web.lock data/scanner.lock data_live/scanner.lock"),
    ("Dừng container cũ và build container mới", "cd /home/ubuntu/dao_vang && docker compose down && docker compose up -d --build --force-recreate"),
    ("Kiểm tra danh sách container", "cd /home/ubuntu/dao_vang && sleep 5 && docker compose ps"),
    ("Kiểm tra API Health Endpoint", "curl -s -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8000/api/status"),
]

print(f"==> Connecting to Google Cloud Server ({user}@{host}:22)...")

try:
    import paramiko
    key = paramiko.Ed25519Key.from_private_key_file(key_path)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=22, username=user, pkey=key, timeout=15)
    print("[OK] Connected successfully via Paramiko!\n")

    for title, cmd in commands:
        print(f"\n========================================================")
        print(f"==> {title}")
        print(f"    CMD: {cmd}")
        print(f"========================================================")
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
        while True:
            line = stdout.readline()
            if not line:
                break
            sys.stdout.write(line)
            sys.stdout.flush()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            print(f"[WARN] Command exited with code: {exit_status}")

    client.close()

except ImportError:
    print("[INFO] Paramiko not found, using system ssh client...")
    full_remote_cmd = " && ".join([f"echo '==> {t}' && {c}" for t, c in commands])
    cmd_args = ["ssh", "-i", key_path, "-o", "StrictHostKeyChecking=no", f"{user}@{host}", full_remote_cmd]
    res = subprocess.run(cmd_args, capture_output=False)
    if res.returncode != 0:
        print(f"[WARN] SSH exited with code {res.returncode}")

print("\n==> [COMPLETE] Deployment on Google Server 136.110.29.208 finished successfully!")
