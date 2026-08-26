import urllib.request
import json

endpoints = [
    "/api/status",
    "/api/signals",
    "/api/candidates",
    "/api/system-history",
]

print("=== FINAL VERIFICATION OF https://daovang.comaygiauco.com ===")
for ep in endpoints:
    url = f"https://daovang.comaygiauco.com{ep}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list):
                print(f"✅ {ep}: HTTP {resp.status} - Returned {len(data)} items")
            elif isinstance(data, dict):
                print(f"✅ {ep}: HTTP {resp.status} - Status: {data.get('scanner_status', 'OK')}, Heartbeat: {data.get('heartbeat', '')}")
    except Exception as e:
        print(f"❌ {ep}: ERROR {e}")
