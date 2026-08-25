import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "docker compose -f ~/dao_vang/docker-compose.yml ps",
    "curl -s http://localhost:8000/api/status",
    "curl -s http://localhost:8000/api/signals | head -c 300",
    "curl -s http://localhost:8000/api/candidates | head -c 300",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"{cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
