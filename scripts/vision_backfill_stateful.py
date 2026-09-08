import asyncio
import httpx
import hashlib
import zipfile
import io
import json
import sys
import calendar
import duckdb
import pandas as pd
from pathlib import Path
from datetime import timezone, datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.dao_vang.updater.upsert import atomic_upsert

UNIVERSE_FILE = Path("data/true_lowcap_universe.json")
TMP_DIR = Path("artifacts/vision_tmp")

def init_state_db(state_db: Path):
    state_db.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(state_db))
    conn.execute("CREATE TABLE IF NOT EXISTS download_state (url VARCHAR PRIMARY KEY, status VARCHAR)")
    conn.close()

def get_completed_urls(state_db: Path):
    if not state_db.exists(): return set()
    conn = duckdb.connect(str(state_db), read_only=True)
    rows = conn.execute("SELECT url FROM download_state WHERE status = 'ok'").fetchall()
    conn.close()
    return set(r[0] for r in rows)

def mark_url(state_db: Path, url: str, status: str):
    conn = duckdb.connect(str(state_db))
    conn.execute("INSERT OR REPLACE INTO download_state VALUES (?, ?)", [url, status])
    conn.close()

def get_listing_times():
    resp = httpx.get("https://fapi.binance.com/fapi/v1/exchangeInfo", timeout=20.0)
    resp.raise_for_status()
    data = resp.json()
    return {s['symbol']: pd.to_datetime(s['onboardDate'], unit='ms', utc=True) 
            for s in data['symbols'] if 'onboardDate' in s}

async def fetch_vision_file(client, url, out_csv: Path):
    try:
        chk_resp = await client.get(url + ".CHECKSUM", timeout=15.0)
        if chk_resp.status_code == 404:
            return "404"
        if chk_resp.status_code != 200:
            return "error"
            
        expected_hash = chk_resp.text.split()[0].lower()
        if out_csv.exists():
            return "ok"
            
        resp = await client.get(url, timeout=30.0)
        if resp.status_code != 200:
            return "error"
            
        actual_hash = hashlib.sha256(resp.content).hexdigest().lower()
        if expected_hash != actual_hash:
            return "error"
            
        with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
            csv_name = z.namelist()[0]
            csv_data = z.read(csv_name)
            
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        out_csv.write_bytes(csv_data)
        return "ok"
    except Exception:
        return "error"

async def fetch_funding_rest(client, sym, start_ms, end_ms, out_csv: Path):
    try:
        url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&startTime={start_ms}&endTime={end_ms}&limit=1000"
        resp = await client.get(url, timeout=20.0)
        if resp.status_code == 200:
            data = resp.json()
            if data:
                df = pd.DataFrame(data)
                out_csv.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(out_csv, index=False)
            return True
        return False
    except Exception:
        return False

def smart_upsert_funding(target_parquet: Path, csv_paths: list[Path], sym: str):
    if not csv_paths: return
    target_parquet.parent.mkdir(parents=True, exist_ok=True)
    tmp_out = target_parquet.with_suffix('.parquet.tmp')
    csv_list_str = ", ".join(f"'{p.as_posix()}'" for p in csv_paths)
    
    new_data_query = f"""
        SELECT 
            '{sym}' as symbol,
            to_timestamp(calc_time / 1000) as funding_time,
            last_funding_rate as funding_rate,
            NULL::DOUBLE as mark_price
        FROM read_csv_auto([{csv_list_str}], header=True)
    """
    
    conn = duckdb.connect()
    try:
        if target_parquet.exists():
            conn.execute(f"""
                COPY (
                    WITH new_data AS ({new_data_query}),
                         old_data AS (SELECT * FROM '{target_parquet.as_posix()}')
                    SELECT 
                        COALESCE(n.symbol, o.symbol) as symbol,
                        COALESCE(n.funding_time, o.funding_time) as funding_time,
                        COALESCE(n.funding_rate, o.funding_rate) as funding_rate,
                        COALESCE(o.mark_price, n.mark_price) as mark_price
                    FROM new_data n
                    FULL OUTER JOIN old_data o 
                    ON n.symbol = o.symbol AND n.funding_time = o.funding_time
                ) TO '{tmp_out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);
            """)
        else:
            conn.execute(f"COPY ({new_data_query}) TO '{tmp_out.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD);")
            
        import os
        os.replace(tmp_out, target_parquet)
    finally:
        if tmp_out.exists(): tmp_out.unlink()
        conn.close()

async def backfill_symbol(client, sym: str, onboard_time: pd.Timestamp, root_dir: Path, state_db: Path, completed: set) -> bool:
    success = True
    base_start = pd.Timestamp("2024-09-01", tz="UTC")
    start_date = max(base_start, onboard_time)
    
    curr_month = start_date.replace(day=1)
    end_date = pd.Timestamp.now(tz="UTC")
    current_ym = end_date.strftime("%Y-%m")
    
    dataset_paths = {
        "klines/5m": "klines/5m",
        "metrics/5m": "metrics/5m",
        "funding": "funding"
    }
    
    QUERIES = {
        "klines/5m": "SELECT '{symbol}' as symbol, to_timestamp(open_time / 1000) as open_time, to_timestamp(close_time / 1000) as close_time, open, high, low, close, volume, quote_volume, taker_buy_volume FROM read_csv_auto([{csv_list}], header=True)",
        "metrics/5m": "SELECT symbol, CAST(create_time AS TIMESTAMP) AT TIME ZONE 'UTC' as timestamp, sum_open_interest as open_interest, sum_open_interest_value as open_interest_value, count_toptrader_long_short_ratio as top_trader_account_ratio, sum_toptrader_long_short_ratio as top_trader_position_ratio, count_long_short_ratio as global_account_ratio, sum_taker_long_short_vol_ratio as taker_buy_sell_ratio FROM read_csv_auto([{csv_list}], header=True)",
        "funding_rest": "SELECT '{symbol}' as symbol, to_timestamp(fundingTime / 1000) as funding_time, fundingRate as funding_rate, markPrice as mark_price FROM read_csv_auto([{csv_list}], header=True)"
    }
    
    for ds in ["klines/5m", "metrics/5m", "funding"]:
        csv_paths = []
        has_error = False
        ds_target = dataset_paths[ds]
        
        month_iter = start_date.replace(day=1)
        while month_iter <= end_date:
            ym = month_iter.strftime("%Y-%m")
            if ym == current_ym:
                if ds == "funding":
                    url = f"rest_funding_{sym}_{ym}"
                    if url not in completed:
                        start_ms = int(pd.Timestamp(f"{ym}-01", tz="UTC").value / 10**6)
                        end_ms = int(end_date.value / 10**6)
                        out_csv = TMP_DIR / sym / "funding_rest" / f"{ym}.csv"
                        if await fetch_funding_rest(client, sym, start_ms, end_ms, out_csv):
                            csv_paths.append((out_csv, "funding_rest", url))
                        else:
                            print(f"  [{sym}] Lỗi REST funding {ym}")
                            has_error = True
                else:
                    y, m = map(int, ym.split("-"))
                    now_day = end_date.day
                    for d in range(1, now_day):
                        ymd = f"{y}-{m:02d}-{d:02d}"
                        url = f"https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{sym}-5m-{ymd}.zip" if ds == "klines/5m" else f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{ymd}.zip"
                        if url in completed: continue
                        
                        out_csv = TMP_DIR / sym / ds / f"{ymd}.csv"
                        res = await fetch_vision_file(client, url, out_csv)
                        if res == "ok":
                            csv_paths.append((out_csv, ds, url))
                        elif res == "404":
                            pass 
                        else:
                            print(f"  [{sym}] Daily Lỗi: {url}")
                            has_error = True
            else:
                if ds in ["klines/5m", "funding"]:
                    url = f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{sym}-5m-{ym}.zip" if ds == "klines/5m" else f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip"
                    if url not in completed:
                        out_csv = TMP_DIR / sym / ds / f"{ym}.csv"
                        res = await fetch_vision_file(client, url, out_csv)
                        if res == "ok":
                            csv_paths.append((out_csv, ds, url))
                        elif res == "404":
                            mark_url(state_db, url, "404")
                        else:
                            print(f"  [{sym}] Monthly Lỗi: {url}")
                            has_error = True
                else:
                    y, m = map(int, ym.split("-"))
                    _, last_day = calendar.monthrange(y, m)
                    for d in range(1, last_day + 1):
                        ymd = f"{y}-{m:02d}-{d:02d}"
                        url = f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{ymd}.zip"
                        if url in completed: continue
                        out_csv = TMP_DIR / sym / ds / f"{ymd}.csv"
                        res = await fetch_vision_file(client, url, out_csv)
                        if res == "ok":
                            csv_paths.append((out_csv, ds, url))
                        elif res == "404":
                            mark_url(state_db, url, "404")
                        else:
                            print(f"  [{sym}] Metrics Lỗi: {url}")
                            has_error = True
            
            month_iter += pd.DateOffset(months=1)

        if has_error:
            print(f"[{sym} - {ds}] Aborted dataset due to download errors.")
            success = False
            continue
            
        if csv_paths:
            grouped = {}
            for p, q_key, u in csv_paths:
                grouped.setdefault(q_key, []).append((p, u))
                
            if ds == "metrics/5m":
                target = root_dir / ds_target / f"{sym}_metrics.parquet"
            elif ds == "funding":
                target = root_dir / ds_target / f"{sym}_funding.parquet"
            else:
                target = root_dir / ds_target / f"{sym}.parquet"
                
            time_col = "open_time" if "klines" in ds else ("funding_time" if "funding" in ds else "timestamp")
            
            for q_key, paths_urls in grouped.items():
                paths = [pu[0] for pu in paths_urls]
                urls = [pu[1] for pu in paths_urls]
                q = QUERIES.get(q_key, "").replace("{symbol}", sym)
                try:
                    if q_key == "funding":
                        smart_upsert_funding(target, paths, sym)
                    else:
                        atomic_upsert(target, paths, time_col, q)
                        
                    for u in urls:
                        mark_url(state_db, u, "ok")
                except Exception as e:
                    print(f"[{sym} - {ds}] Upsert error: {e}")
                    success = False

    if success:
        import shutil
        shutil.rmtree(TMP_DIR / sym, ignore_errors=True)
        
    return success

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", type=str, help="Symbol to smoke test")
    parser.add_argument("--apply", action="store_true", help="Apply to D: drive")
    args = parser.parse_args()
    
    root_dir = Path("D:/Quant-trading/data_lake") if args.apply else Path("artifacts/smoke")
    state_db = root_dir / "backfill_state.duckdb"
    print(f"Targeting root: {root_dir}")
    print(f"State DB: {state_db}")
    
    init_state_db(state_db)
    completed = get_completed_urls(state_db)
    
    with open(UNIVERSE_FILE, "r") as f:
        u_data = json.load(f)
        universe = list(u_data.keys()) if isinstance(u_data, dict) else list(u_data)
        
    listings = get_listing_times()
    
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=20)) as client:
        if args.test:
            onboard = listings.get(args.test, pd.Timestamp("2024-09-01", tz="UTC"))
            print(f"Testing {args.test} (Listed: {onboard})...")
            res = await backfill_symbol(client, args.test, onboard, root_dir, state_db, completed)
            sys.exit(0 if res else 1)
        else:
            success = True
            for sym in universe:
                onboard = listings.get(sym, pd.Timestamp("2024-09-01", tz="UTC"))
                if not await backfill_symbol(client, sym, onboard, root_dir, state_db, completed):
                    success = False
            if not success:
                print("SOME ERRORS OCCURRED")
                sys.exit(1)
            print("ALL DONE.")

if __name__ == "__main__":
    asyncio.run(main())
