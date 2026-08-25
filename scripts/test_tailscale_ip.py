import urllib.request
import json

urls = [
    "http://100.120.176.52:8000/api/status",
    "http://100.120.176.52:8000/api/signals",
    "http://100.120.176.52:8000/api/candidates",
]

for url in urls:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = resp.read()
            print(f"GET {url} => HTTP {resp.status}, length={len(data)}")
            print("Snippet:", data.decode("utf-8", errors="replace")[:150])
    except Exception as e:
        print(f"GET {url} => ERROR: {e}")
