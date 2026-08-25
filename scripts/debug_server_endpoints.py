import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "curl -s -w '\\nTIME: %{time_total}s, HTTP: %{http_code}\\n' 'http://localhost:8000/api/coin/TACUSDT' | head -c 200",
    "curl -s -w '\\nTIME: %{time_total}s, HTTP: %{http_code}\\n' 'http://localhost:8000/api/coin/TACUSDT/chart?interval=5m' | head -c 200",
    "curl -s -w '\\nTIME: %{time_total}s, HTTP: %{http_code}\\n' 'http://localhost:8000/api/coin/TACUSDT/deep-analysis' | head -c 200",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"{cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
