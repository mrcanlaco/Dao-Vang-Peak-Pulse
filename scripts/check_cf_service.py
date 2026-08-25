import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "systemctl list-units | grep -i cloudflare || true",
    "journalctl -u cloudflared -n 30 --no-pager || true",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"{cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
