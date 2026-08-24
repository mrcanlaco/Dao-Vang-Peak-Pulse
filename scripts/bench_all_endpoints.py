import time
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

endpoints = [
    "/api/status",
    "/api/signals",
    "/api/candidates",
    "/api/candidates/compare",
    "/api/watchlist",
    "/api/tracking-watchlist",
    "/api/market",
    "/api/audit",
    "/api/models",
    "/api/scanner/telemetry",
    "/api/coin/TACUSDT",
    "/api/coin/TACUSDT/deep-analysis",
]

for ep in endpoints:
    t0 = time.time()
    cmd = f"curl -m 4 -s -w '\nCODE:%{{http_code}} TIME:%{{time_total}}s' http://localhost:8000{ep}"
    stdin, stdout, stderr = client.exec_command(cmd, timeout=5)
    try:
        res = stdout.read().decode("utf-8", errors="replace")
        elapsed = time.time() - t0
        print(f"[{elapsed:.2f}s] {ep} => {res.strip()[-30:]}")
    except Exception as e:
        print(f"[TIMEOUT] {ep} => {e}")

client.close()
