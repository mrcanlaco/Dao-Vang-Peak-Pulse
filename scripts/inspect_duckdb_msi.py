import json
import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

cmds = [
    ("Heartbeat", "cat ~/dao_vang/data/scanner_heartbeat.json 2>/dev/null || cat ~/dao_vang/data_live/scanner_heartbeat.json 2>/dev/null"),
    ("Runtime State", "cat ~/dao_vang/data/scanner_runtime_state.json 2>/dev/null || cat ~/dao_vang/data_live/scanner_runtime_state.json 2>/dev/null"),
    ("Watchlist", "cat ~/dao_vang/data/watchlist.json 2>/dev/null || cat ~/dao_vang/data_live/watchlist.json 2>/dev/null"),
    ("Latest Scan Results from DuckDB", 'docker exec dao_vang_web python -c "import duckdb; conn=duckdb.connect(\'data_live/live.duckdb\', read_only=True); print(\'Total scan_results:\', conn.execute(\'SELECT count(*) FROM scan_results\').fetchone()[0]); print(\'Latest 5 scan_results:\'); print(conn.execute(\'SELECT scan_time, symbol, final_score, alert_level FROM scan_results ORDER BY scan_time DESC LIMIT 5\').fetchall()); print(\'Total alerts in alert_history:\', conn.execute(\'SELECT count(*) FROM alert_history\').fetchone()[0]); print(\'Latest 5 alerts:\'); print(conn.execute(\'SELECT signal_time, symbol, score, alert_level, status FROM alert_history ORDER BY signal_time DESC LIMIT 5\').fetchall())"'),
]

for title, cmd in cmds:
    print(f"\n====================== {title} ======================")
    stdin, stdout, stderr = client.exec_command(cmd)
    out = stdout.read().decode("utf-8", errors="replace")
    print(out)
    err = stderr.read().decode("utf-8", errors="replace")
    if err:
        print("ERR:", err)

client.close()
