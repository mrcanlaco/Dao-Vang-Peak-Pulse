import time
import subprocess
from pathlib import Path

# timestamp 14 days ago to now
now = int(time.time())
start = now - (14 * 24 * 60 * 60)

print(f"Collecting from {start} to {now}")
# Not running this to avoid overwhelming Binance API if not needed.
