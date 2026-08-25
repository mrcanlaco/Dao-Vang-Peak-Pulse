import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

code = """
import time, glob, duckdb
snapshots = glob.glob('data_live/.*.ro_copy')
print('Found snapshots:', snapshots)
if not snapshots:
    import shutil
    shutil.copy2('data_live/live.duckdb', 'data_live/test_snap.ro_copy')
    snap = 'data_live/test_snap.ro_copy'
else:
    snap = snapshots[0]

conn = duckdb.connect(snap, read_only=True)
t0 = time.time()
q1 = conn.execute('SELECT count(*) FROM feature_results WHERE symbol = ?', ['TACUSDT']).fetchone()
print(f'feature_results for TACUSDT: {q1} in {time.time()-t0:.3f}s')

t0 = time.time()
rows = conn.execute('''
WITH f AS (
    SELECT feature_time, symbol, oi_change_24h, funding_rate_raw,
           taker_buy_ratio, price_ret_5m, volume_percentile_24h
    FROM feature_results
    WHERE symbol = ?
    ORDER BY feature_time DESC
    LIMIT 1500
)
SELECT f.feature_time, k.open, k.high, k.low, k.close,
       k.volume_base, k.taker_buy_base,
       f.oi_change_24h, f.funding_rate_raw,
       f.taker_buy_ratio, f.price_ret_5m, f.volume_percentile_24h
FROM f
LEFT JOIN kline k
    ON k.symbol = ?
    AND k.interval = '5m'
    AND k.close_time = f.feature_time
ORDER BY f.feature_time DESC
''', ['TACUSDT', 'TACUSDT']).fetchall()
print(f'CTE Join Query returned {len(rows)} rows in {time.time()-t0:.3f}s')
"""

cmd = "docker exec -i dao_vang_web python"
stdin, stdout, stderr = client.exec_command(cmd)
stdin.write(code)
stdin.channel.shutdown_write()
print("STDOUT:", stdout.read().decode("utf-8", errors="replace"))
print("STDERR:", stderr.read().decode("utf-8", errors="replace"))
client.close()
