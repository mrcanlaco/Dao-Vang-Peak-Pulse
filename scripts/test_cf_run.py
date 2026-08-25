import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmd = "docker run --rm --network host -v /home/mrcanlaco/dao_vang/cloudflared:/etc/cloudflared cloudflare/cloudflared:latest tunnel --config /etc/cloudflared/config.yml run"
stdin, stdout, stderr = client.exec_command(f"timeout 6 {cmd}")
print("STDOUT:", stdout.read().decode("utf-8", errors="replace"))
print("STDERR:", stderr.read().decode("utf-8", errors="replace"))

client.close()
