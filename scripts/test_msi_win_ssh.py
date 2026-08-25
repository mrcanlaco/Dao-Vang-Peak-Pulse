import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
try:
    client.connect("100.88.76.126", port=22, username="mrcanlaco", password="Hailong200%", timeout=5)
    stdin, stdout, stderr = client.exec_command("wsl -l -v")
    print("SSH SUCCESS on 100.88.76.126:")
    print(stdout.read().decode("utf-8", errors="replace"))
    client.close()
except Exception as e:
    print("SSH FAIL on 100.88.76.126:", e)
