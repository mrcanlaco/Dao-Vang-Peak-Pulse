import urllib.request
import json
import time

time.sleep(2)
url = "https://trade.comaygiauco.com/api/status"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        print("HTTP Status:", resp.status)
        print("Response Body:\n", body)
except Exception as e:
    print("Error:", e)
