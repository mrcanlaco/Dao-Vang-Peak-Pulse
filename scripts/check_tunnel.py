import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "docker inspect dao_vang_cloudflared | grep -A 20 -B 5 'Args' || true",
    "docker exec dao_vang_cloudflared cat /etc/cloudflared/config.yml 2>/dev/null || true",
    "cat ~/dao_vang/docker-compose.yml",
    "ps aux | grep -i cloudflare || true",
    "ls -la ~/.cloudflared/ /etc/cloudflared/ 2>/dev/null || true",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"cd ~/dao_vang && {cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
