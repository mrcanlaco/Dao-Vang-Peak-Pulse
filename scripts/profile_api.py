import sys
import paramiko
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect("100.120.176.52", port=22, username="mrcanlaco", password="Hailong200%")

script = '''
import time
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.web.api_server import _scan_store, _alert_store, _settings, _ro_duckdb_connect

symbol = "TACUSDT"

print("--- 1. Testing BinanceClient klines ---")
t0 = time.time()
client = BinanceClient(timeout_seconds=2.0, max_retries=1)
try:
    k = client.get("fapi/v1/klines", {"symbol": symbol, "interval": "5m", "limit": 96})
    print(f"klines: {len(k)} items in {time.time()-t0:.2f}s")
except Exception as e:
    print(f"klines failed in {time.time()-t0:.2f}s: {e}")

print("--- 2. Testing BinanceClient fundingRate ---")
t0 = time.time()
try:
    f = client.get("fapi/v1/fundingRate", {"symbol": symbol, "limit": 96})
    print(f"fundingRate: {len(f)} items in {time.time()-t0:.2f}s")
except Exception as e:
    print(f"fundingRate failed in {time.time()-t0:.2f}s: {e}")

print("--- 3. Testing BinanceClient openInterestHist ---")
t0 = time.time()
try:
    o = client.get("fapi/v1/openInterestHist", {"symbol": symbol, "period": "5m", "limit": 96})
    print(f"openInterestHist: {len(o)} items in {time.time()-t0:.2f}s")
except Exception as e:
    print(f"openInterestHist failed in {time.time()-t0:.2f}s: {e}")

print("--- 4. Testing DuckDB feature_results query ---")
t0 = time.time()
try:
    conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
    df = conn.execute("SELECT * FROM feature_results WHERE symbol = ? ORDER BY feature_time DESC LIMIT 1", [symbol]).df()
    conn.close()
    print(f"feature_results: {len(df)} rows in {time.time()-t0:.2f}s")
except Exception as e:
    print(f"feature_results query failed in {time.time()-t0:.2f}s: {e}")
'''

stdin, stdout, stderr = client.exec_command(f'cd ~/dao_vang && docker compose exec -T web python -c """{script}"""')
print(stdout.read().decode("utf-8", errors="replace"))
print(stderr.read().decode("utf-8", errors="replace"))

client.close()
