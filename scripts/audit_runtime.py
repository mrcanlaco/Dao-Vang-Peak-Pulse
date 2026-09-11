"""Read-only runtime audit; authenticate with the environment, never print secrets.

Run inside the web container, or locally with --base-url and matching settings.
Only the normal login endpoint is posted to; no scans or alerts are triggered.
"""

from __future__ import annotations

import argparse
import json
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from dao_vang.config.settings import AppSettings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    settings = AppSettings()
    cookie = ""
    failures = 0

    def request(path, data=None, authenticated=True):
        headers = {"Content-Type": "application/json"}
        if authenticated and cookie:
            headers["Cookie"] = cookie
        req = Request(base + path, headers=headers, data=data)
        start = time.monotonic()
        try:
            response = urlopen(req, timeout=45)
        except HTTPError as exc:
            response = exc
        with response:
            body = response.read()
            try:
                payload = json.loads(body)
            except (ValueError, UnicodeDecodeError):
                payload = {"bytes": len(body)}
            return response.status, payload, response.headers, round(time.monotonic() - start, 3)

    for path in ("/api/health", "/api/auth/status", "/api/status", "/%2e%2e/%2e%2e/pyproject.toml"):
        status, payload, _, seconds = request(path, authenticated=False)
        expected = 401 if path == "/api/status" else 404 if "%2e" in path else 200
        failures += status != expected
        print(json.dumps({"path": path, "status": status, "expected": expected, "seconds": seconds,
                          "data": payload if path in ("/api/health", "/api/auth/status") else None}), flush=True)

    if not settings.web.access_password:
        print(json.dumps({"error": "Access password is not configured"}))
        return 1
    status, _, headers, _ = request("/api/auth/verify", json.dumps({"password": settings.web.access_password}).encode())
    if status != 200:
        print(json.dumps({"error": "Authentication failed", "status": status}))
        return 1
    cookie = headers.get("Set-Cookie", "").split(";", 1)[0]

    for path in (
        "/api/status", "/api/signals", "/api/candidates", "/api/candidates/compare",
        "/api/audit", "/api/market", "/api/watchlist", "/api/tracking-watchlist",
        "/api/scanner/telemetry", "/api/models", "/api/experiments",
        "/api/forward-test/models", "/api/system-history", "/api/research/reports",
        "/api/alpha-lab/summary", "/api/system/update-status", "/api/ai/config",
        "/api/coin/BTCUSDT", "/api/coin/BTCUSDT/klines?limit=5",
    ):
        try:
            status, payload, _, seconds = request(path)
            failures += status != 200
            summary = {"count": len(payload)} if isinstance(payload, list) else {"keys": list(payload)}
            if path in ("/api/status", "/api/scanner/telemetry", "/api/system/update-status"):
                summary = payload
            print(json.dumps({"path": path, "status": status, "seconds": seconds, "summary": summary}, default=str), flush=True)
        except Exception as exc:
            failures += 1
            print(json.dumps({"path": path, "error": type(exc).__name__}), flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
