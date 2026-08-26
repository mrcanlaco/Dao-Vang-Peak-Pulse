import urllib.request
import json
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

print("=== 1. Testing https://daovang.comaygiauco.com from client machine ===")
for path in ["/", "/api/status", "/api/signals", "/api/candidates"]:
    url = f"https://daovang.comaygiauco.com{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            print(f"GET {url} => HTTP {resp.status}, length={len(data)}")
            if path == "/":
                print("HTML content snippet:\n", data.decode("utf-8", errors="replace")[:400])
            else:
                print("JSON snippet:\n", data.decode("utf-8", errors="replace")[:200])
    except Exception as e:
        print(f"GET {url} => ERROR: {e}")

print("\n=== 2. Testing inside MSI server ===")
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "docker compose ps",
    "cat /etc/cloudflared/config.yml 2>/dev/null || cat ~/dao_vang/configs/cloudflared.yml 2>/dev/null || true",
    "docker logs --tail=30 dao_vang_cloudflared",
    "curl -s http://localhost:8000/ | head -n 30",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"cd ~/dao_vang && {cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
