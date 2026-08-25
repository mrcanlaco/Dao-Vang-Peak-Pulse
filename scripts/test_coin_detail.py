import time
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

t0 = time.time()
cmd = "curl -m 15 -s -w '\nCODE:%{http_code} TIME:%{time_total}s\n' http://localhost:8000/api/coin/TACUSDT | head -c 300"
stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode("utf-8", errors="replace"))
print("Total client time:", time.time() - t0)

client.close()
