import io
import sys
import zipfile
from datetime import timedelta
from pathlib import Path

import duckdb
import httpx
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dao_vang.data.historical_adapter import DEFAULT_MASTER_DUCKDB


def backfill_symbol(conn, symbol, start_date, end_date):
    print(f"Backfilling {symbol} from {start_date.date()} to {end_date.date()}")
    
    # 1. Backfill Monthly Funding
    current_month = start_date.replace(day=1)
    while current_month <= end_date:
        ym = current_month.strftime("%Y-%m")
        url = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{ym}.zip"
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=15.0)
            if resp.status_code == 200:
                z = zipfile.ZipFile(io.BytesIO(resp.content))
                csv_name = z.namelist()[0]
                df = pd.read_csv(z.open(csv_name))
                if "calc_time" in df.columns:
                    df["funding_time"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True)
                    df["funding_rate"] = df["last_funding_rate"]
                    df["symbol"] = symbol
                    df["mark_price"] = 0.0
                    
                    df_insert = df[["symbol", "funding_time", "funding_rate", "mark_price"]]
                    
                    # Delete existing to prevent duplicates
                    conn.execute(f"DELETE FROM funding_history WHERE symbol = '{symbol}' AND funding_time >= '{df_insert['funding_time'].min()}' AND funding_time <= '{df_insert['funding_time'].max()}'")
                    conn.execute("INSERT INTO funding_history SELECT * FROM df_insert")
                    print(f"  [+] Funding {ym} inserted ({len(df_insert)} rows)")
            else:
                print(f"  [-] Funding {ym} missing (HTTP {resp.status_code})")
        except Exception as e:
            print(f"  [!] Error fetching funding {ym}: {e}")
            
        # Move to next month
        next_month = current_month.replace(day=28) + timedelta(days=4)
        current_month = next_month.replace(day=1)

    # 2. Backfill Daily Metrics
    current_day = start_date
    while current_day <= end_date:
        ymd = current_day.strftime("%Y-%m-%d")
        url = f"https://data.binance.vision/data/futures/um/daily/metrics/{symbol}/{symbol}-metrics-{ymd}.zip"
        try:
            resp = httpx.get(url, follow_redirects=True, timeout=15.0)
            if resp.status_code == 200:
                z = zipfile.ZipFile(io.BytesIO(resp.content))
                csv_name = z.namelist()[0]
                df = pd.read_csv(z.open(csv_name))
                if "create_time" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["create_time"], utc=True)
                    df["symbol"] = df["symbol"]
                    df["open_interest"] = df["sum_open_interest"]
                    df["open_interest_value"] = df["sum_open_interest_value"]
                    df["top_trader_account_ratio"] = df["count_toptrader_long_short_ratio"]
                    df["top_trader_position_ratio"] = df["sum_toptrader_long_short_ratio"]
                    df["global_account_ratio"] = df["count_long_short_ratio"]
                    df["taker_buy_sell_ratio"] = df["sum_taker_long_short_vol_ratio"]
                    
                    df_insert = df[[
                        "symbol", "timestamp", "open_interest", "open_interest_value",
                        "top_trader_account_ratio", "top_trader_position_ratio",
                        "global_account_ratio", "taker_buy_sell_ratio"
                    ]]
                    
                    conn.execute(f"DELETE FROM metrics_5m WHERE symbol = '{symbol}' AND timestamp >= '{df_insert['timestamp'].min()}' AND timestamp <= '{df_insert['timestamp'].max()}'")
                    conn.execute("INSERT INTO metrics_5m SELECT * FROM df_insert")
            else:
                pass # Silent for daily missing
        except Exception:
            pass # Silent
            
        current_day += timedelta(days=1)
    print(f"  [*] Finished metrics up to {end_date.date()}")

def main():
    conn = duckdb.connect(str(DEFAULT_MASTER_DUCKDB), read_only=False)
    
    # Get top 50 symbols from DB
    query = """
    WITH period_data AS (
        SELECT symbol,
               FIRST_VALUE(open) OVER (PARTITION BY symbol ORDER BY close_time ASC) as start_price,
               MAX(high) OVER (PARTITION BY symbol) as period_max_high,
               SUM(quote_volume) OVER (PARTITION BY symbol) as total_vol
        FROM klines_5m
        WHERE close_time >= '2025-06-01' AND close_time < '2025-12-01'
    )
    SELECT symbol
    FROM period_data
    GROUP BY symbol, total_vol
    HAVING total_vol > 100000000
    ORDER BY MAX(period_max_high / NULLIF(start_price, 0)) DESC
    LIMIT 50
    """
    symbols = [r[0] for r in conn.execute(query).fetchall()]
    
    print(f"Backfilling {len(symbols)} symbols from Binance Vision...")
    start_date = pd.Timestamp("2025-10-01") # Backfill enough for 30d rolling window before 2025-12-01
    end_date = pd.Timestamp("2026-08-15")
    
    for sym in symbols:
        backfill_symbol(conn, sym, start_date, end_date)
        
    conn.close()
    print("Backfill complete!")

if __name__ == "__main__":
    main()
