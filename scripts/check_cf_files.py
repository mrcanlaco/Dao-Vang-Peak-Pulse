import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "ls -la ~/dao_vang/cloudflared/",
    "docker inspect dao_vang_cloudflared | grep -A 10 'Mounts' || true",
    "docker run --rm -v /home/mrcanlaco/dao_vang/cloudflared:/etc/cloudflared cloudflare/cloudflared:latest tunnel --config /etc/cloudflared/config.yml ingress validate || true",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"{cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
