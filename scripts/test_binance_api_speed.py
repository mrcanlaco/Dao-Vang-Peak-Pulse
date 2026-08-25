import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

code = """
import time
from dao_vang.data.collectors.binance_client import BinanceClient
t0 = time.time()
b_client = BinanceClient()
klines = b_client.get('fapi/v1/klines', {'symbol': 'TACUSDT', 'interval': '5m', 'limit': 96})
print(f'Binance klines: {len(klines)} candles in {time.time()-t0:.3f}s')
"""

cmd = "docker exec -i dao_vang_web python"
stdin, stdout, stderr = client.exec_command(cmd)
stdin.write(code)
stdin.channel.shutdown_write()
print("STDOUT:", stdout.read().decode("utf-8", errors="replace"))
print("STDERR:", stderr.read().decode("utf-8", errors="replace"))
client.close()
