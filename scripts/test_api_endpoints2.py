import json
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

endpoints = [
    "/api/audit",
    "/api/market",
    "/api/scanner/telemetry",
    "/api/models",
    "/api/coin/TACUSDT",
    "/api/coin/TACUSDT/deep-analysis",
]

for ep in endpoints:
    cmd = f"curl -s -w '\nHTTP_CODE: %{{http_code}}\nTIME: %{{time_total}}s\n' http://localhost:8000{ep} | head -c 200"
    stdin, stdout, stderr = client.exec_command(cmd)
    res = stdout.read().decode("utf-8", errors="replace")
    print(f"\n>>> Endpoint: {ep}")
    print(res)

client.close()
