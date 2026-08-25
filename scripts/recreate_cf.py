import sys
import time
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

stdin, stdout, stderr = client.exec_command("cd ~/dao_vang && docker compose up -d --force-recreate cloudflared")
print(stdout.read().decode("utf-8", errors="replace"))

time.sleep(3)
stdin, stdout, stderr = client.exec_command("docker logs --tail=30 dao_vang_cloudflared")
print(stdout.read().decode("utf-8", errors="replace"))

client.close()
