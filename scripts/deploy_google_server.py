"""Deploy a committed revision to GCP without discarding local server changes."""
import argparse
import re
import shlex
import subprocess
from pathlib import Path

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--revision", help="Full 40-character Git commit; defaults to local HEAD")
    parser.add_argument("--apply", action="store_true", help="Apply after reviewing the target")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    revision = args.revision or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        parser.error("revision must be a full Git commit hash")
    key = Path.home() / ".ssh" / "gcp_dao_vang"
    if not key.is_file():
        parser.error(f"SSH key not found: {key}")
    print(f"GCP: ubuntu@136.110.29.208; revision: {revision}")
    if not args.apply:
        print("Chay lai voi --apply de trien khai revision nay. Thay doi local chua commit se khong duoc gui.")
        return 0
    command = f"""
set -eu
cd /home/ubuntu/dao_vang
test "$(git branch --show-current)" = "main" || {{
  echo "Deployment stopped: server checkout is not on main."
  exit 1
}}
test -z "$(git status --porcelain --untracked-files=no)" || {{
  echo "Deployment stopped: preserve and review tracked local changes first."
  exit 1
}}
git fetch origin main --prune
git merge --ff-only {shlex.quote(revision)}
test "$(git rev-parse HEAD)" = {shlex.quote(revision)}
test -z "$(git status --porcelain)" || {{
  echo "Deployment stopped: unexpected untracked files remain after update."
  exit 1
}}
export DAO_VANG_RUNTIME_UID="$(id -u)"
export DAO_VANG_RUNTIME_GID="$(id -g)"
bash scripts/prepare_runtime_permissions.sh --apply
docker compose build
docker compose up -d --no-build --wait --wait-timeout 180
curl --fail --silent --show-error http://localhost:8000/api/health
curl --fail --silent --show-error http://localhost:8000/api/ready
bash scripts/install_production_cron.sh --apply
"""
    return subprocess.run(["ssh", "-i", str(key), "-o", "BatchMode=yes", "-o",
        "ConnectTimeout=15", "ubuntu@136.110.29.208", command], check=False).returncode

if __name__ == "__main__":
    raise SystemExit(main())
