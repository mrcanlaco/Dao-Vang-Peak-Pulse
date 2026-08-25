import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

code = """
import time, duckdb
t0 = time.time()
conn = duckdb.connect('data_live/live.duckdb', read_only=True)
print(f'Connected in {time.time()-t0:.3f}s')

t0 = time.time()
feature_rows = conn.execute('SELECT count(*) FROM feature_results WHERE symbol = ?', ['TACUSDT']).fetchone()
print(f'feature_results count: {feature_rows} in {time.time()-t0:.3f}s')

t0 = time.time()
kline_count = conn.execute('SELECT count(*) FROM kline WHERE symbol = ?', ['TACUSDT']).fetchone()
print(f'kline count: {kline_count} in {time.time()-t0:.3f}s')
"""

cmd = "docker exec -i dao_vang_web python"
stdin, stdout, stderr = client.exec_command(cmd)
stdin.write(code)
stdin.channel.shutdown_write()
print("STDOUT:", stdout.read().decode("utf-8", errors="replace"))
print("STDERR:", stderr.read().decode("utf-8", errors="replace"))
client.close()
