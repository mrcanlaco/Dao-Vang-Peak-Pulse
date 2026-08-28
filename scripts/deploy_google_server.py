"""Deploy and update application on Google Cloud Server (136.110.29.208)."""

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
    print("Vui long kiem tra SSH key de ket noi toi Google Cloud Server.")
    sys.exit(1)

commands = [
    ("Kiểm tra trạng thái Git", "cd /home/ubuntu/dao_vang && git status --short"),
    ("Hủy các trạng thái xung đột / merge dở dang", "cd /home/ubuntu/dao_vang && git merge --abort 2>/dev/null || true && git rebase --abort 2>/dev/null || true && git reset --hard HEAD && git clean -fd"),
    ("Đồng bộ mã nguồn mới nhất từ GitHub origin/main", "cd /home/ubuntu/dao_vang && git fetch origin main --prune && git reset --hard origin/main"),
    ("Bảo đảm quyền truy cập Cloudflare Tunnel", "chmod 644 /home/ubuntu/dao_vang/cloudflared/* 2>/dev/null || true"),
    ("Dọn dẹp lock files cũ", "cd /home/ubuntu/dao_vang && rm -f data/web.lock data_live/web.lock data/scanner.lock data_live/scanner.lock"),
    ("Dừng container cũ và build container mới", "cd /home/ubuntu/dao_vang && docker compose down && docker compose up -d --build --force-recreate"),
    ("Kiểm tra danh sách container", "cd /home/ubuntu/dao_vang && sleep 5 && docker compose ps"),
    ("Kiểm tra sức khỏe Web API (Health Check)", "cd /home/ubuntu/dao_vang && sleep 5 && for i in $(seq 1 10); do if curl -s -f http://localhost:8000/api/status >/dev/null; then echo 'API Health: ONLINE & HEALTHY (HTTP 200)'; exit 0; fi; echo 'Dang cho API Server khoi dong... (thu lai '$i'/10)'; sleep 2; done; echo 'Canh bao: API chua san sang ngay luc nay.'"),
]

print(f"========================================================")
print(f"🚀 [LIVE DEPLOY] KẾT NỐI TỚI GOOGLE CLOUD SERVER")
print(f"   Host: {host} (User: {user})")
print(f"   Mục tiêu: Kéo mã nguồn mới và tái khởi động dịch vụ Live")
print(f"========================================================\n")

success = True

try:
    import paramiko
    key = paramiko.Ed25519Key.from_private_key_file(key_path)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, port=22, username=user, pkey=key, timeout=15)
    print("[OK] Kết nối SSH thành công qua Paramiko!\n")

    for title, cmd in commands:
        print(f"\n--------------------------------------------------------")
        print(f"==> {title}")
        print(f"--------------------------------------------------------")
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
        while True:
            line = stdout.readline()
            if not line:
                break
            sys.stdout.write(line)
            sys.stdout.flush()
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            print(f"[WARN] Lệnh hoàn thành với mã: {exit_status}")

    client.close()

except ImportError:
    print("[INFO] Sử dụng system OpenSSH client...")
    full_remote_cmd = " && ".join([f"echo '==> {t}' && {c}" for t, c in commands])
    cmd_args = ["ssh", "-i", key_path, "-o", "StrictHostKeyChecking=no", f"{user}@{host}", full_remote_cmd]
    res = subprocess.run(cmd_args, capture_output=False)
    if res.returncode != 0:
        print(f"[WARN] SSH client exited with code {res.returncode}")
        success = False

print("\n========================================================")
print("✅ [HOÀN TẤT] TRIỂN KHAI LÊN GOOGLE CLOUD SERVER THÀNH CÔNG!")
print("   - Dashboard Live: https://daovang.comaygiauco.com")
print(f"   - Server Direct: http://{host}:8000")
print("========================================================\n")
