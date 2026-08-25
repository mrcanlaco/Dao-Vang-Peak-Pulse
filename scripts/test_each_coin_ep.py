import sys
import time
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

eps = [
    "/api/coin/TACUSDT",
    "/api/coin/TACUSDT/chart?interval=5m",
    "/api/coin/TACUSDT/deep-analysis",
]

for ep in eps:
    print(f"Testing {ep}...")
    t0 = time.time()
    cmd = f"curl -s --max-time 10 'http://localhost:8000{ep}'"
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    dt = time.time() - t0
    print(f"Result for {ep} in {dt:.2f}s: {out[:100]}\n")

client.close()
