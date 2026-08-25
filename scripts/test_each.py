import time
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

eps = ["/api/status", "/api/signals", "/api/tracking-watchlist", "/api/coin/BTCUSDT", "/api/coin/TACUSDT"]
for ep in eps:
    t0 = time.time()
    cmd = f"curl -s -w '\nHTTP: %{{http_code}} in %{{time_total}}s' http://localhost:8000{ep}"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    print(f"--> {ep} returned in {time.time()-t0:.2f}s: {out.strip()[-30:]}")

client.close()
