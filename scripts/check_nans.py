import duckdb
from pathlib import Path
from dao_vang.experiments.ablation import FEATURE_GROUPS

active_features = []
for group, cols in FEATURE_GROUPS.items():
    if group != "funding":
        active_features.extend(cols)

conn = duckdb.connect("artifacts/backtest_results.duckdb", read_only=True)
print("Checking nulls...")
for col in active_features:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM bt_features WHERE {col} IS NOT NULL").fetchone()[0]
        if count == 0:
            print(f"{col} is ALL NULL")
    except Exception as e:
        print(f"Error checking {col}: {e}")
conn.close()
