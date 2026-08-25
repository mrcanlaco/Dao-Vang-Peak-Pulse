import sys
import paramiko
if sys.platform == win32:
    sys.stdout.reconfigure(encoding=utf-8, errors=replace)

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect(100.120.176.52, port=22, username=mrcanlaco, password=Hailong200%)

code = "
import time
from dao_vang.data.collectors.binance_client import BinanceClient
b = BinanceClient()

for ep, params in [
    ('fapi/v1/klines', {'symbol': 'TACUSDT', 'interval': '5m', 'limit': 96}),
    ('fapi/v1/fundingRate', {'symbol': 'TACUSDT', 'limit': 96}),
    ('fapi/v1/openInterestHist', {'symbol': 'TACUSDT', 'period': '5m', 'limit': 96}),
]:
    t0 = time.time()
    try:
        res = b.get(ep, params)
        print(f'{ep}: {len(res) if res else 0} items in {time.time()-t0:.3f}s')
    except Exception as e:
        print(f'{ep} FAILED in {time.time()-t0:.3f}s: {e}')
"

cmd = docker exec -i dao_vang_web python
stdin, stdout, stderr = client.exec_command(cmd)
stdin.write(code)
stdin.channel.shutdown_write()
print(STDOUT:, stdout.read().decode(utf-8, errors=replace))
print(STDERR:, stderr.read().decode(utf-8, errors=replace))
client.close()
