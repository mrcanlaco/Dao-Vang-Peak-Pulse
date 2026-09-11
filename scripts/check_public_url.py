"""Verify public reachability and authentication without credentials or SSH."""
import argparse
from urllib.error import HTTPError
from urllib.request import urlopen

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="https://daovang.comaygiauco.com")
    args = parser.parse_args()
    failed = False
    for path, expected in (("/", 200), ("/api/health", 200), ("/api/auth/status", 200), ("/api/status", 401)):
        try:
            with urlopen(args.url.rstrip("/") + path, timeout=15) as response:
                status = response.status
        except HTTPError as exc:
            status = exc.code
        except OSError as exc:
            print(f"{path}: {type(exc).__name__}")
            failed = True
            continue
        print(f"{path}: HTTP {status} (expected {expected})")
        failed |= status != expected
    return int(failed)

if __name__ == "__main__":
    raise SystemExit(main())
