import json
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

stdin, stdout, stderr = client.exec_command("curl -s http://localhost:8000/api/signals")
raw = stdout.read().decode("utf-8", errors="replace")
try:
    data = json.loads(raw)
    print(f"Total signals returned: {len(data)}")
    if data:
        print("Sample signal 0:", json.dumps(data[0], indent=2))
except Exception as e:
    print("Error parsing JSON:", e)
    print("Raw output snippet:", raw[:500])

client.close()
