import os
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "echo '=== Docker Containers ===' && cd ~/dao_vang && docker compose ps",
    "echo '=== Scanner Logs (last 50 lines) ===' && cd ~/dao_vang && docker compose logs --tail=50 scanner",
    "echo '=== Web Logs (last 30 lines) ===' && cd ~/dao_vang && docker compose logs --tail=30 web",
    "echo '=== Scanner Heartbeat ===' && cd ~/dao_vang && (cat data/scanner_heartbeat.json 2>/dev/null || cat data_live/scanner_heartbeat.json 2>/dev/null)",
    "echo '=== Scanner Runtime State ===' && cd ~/dao_vang && (cat data/scanner_runtime_state.json 2>/dev/null || cat data_live/scanner_runtime_state.json 2>/dev/null)",
    "echo '=== Watchlist ===' && cd ~/dao_vang && (cat data/watchlist.json 2>/dev/null || cat data_live/watchlist.json 2>/dev/null)",
    "echo '=== Candidate Comparison Snapshot ===' && cd ~/dao_vang && (head -n 20 data/candidate_filter_comparison.json 2>/dev/null || head -n 20 data_live/candidate_filter_comparison.json 2>/dev/null)",
    "echo '=== API /api/status ===' && curl -s http://localhost:8000/api/status",
    "echo '=== API /api/signals ===' && curl -s http://localhost:8000/api/signals",
]

for cmd in cmds:
    print(f"\n====================== {cmd} ======================")
    stdin, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode("utf-8", errors="replace"))
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        print("STDERR:", err)

client.close()
