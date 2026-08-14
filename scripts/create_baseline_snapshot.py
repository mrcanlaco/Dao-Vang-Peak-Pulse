import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from dao_vang.domain.time import SYSTEM_TIMEZONE_NAME, system_now


def hash_file(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    parser = argparse.ArgumentParser(description="Create a frozen baseline snapshot")
    parser.add_argument("--db-path", type=str, default="data/dev.duckdb.ro_copy", help="Path to DB")
    parser.add_argument("--baseline-id", type=str, required=True, help="ID of baseline (e.g., v0_initial)")
    parser.add_argument(
        "--label-version",
        type=str,
        default="distribution_short_v1",
        help="Immutable label contract version used by the snapshot",
    )
    parser.add_argument(
        "--feature-set-version",
        type=str,
        default="features_v1",
        help="Immutable feature contract version used by the snapshot",
    )
    args = parser.parse_args()

    artifacts_dir = Path("artifacts/baselines") / args.baseline_id
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Get git commit SHA
    try:
        commit_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except subprocess.CalledProcessError:
        commit_sha = "unknown"
        
    # 2. Get python lockfile hash
    lockfile_hash = hash_file(Path("uv.lock"))
    
    # 3. Snapshot DB
    source_db = Path(args.db_path)
    snapshot_db_path = artifacts_dir / "dao_vang_snapshot.duckdb"
    
    if source_db.exists():
        shutil.copy2(source_db, snapshot_db_path)
    else:
        print(f"Warning: Source DB not found at {source_db}")
    
    db_hash = hash_file(snapshot_db_path)
    
    # 4. Save manifest
    manifest = {
        "baseline_id": args.baseline_id,
        "created_at": system_now().isoformat(),
        "commit_sha": commit_sha,
        "label_version": args.label_version,
        "feature_set_version": args.feature_set_version,
        "environment": {
            "timezone": SYSTEM_TIMEZONE_NAME,
            "seed": 42
        },
        "datasets": {
            "database_path": str(snapshot_db_path.as_posix()),
            "database_sha256": db_hash,
            "universe": "all_usdt_futures",
            "window": "historical_to_creation"
        },
        "dependencies": {
            "lockfile": "uv.lock",
            "lockfile_sha256": lockfile_hash
        }
    }
    
    with open(artifacts_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"Created baseline snapshot {args.baseline_id} at {artifacts_dir}")

if __name__ == "__main__":
    main()
