import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "ls -lh ~/dao_vang/data/",
    "ls -lh ~/dao_vang/data_live/ 2>/dev/null || true",
]

for cmd in cmds:
    print(f"\n====================== {cmd} ======================")
    stdin, stdout, stderr = client.exec_command(cmd)
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
