import json
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
    "/api/market-overview",
    "/api/radar-telemetry",
]

for ep in endpoints:
    cmd = f"curl -s http://localhost:8000{ep}"
    stdin, stdout, stderr = client.exec_command(cmd)
    res = stdout.read().decode("utf-8", errors="replace")
    print(f"\n>>> Endpoint: {ep} (length: {len(res)})")
    try:
        data = json.loads(res)
        if isinstance(data, list):
            print(f"List with {len(data)} items")
            if len(data) > 0:
                print("First item:", json.dumps(data[0], indent=2)[:300])
        elif isinstance(data, dict):
            print(f"Dict with keys: {list(data.keys())}")
            print(json.dumps(data, indent=2)[:300])
    except Exception:
        print("Raw text:", res[:300])

client.close()
