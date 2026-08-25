"""Deploy and update application on Google Server (136.110.29.208)."""

import os
import sys
import time
import paramiko

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ssh_dir = os.path.expanduser("~/.ssh")
key_path = os.path.join(ssh_dir, "gcp_dao_vang")
host = "136.110.29.208"
user = "ubuntu"

if not os.path.exists(key_path):
    print(f"[ERROR] SSH Key not found at {key_path}")
    sys.exit(1)

key = paramiko.Ed25519Key.from_private_key_file(key_path)
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

print(f"==> Connecting to Google Cloud Server ({user}@{host}:22)...")
client.connect(host, port=22, username=user, pkey=key, timeout=15)
print("[OK] Connected successfully!\n")

commands = [
    ("Kiểm tra trạng thái Git", "cd /home/ubuntu/dao_vang && git status --short"),
    ("Đồng bộ mã nguồn mới nhất từ GitHub origin/main", "cd /home/ubuntu/dao_vang && git fetch origin main && git reset --hard origin/main && git clean -fd"),
    ("Dọn dẹp lock files cũ", "cd /home/ubuntu/dao_vang && rm -f data/web.lock data_live/web.lock data/scanner.lock data_live/scanner.lock"),
    ("Dừng container cũ", "cd /home/ubuntu/dao_vang && docker compose down"),
    ("Build và khởi động lại container mới", "cd /home/ubuntu/dao_vang && docker compose up -d --build --force-recreate"),
    ("Kiểm tra danh sách container", "cd /home/ubuntu/dao_vang && sleep 3 && docker compose ps"),
    ("Kiểm tra API Health Endpoint", "curl -s -w '\nHTTP_STATUS:%{http_code}\n' http://localhost:8000/api/status"),
]

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
        print(line, end="")
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        print(f"[WARN] Command exited with code: {exit_status}")

client.close()
print("\n==> [COMPLETE] Deployment on Google Server 136.110.29.208 finished successfully!")
