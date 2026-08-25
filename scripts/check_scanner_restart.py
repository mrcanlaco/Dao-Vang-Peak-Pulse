import sys
import time
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

print("Restarting dao_vang_scanner...")
stdin, stdout, stderr = client.exec_command("cd ~/dao_vang && docker compose restart scanner")
print(stdout.read().decode("utf-8", errors="replace"))

for i in range(12):
    time.sleep(5)
    print(f"\n--- Logs after {(i+1)*5}s ---")
    stdin, stdout, stderr = client.exec_command("cd ~/dao_vang && docker logs --tail=25 dao_vang_scanner")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
