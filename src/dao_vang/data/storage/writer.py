import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


def compute_checksum(file_path: Path) -> str:
    """Compute SHA-256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def write_atomic(target_path: Path, data: bytes) -> str:
    """Atomically write data to target_path and return its SHA-256 checksum."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=target_path.parent, prefix=".tmp_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)

        checksum = compute_checksum(Path(temp_path))
        os.replace(temp_path, target_path)
        return checksum
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise


def write_jsonl_atomic(target_path: Path, items: list[dict[str, Any]]) -> str:
    """Atomically write a list of dictionaries as JSONL."""
    lines = [json.dumps(item, separators=(",", ":")) + "\n" for item in items]
    data = "".join(lines).encode("utf-8")
    return write_atomic(target_path, data)
