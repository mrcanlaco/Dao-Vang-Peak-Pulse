import os
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "docker logs --tail=50 dao_vang_web",
    "docker logs --tail=50 dao_vang_scanner",
]

for cmd in cmds:
    print(f"\n====================== {cmd} ======================")
    stdin, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
