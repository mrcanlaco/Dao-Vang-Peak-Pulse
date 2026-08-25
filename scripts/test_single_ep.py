import time
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

for ep in ["/api/status", "/api/signals", "/api/tracking-watchlist", "/api/coin/TACUSDT", "/api/coin/TACUSDT/deep-analysis", "/api/coin/BTCUSDT"]:
    t0 = time.time()
    cmd = f"curl -s -w '\nCODE:%{{http_code}} TIME:%{{time_total}}s\n' http://localhost:8000{ep}"
    stdin, stdout, stderr = client.exec_command(cmd)
    res = stdout.read().decode("utf-8", errors="replace")
    print(f"[{time.time()-t0:.2f}s] {ep} => {res.strip()[-30:]}")

client.close()
