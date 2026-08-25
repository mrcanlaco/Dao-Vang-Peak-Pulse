import json
import time
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

time.sleep(3)
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

stdin, stdout, stderr = client.exec_command("curl -s http://localhost:8000/api/system-history")
raw = stdout.read().decode("utf-8", errors="replace")
try:
    data = json.loads(raw)
    stats = data.get("data_stats", [])
    print(f"Total tables/views reported in system history: {len(stats)}")
    for row in stats:
        print(f"  - {row.get('table')}: rows={row.get('rows')} max_time={row.get('max_time')}")
except Exception as e:
    print("Error parsing:", e)
    print("Raw:", raw[:300])

client.close()
