import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "docker compose ps",
    "docker logs --tail=100 dao_vang_scanner",
    "cat ~/dao_vang/data/scanner_heartbeat.json 2>/dev/null || true",
    "cat ~/dao_vang/data/scanner_runtime_state.json 2>/dev/null || true",
]

for cmd in cmds:
    print(f"\n====================== {cmd} ======================")
    stdin, stdout, stderr = client.exec_command(f"cd ~/dao_vang && {cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        print("ERR:", err)

client.close()
