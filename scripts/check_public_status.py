import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "curl -s -w '\nSTATUS: %{http_code}\n' http://localhost:8000/api/status",
    "curl -s -w '\nSIGNALS: %{http_code}\n' http://localhost:8000/api/signals | head -c 200",
    "docker compose ps",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"cd ~/dao_vang && {cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
