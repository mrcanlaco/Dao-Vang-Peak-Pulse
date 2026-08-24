import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmd = "curl -s -w '\nHTTP_CODE: %{http_code}\nTIME_TOTAL: %{time_total}s\n' http://localhost:8000/api/system-history | head -c 200"
stdin, stdout, stderr = client.exec_command(cmd)
print("=== /api/system-history Check ===")
print(stdout.read().decode("utf-8", errors="replace"))

cmd_ps = "cd ~/dao_vang && docker compose ps"
stdin, stdout, stderr = client.exec_command(cmd_ps)
print("=== Docker Containers Status ===")
print(stdout.read().decode("utf-8", errors="replace"))
client.close()
