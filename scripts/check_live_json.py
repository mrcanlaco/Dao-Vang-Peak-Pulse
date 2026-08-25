import urllib.request
import json
import sys
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

endpoints = ["/api/status", "/api/signals", "/api/candidates", "/api/system-history"]

for ep in endpoints:
    url = f"https://trade.comaygiauco.com{ep}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            print(f"GET {ep} => HTTP {resp.status}, size={len(data)} bytes")
    except Exception as e:
        print(f"GET {ep} => ERROR: {e}")
