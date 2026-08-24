import os
import sys
import time
from pathlib import Path
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def load_env(path=".env.remote"):
    env = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def main():
    env = load_env()
    host = env.get("SSH_HOST", "100.120.176.52")
    port = int(env.get("SSH_PORT", "22"))
    user = env.get("SSH_USER", "mrcanlaco")
    password = env.get("SSH_PASS", "Hailong200%")

    print(f"Connecting to {user}@{host}:{port}...")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        client.connect(
            hostname=host,
            port=port,
            username=user,
            password=password,
            timeout=15,
            banner_timeout=15,
            auth_timeout=15,
        )
        print("Connected successfully!")
    except Exception as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    # Find dao_vang directory
    find_cmd = "find ~ -maxdepth 3 -name 'docker-compose.yml' -path '*/dao_vang/*' 2>/dev/null | head -n 1"
    _, stdout, _ = client.exec_command(find_cmd)
    compose_path = stdout.read().decode().strip()

    if compose_path:
        project_dir = os.path.dirname(compose_path)
    else:
        # Fallback to standard locations
        check_dirs = ["~/dao_vang", "~/Coding/dao_vang", "/home/mrcanlaco/dao_vang", "/home/mrcanlaco/Coding/dao_vang"]
        project_dir = "~/dao_vang"
        for d in check_dirs:
            _, stdout, _ = client.exec_command(f"test -f {d}/docker-compose.yml && echo 'found'")
            if stdout.read().decode().strip() == "found":
                project_dir = d
                break

    print(f"Target Project Directory on MSI Server: {project_dir}")

    commands = [
        f"cd {project_dir} && git status --short",
        f"cd {project_dir} && git pull origin main",
        f"cd {project_dir} && rm -f data/web.lock data_live/web.lock",
        f"cd {project_dir} && docker compose build",
        f"cd {project_dir} && docker compose up -d",
        f"cd {project_dir} && sleep 3 && docker compose ps",
        "curl -s -o /dev/null -w 'API Health Check HTTP Status: %{http_code}\n' http://localhost:8000/api/status || true",
    ]

    for cmd in commands:
        print(f"\n---> Running: {cmd}")
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)
        while True:
            line = stdout.readline()
            if not line:
                break
            print(line, end="")
        exit_status = stdout.channel.recv_exit_status()
        if exit_status != 0:
            err = stderr.read().decode()
            if err:
                print(f"Error (code {exit_status}): {err}")

    client.close()
    print("\nDeployment to Ubuntu MSI server finished successfully!")

if __name__ == '__main__':
    main()
