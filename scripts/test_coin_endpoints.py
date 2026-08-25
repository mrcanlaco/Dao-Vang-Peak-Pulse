import time
import urllib.request
import json
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

symbol = "TACUSDT"
endpoints = [
    f"/api/coin/{symbol}",
    f"/api/coin/{symbol}/chart?interval=5m",
    f"/api/coin/{symbol}/deep-analysis",
]

print(f"=== Testing coin endpoints for {symbol} via https://trade.comaygiauco.com ===")
for ep in endpoints:
    url = f"https://trade.comaygiauco.com{ep}"
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            dt = time.time() - t0
            print(f"GET {ep} => HTTP {resp.status}, size={len(data)} bytes, time={dt:.2f}s")
            print("Snippet:", data.decode("utf-8", errors="replace")[:150])
    except Exception as e:
        dt = time.time() - t0
        print(f"GET {ep} => ERROR after {dt:.2f}s: {e}")

print(f"\n=== Testing inside MSI server ===")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

for ep in endpoints:
    cmd = f"curl -w '\\nTIME: %{{time_total}}s, STATUS: %{{http_code}}\\n' -s 'http://localhost:8000{ep}'"
    print(f"\n---> {ep}")
    stdin, stdout, stderr = client.exec_command(cmd)
    res = stdout.read().decode("utf-8", errors="replace")
    print(res[:300] + ("..." if len(res) > 300 else ""))

client.close()
