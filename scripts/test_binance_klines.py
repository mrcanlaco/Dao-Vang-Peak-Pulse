import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    "curl -s 'https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=5' | head -c 200",
    "curl -s 'https://fapi.binance.com/fapi/v1/klines?symbol=TACUSDT&interval=1h&limit=5' | head -c 200",
    "curl -s 'https://api.binance.com/api/v3/klines?symbol=TACUSDT&interval=1h&limit=5' | head -c 200",
]

for cmd in cmds:
    print(f"\n---> {cmd}")
    stdin, stdout, stderr = client.exec_command(f"{cmd}")
    print(stdout.read().decode("utf-8", errors="replace"))

client.close()
