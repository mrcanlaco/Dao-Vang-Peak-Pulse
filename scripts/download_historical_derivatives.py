"""Download historical Binance derivatives data into the data lake.

Fetches funding rate, open interest, taker buy/sell ratio, and long/short ratios
for all coins in the klines data lake, in monthly chunks to avoid API rate limits.

Usage:
    uv run python scripts/download_historical_derivatives.py \
        --data-lake D:\Quant-trading\data_lake \
        --start 2024-01-01 \
        --end 2026-08-28 \
        --max-coins 50 \
        --sleep-between-coins 0.5
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Add project to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pyarrow as pa
import pyarrow.parquet as pq

from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.logging import get_logger

logger = get_logger(__name__)

# ──────────────────────────────────────────────────────────────────────
# Binance API endpoints for derivatives data
# ──────────────────────────────────────────────────────────────────────

DERIVATIVES_ENDPOINTS = {
    "funding": {
        "path": "/fapi/v1/fundingRate",
        "limit": 1000,
        "time_key": "fundingTime",
        "period_param": False,
    },
    "open_interest": {
        "path": "/futures/data/openInterestHist",
        "limit": 500,
        "time_key": "timestamp",
        "period_param": True,
    },
    "taker_volume": {
        "path": "/futures/data/takerlongshortRatio",
        "limit": 500,
        "time_key": "timestamp",
        "period_param": True,
    },
    "global_ratio": {
        "path": "/futures/data/globalLongShortAccountRatio",
        "limit": 500,
        "time_key": "timestamp",
        "period_param": True,
    },
    "top_ratio": {
        "path": "/futures/data/topLongShortAccountRatio",
        "limit": 500,
        "time_key": "timestamp",
        "period_param": True,
    },
    "top_position_ratio": {
        "path": "/futures/data/topLongShortPositionRatio",
        "limit": 500,
        "time_key": "timestamp",
        "period_param": True,
    },
}

# Arrow schemas per data type
FUNDING_SCHEMA = pa.schema([
    ("symbol", pa.string()),
    ("funding_time", pa.timestamp("ms", tz="UTC")),
    ("funding_rate", pa.float64()),
    ("mark_price", pa.float64()),
])

OI_SCHEMA = pa.schema([
    ("symbol", pa.string()),
    ("timestamp", pa.timestamp("ms", tz="UTC")),
    ("open_interest_contracts", pa.float64()),
    ("open_interest_value", pa.float64()),
])

TAKER_SCHEMA = pa.schema([
    ("symbol", pa.string()),
    ("timestamp", pa.timestamp("ms", tz="UTC")),
    ("buy_volume", pa.float64()),
    ("sell_volume", pa.float64()),
    ("buy_sell_ratio", pa.float64()),
])

RATIO_SCHEMA = pa.schema([
    ("symbol", pa.string()),
    ("timestamp", pa.timestamp("ms", tz="UTC")),
    ("long_account", pa.float64()),
    ("short_account", pa.float64()),
    ("long_short_ratio", pa.float64()),
])


def _parse_funding(symbol: str, raw: list[dict]) -> list[dict]:
    rows = []
    for item in raw:
        rows.append({
            "symbol": symbol,
            "funding_time": item["fundingTime"],
            "funding_rate": float(item["fundingRate"]),
            "mark_price": float(item.get("markPrice", 0)) or None,
        })
    return rows


def _parse_oi(symbol: str, raw: list[dict]) -> list[dict]:
    rows = []
    for item in raw:
        rows.append({
            "symbol": symbol,
            "timestamp": int(item["timestamp"]),
            "open_interest_contracts": float(item.get("sumOpenInterest", 0)),
            "open_interest_value": float(item.get("sumOpenInterestValue", 0)),
        })
    return rows


def _parse_taker(symbol: str, raw: list[dict]) -> list[dict]:
    rows = []
    for item in raw:
        rows.append({
            "symbol": symbol,
            "timestamp": int(item["timestamp"]),
            "buy_volume": float(item.get("buyVol", 0)),
            "sell_volume": float(item.get("sellVol", 0)),
            "buy_sell_ratio": float(item.get("buySellRatio", 0)),
        })
    return rows


def _parse_ratio(symbol: str, raw: list[dict]) -> list[dict]:
    rows = []
    for item in raw:
        rows.append({
            "symbol": symbol,
            "timestamp": int(item["timestamp"]),
            "long_account": float(item.get("longAccount", 0) or item.get("longPosition", 0)),
            "short_account": float(item.get("shortAccount", 0) or item.get("shortPosition", 0)),
            "long_short_ratio": float(item.get("longShortRatio", 0)),
        })
    return rows


PARSERS = {
    "funding": (_parse_funding, FUNDING_SCHEMA),
    "open_interest": (_parse_oi, OI_SCHEMA),
    "taker_volume": (_parse_taker, TAKER_SCHEMA),
    "global_ratio": (_parse_ratio, RATIO_SCHEMA),
    "top_ratio": (_parse_ratio, RATIO_SCHEMA),
    "top_position_ratio": (_parse_ratio, RATIO_SCHEMA),
}


def fetch_paginated(
    client: BinanceClient,
    endpoint: dict,
    symbol: str,
    start_ms: int,
    end_ms: int,
    sleep_between_pages: float = 0.2,
) -> list[dict]:
    """Fetch all pages from a Binance endpoint between start_ms and end_ms."""
    all_data: list[dict] = []
    current_start = start_ms
    path = endpoint["path"]
    limit = endpoint["limit"]
    time_key = endpoint["time_key"]

    while current_start < end_ms:
        params: dict[str, Any] = {
            "symbol": symbol,
            "startTime": current_start,
            "endTime": end_ms,
            "limit": limit,
        }
        if endpoint["period_param"]:
            params["period"] = "5m"

        try:
            data = client.get(path, params)
        except Exception as e:
            logger.warning("api_error", symbol=symbol, path=path, error=str(e))
            break

        if not data or not isinstance(data, list):
            break

        all_data.extend(data)

        last_ts = int(data[-1][time_key])
        if last_ts <= current_start:
            break  # No progress
        current_start = last_ts + 1

        if len(data) < limit:
            break  # Last page

        time.sleep(sleep_between_pages)

    return all_data


def download_derivatives_for_symbol(
    client: BinanceClient,
    symbol: str,
    data_lake_dir: Path,
    start_date: datetime,
    end_date: datetime,
    data_types: list[str] | None = None,
) -> dict[str, int]:
    """Download all derivatives data for one symbol, save as Parquet."""
    if data_types is None:
        data_types = list(DERIVATIVES_ENDPOINTS.keys())

    start_ms = int(start_date.timestamp() * 1000)
    end_ms = int(end_date.timestamp() * 1000)
    results: dict[str, int] = {}

    for data_type in data_types:
        output_dir = data_lake_dir / data_type / "5m"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{symbol}.parquet"

        # Skip if already downloaded
        if output_path.exists():
            existing = pq.read_metadata(str(output_path))
            if existing.num_rows > 100:
                results[data_type] = -1  # Already exists
                continue

        endpoint = DERIVATIVES_ENDPOINTS[data_type]
        parser, schema = PARSERS[data_type]

        # Fetch in chunks — /futures/data/ endpoints have ~30d max lookback
        # Use 7-day chunks for safety
        chunk_rows: list[dict] = []
        chunk_start = start_ms
        chunk_size_ms = 7 * 24 * 60 * 60 * 1000  # 7 days

        while chunk_start < end_ms:
            chunk_end = min(chunk_start + chunk_size_ms, end_ms)
            raw = fetch_paginated(client, endpoint, symbol, chunk_start, chunk_end)
            if raw:
                parsed = parser(symbol, raw)
                chunk_rows.extend(parsed)
            chunk_start = chunk_end + 1
            time.sleep(0.15)

        if chunk_rows:
            table = pa.Table.from_pylist(chunk_rows, schema=schema)
            # Deduplicate
            df = table.to_pandas()
            time_col = "funding_time" if data_type == "funding" else "timestamp"
            df = df.drop_duplicates(subset=[time_col], keep="last")
            df = df.sort_values(time_col).reset_index(drop=True)
            table = pa.Table.from_pandas(df, schema=schema, preserve_index=False)
            pq.write_table(table, str(output_path), compression="zstd")
            results[data_type] = len(df)
        else:
            results[data_type] = 0

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Download historical Binance derivatives data")
    parser.add_argument("--data-lake", type=str, default=r"D:\Quant-trading\data_lake",
                       help="Path to data lake directory")
    parser.add_argument("--start", type=str, default="2024-01-01",
                       help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default="2026-08-28",
                       help="End date (YYYY-MM-DD)")
    parser.add_argument("--max-coins", type=int, default=0,
                       help="Max coins to download (0 = all)")
    parser.add_argument("--sleep-between-coins", type=float, default=1.0,
                       help="Sleep seconds between coins")
    parser.add_argument("--data-types", type=str, nargs="+",
                       default=None,
                       help="Specific data types to download")
    args = parser.parse_args()

    data_lake = Path(args.data_lake)
    start_date = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end_date = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Get coin list from existing klines
    klines_dir = data_lake / "klines" / "5m"
    coins = sorted([
        f.stem for f in klines_dir.glob("*.parquet")
        if not f.stem.startswith(".")
        and "USDT" in f.stem
        # Skip stablecoins and non-crypto
        and f.stem not in {"USDCUSDT", "BUSDUSDT", "TUSDUSDT", "FDUSDUSDT"}
    ])

    if args.max_coins > 0:
        coins = coins[:args.max_coins]

    print(f"Downloading derivatives for {len(coins)} coins")
    print(f"Date range: {args.start} to {args.end}")
    print(f"Data lake: {data_lake}")
    print(f"Data types: {args.data_types or 'all'}")
    print()

    client = BinanceClient()
    total_stats: dict[str, int] = {}
    failed_coins: list[str] = []

    for i, symbol in enumerate(coins, 1):
        print(f"[{i}/{len(coins)}] {symbol}...", end=" ", flush=True)
        try:
            results = download_derivatives_for_symbol(
                client, symbol, data_lake, start_date, end_date,
                data_types=args.data_types,
            )
            parts = []
            for dt, count in results.items():
                if count == -1:
                    parts.append(f"{dt}:skip")
                elif count == 0:
                    parts.append(f"{dt}:empty")
                else:
                    parts.append(f"{dt}:{count:,}")
                    total_stats[dt] = total_stats.get(dt, 0) + count
            print(" | ".join(parts))
        except Exception as e:
            print(f"FAILED: {e}")
            failed_coins.append(symbol)

        if i < len(coins):
            time.sleep(args.sleep_between_coins)

    print(f"\n{'='*60}")
    print("DOWNLOAD SUMMARY")
    print(f"{'='*60}")
    for dt, total in sorted(total_stats.items()):
        print(f"  {dt}: {total:,} rows")
    if failed_coins:
        print(f"\n  Failed coins ({len(failed_coins)}): {', '.join(failed_coins[:10])}")
    print(f"\nData saved to: {data_lake}")


if __name__ == "__main__":
    main()
