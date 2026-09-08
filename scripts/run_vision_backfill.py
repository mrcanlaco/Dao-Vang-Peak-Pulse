import asyncio
import httpx
import hashlib
import zipfile
import io
import json
import sys
import calendar
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.dao_vang.updater.upsert import atomic_upsert

MANIFEST_FILE = Path("data/backfill_manifest.json")
TMP_DIR = Path("artifacts/vision_tmp")

QUERIES = {
    "klines/5m": """
        SELECT 
            '{symbol}' as symbol,
            to_timestamp(open_time / 1000) as open_time,
            to_timestamp(close_time / 1000) as close_time,
            open, high, low, close, volume, quote_volume, taker_buy_volume
        FROM read_csv_auto([{csv_list}], header=True)
    """,
    "metrics/5m": """
        SELECT 
            symbol,
            CAST(create_time AS TIMESTAMP) AT TIME ZONE 'UTC' as timestamp,
            sum_open_interest as open_interest,
            sum_open_interest_value as open_interest_value,
            count_toptrader_long_short_ratio as top_trader_account_ratio,
            sum_toptrader_long_short_ratio as top_trader_position_ratio,
            count_long_short_ratio as global_account_ratio,
            sum_taker_long_short_vol_ratio as taker_buy_sell_ratio
        FROM read_csv_auto([{csv_list}], header=True)
    """,
    "funding": """
        SELECT 
            '{symbol}' as symbol,
            to_timestamp(calc_time / 1000) as funding_time,
            last_funding_rate as funding_rate,
            NULL::DOUBLE as mark_price
        FROM read_csv_auto([{csv_list}], header=True)
    """,
    "funding_rest": """
        SELECT 
            '{symbol}' as symbol,
            to_timestamp(fundingTime / 1000) as funding_time,
            fundingRate as funding_rate,
            markPrice as mark_price
        FROM read_csv_auto([{csv_list}], header=True)
    """
}

async def fetch_vision_file(client, url, out_csv: Path):
    try:
        chk_resp = await client.get(url + ".CHECKSUM", timeout=15.0)
        if chk_resp.status_code == 404:
            return "404"
        if chk_resp.status_code != 200:
            return "error"
            
        expected_hash = chk_resp.text.split()[0].lower()
        
        # Nếu đã có tmp, verify hash
        if out_csv.exists():
            with open(out_csv, "rb") as f:
                # File out_csv là CSV đã unzip. Checksum của Binance là cho ZIP.
                # Do đó nếu có file csv rồi, coi như tải qua. Nếu muốn chặt, phải giữ ZIP.
                pass
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
    if out_csv.exists():
        return True
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

async def backfill_symbol(client, sym: str, months: list[str], root_dir: Path) -> bool:
    success = True
    current_ym = datetime.now(timezone.utc).strftime("%Y-%m")
    
    dataset_paths = {
        "klines/5m": "klines/5m",
        "metrics/5m": "metrics/5m",
        "funding": "funding"
    }
    
    for ds in ["klines/5m", "metrics/5m", "funding"]:
        csv_paths = []
        has_error = False
        ds_target = dataset_paths[ds]
        
        for ym in months:
            if ym == current_ym:
                if ds == "funding":
                    # REST API cho current month
                    start_ms = int(pd.Timestamp(f"{ym}-01", tz="UTC").timestamp() * 1000)
                    end_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
                    out_csv = TMP_DIR / sym / "funding_rest" / f"{ym}.csv"
                    if await fetch_funding_rest(client, sym, start_ms, end_ms, out_csv):
                        csv_paths.append((out_csv, "funding_rest"))
                    else:
                        print(f"  [{sym}] Lỗi REST funding {ym}")
                        has_error = True
                else:
                    # Daily zips
                    y, m = map(int, ym.split("-"))
                    now_day = datetime.now(timezone.utc).day
                    for d in range(1, now_day + 1):
                        ymd = f"{y}-{m:02d}-{d:02d}"
                        if ds == "klines/5m":
                            url = f"https://data.binance.vision/data/futures/um/daily/klines/{sym}/5m/{sym}-5m-{ymd}.zip"
                        else:
                            url = f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{ymd}.zip"
                        
                        out_csv = TMP_DIR / sym / ds / f"{ymd}.csv"
                        res = await fetch_vision_file(client, url, out_csv)
                        if res == "ok":
                            csv_paths.append((out_csv, ds))
                        elif res == "404":
                            # Unpublished / not available yet, ignore cleanly
                            pass
                        else:
                            print(f"  [{sym}] Daily Lỗi: {url}")
                            has_error = True
            else:
                if ds in ["klines/5m", "funding"]:
                    if ds == "klines/5m":
                        url = f"https://data.binance.vision/data/futures/um/monthly/klines/{sym}/5m/{sym}-5m-{ym}.zip"
                    else:
                        url = f"https://data.binance.vision/data/futures/um/monthly/fundingRate/{sym}/{sym}-fundingRate-{ym}.zip"
                        
                    out_csv = TMP_DIR / sym / ds / f"{ym}.csv"
                    res = await fetch_vision_file(client, url, out_csv)
                    if res == "ok":
                        csv_paths.append((out_csv, ds))
                    elif res == "404":
                        pass # Coin chưa list / gap
                    else:
                        print(f"  [{sym}] Monthly Lỗi: {url}")
                        has_error = True
                else:
                    # Metrics daily history
                    y, m = map(int, ym.split("-"))
                    _, last_day = calendar.monthrange(y, m)
                    for d in range(1, last_day + 1):
                        ymd = f"{y}-{m:02d}-{d:02d}"
                        url = f"https://data.binance.vision/data/futures/um/daily/metrics/{sym}/{sym}-metrics-{ymd}.zip"
                        out_csv = TMP_DIR / sym / ds / f"{ymd}.csv"
                        res = await fetch_vision_file(client, url, out_csv)
                        if res == "ok":
                            csv_paths.append((out_csv, ds))
                        elif res == "404":
                            pass
                        else:
                            print(f"  [{sym}] Metrics Lỗi: {url}")
                            has_error = True

        if has_error:
            print(f"[{sym} - {ds}] Aborted dataset due to download errors.")
            success = False
            continue
            
        if csv_paths:
            grouped = {}
            for p, q_key in csv_paths:
                grouped.setdefault(q_key, []).append(p)
                
            if "metrics" in ds_target:
                target = root_dir / ds_target / f"{sym}_metrics.parquet"
            elif "funding" in ds_target:
                target = root_dir / ds_target / f"{sym}_funding.parquet"
            else:
                target = root_dir / ds_target / f"{sym}.parquet"
            time_col = "open_time" if "klines" in ds else ("funding_time" if "funding" in ds else "timestamp")
            
            for q_key, paths in grouped.items():
                q = QUERIES[q_key].replace("{symbol}", sym)
                try:
                    atomic_upsert(target, paths, time_col, q)
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
    print(f"Targeting root: {root_dir}")
    
    with open(MANIFEST_FILE, "r") as f:
        manifest = json.load(f)
        
    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=20)) as client:
        if args.test:
            data = manifest.get(args.test)
            if data:
                print(f"Testing {args.test} for months {data['missing_months']}...")
                res = await backfill_symbol(client, args.test, data["missing_months"], root_dir)
                sys.exit(0 if res else 1)
            else:
                print("Symbol not in manifest")
                sys.exit(1)
        else:
            success = True
            for sym, data in manifest.items():
                m = data.get("missing_months", [])
                if m:
                    if not await backfill_symbol(client, sym, m, root_dir):
                        success = False
            if not success:
                print("SOME ERRORS OCCURRED")
                sys.exit(1)
            print("ALL DONE.")

if __name__ == "__main__":
    asyncio.run(main())
