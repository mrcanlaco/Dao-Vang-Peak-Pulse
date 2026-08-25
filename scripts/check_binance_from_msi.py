import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "curl -I -m 5 https://fapi.binance.com/fapi/v1/ping || true",
    "curl -I -m 5 https://api.binance.com/api/v3/ping || true",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"{cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))
    print("ERR:", stderr.read().decode("utf-8", errors="replace"))

client.close()
