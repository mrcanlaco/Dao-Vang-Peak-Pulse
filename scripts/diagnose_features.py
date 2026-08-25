import json
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    ("Status API", "curl -s http://localhost:8000/api/status"),
    ("Signals API (Radar count)", "curl -s http://localhost:8000/api/signals | head -c 500"),
    ("Candidates API", "curl -s http://localhost:8000/api/candidates | head -c 500"),
    ("Watchlist API", "curl -s http://localhost:8000/api/watchlist"),
    ("Telemetry API", "curl -s http://localhost:8000/api/radar-telemetry"),
    ("Scanner Heartbeat File", "cd ~/dao_vang && (cat data/scanner_heartbeat.json 2>/dev/null || cat data_live/scanner_heartbeat.json 2>/dev/null)"),
    ("Scanner Docker Logs", "docker logs --tail=25 dao_vang_scanner"),
]

for title, cmd in cmds:
    print(f"\n====================== {title} ======================")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=10)
    out = stdout.read().decode("utf-8", errors="replace")
    print(out)
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        print("ERR:", err)

client.close()
