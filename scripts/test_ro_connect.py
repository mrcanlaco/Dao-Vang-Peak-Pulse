import time
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmd = 'docker exec dao_vang_web python -c "import time, duckdb; t0=time.time(); conn=duckdb.connect(\'data_live/live.duckdb\', read_only=True); print(\'Connected in\', time.time()-t0, \'sec\'); print(\'Alerts:\', conn.execute(\'SELECT count(*) FROM alert_history\').fetchone()[0]); print(\'Scans:\', conn.execute(\'SELECT count(*) FROM scan_results\').fetchone()[0])"'
stdin, stdout, stderr = client.exec_command(cmd)
print(stdout.read().decode("utf-8", errors="replace"))
print("ERR:", stderr.read().decode("utf-8", errors="replace"))

client.close()
