import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Any, Optional

from dao_vang.config.settings import AppSettings
from dao_vang.data.normalization.normalizers import (
    normalize_funding,
    normalize_global_ratio,
    normalize_kline,
    normalize_open_interest,
    normalize_taker_volume,
    normalize_top_ratio,
)
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.data.storage.parquet import write_normalized_to_parquet
from dao_vang.data.timeline import align_exact_5m, align_funding_asof

logger = logging.getLogger(__name__)

# Timestamp field/extraction per data type for incremental download
_TIMESTAMP_SPECS: Dict[str, Any] = {
    "klines": {"field": None, "index": 6},  # close_time at index 6 in kline list
    "funding": {"field": "fundingTime"},
    "open_interest": {"field": "timestamp"},
    "taker_ratio": {"field": "timestamp"},
    "global_ratio": {"field": "timestamp"},
    "top_ratio": {"field": "timestamp"},
}


def get_latest_data_timestamp(
    data_dir: Path, data_type: str, symbol: str
) -> Optional[datetime]:
    """
    Scan existing raw JSONL files for the given data_type and symbol,
    and return the latest data timestamp (UTC).

    Returns None if no matching data is found.
    """
    raw_dir = data_dir / "raw" / data_type
    if not raw_dir.exists():
        return None

    date_dirs = sorted(raw_dir.glob("date=*"))
    if not date_dirs:
        return None

    spec = _TIMESTAMP_SPECS.get(data_type)
    if spec is None:
        return None

    latest_ts_ms = 0

    # Only scan the last few date directories for efficiency
    for date_dir in reversed(date_dirs[-5:]):
        jsonl_files = sorted(date_dir.glob("*.jsonl"))
        if not jsonl_files:
            continue

        for f in jsonl_files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        envelope = json.loads(line)
                        # Check symbol from request params
                        req_params = json.loads(envelope.get("request_params_json", "{}"))
                        file_symbol = req_params.get("symbol", "")
                        if file_symbol != symbol:
                            continue

                        payload = json.loads(envelope["payload_json"])
                        if not payload or not isinstance(payload, list):
                            continue

                        last_item = payload[-1]
                        if spec["field"] is None:
                            # klines: timestamp at index
                            ts = int(last_item[spec["index"]])
                        else:
                            ts = int(last_item[spec["field"]])

                        if ts > latest_ts_ms:
                            latest_ts_ms = ts
            except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                continue

    if latest_ts_ms > 0:
        return datetime.fromtimestamp(latest_ts_ms / 1000.0, tz=timezone.utc)
    return None


def get_incremental_start(
    data_dir: Path, data_type: str, symbol: str, requested_start: datetime
) -> datetime:
    """
    Return the effective start time for incremental collection.
    If existing data covers up to a later timestamp, start from there (+1ms).
    Otherwise, start from the requested_start.
    """
    latest = get_latest_data_timestamp(data_dir, data_type, symbol)
    if latest is not None and latest >= requested_start:
        return latest + timedelta(milliseconds=1)
    return requested_start


def scan_downloaded_data(data_dir: Path) -> Dict[str, Dict[str, Any]]:
    """
    Scan all raw JSONL files and return a summary of downloaded data
    organized by symbol and data_type.

    Returns:
        {
            "BTCUSDT": {
                "klines": {"rows": 12345, "files": 5, "first_date": "2026-07-01", "last_date": "2026-07-31"},
                "funding": {...},
                ...
            },
            ...
        }
    """
    raw_dir = data_dir / "raw"
    if not raw_dir.exists():
        return {}

    result: Dict[str, Dict[str, Any]] = {}

    for data_type, spec in _TIMESTAMP_SPECS.items():
        dtype_dir = raw_dir / data_type
        if not dtype_dir.exists():
            continue

        for jsonl in sorted(dtype_dir.rglob("*.jsonl")):
            date_str = jsonl.parent.name.replace("date=", "")
            try:
                with open(jsonl, "r", encoding="utf-8") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        envelope = json.loads(line)
                        req = json.loads(envelope.get("request_params_json", "{}"))
                        sym = req.get("symbol", "")
                        if not sym:
                            continue

                        if sym not in result:
                            result[sym] = {}
                        if data_type not in result[sym]:
                            result[sym][data_type] = {
                                "rows": 0,
                                "files": set(),
                                "first_date": date_str,
                                "last_date": date_str,
                            }

                        entry = result[sym][data_type]
                        entry["files"].add(jsonl.name)
                        if date_str < entry["first_date"]:
                            entry["first_date"] = date_str
                        if date_str > entry["last_date"]:
                            entry["last_date"] = date_str

                        payload = json.loads(envelope["payload_json"])
                        if isinstance(payload, list):
                            entry["rows"] += len(payload)
            except (json.JSONDecodeError, KeyError, IndexError, ValueError):
                continue

    # Convert file sets to counts
    for sym in result:
        for dt in result[sym]:
            result[sym][dt]["files"] = len(result[sym][dt]["files"])

    return result


# Map collector types to their normalization functions
NORMALIZER_MAP: Dict[str, Callable[[Dict[str, Any], str], list[Any]]] = {
    "klines": normalize_kline,
    "funding": normalize_funding,
    "open_interest": normalize_open_interest,
    "taker_ratio": normalize_taker_volume,
    "global_ratio": normalize_global_ratio,
    "top_ratio": normalize_top_ratio,
}


def process_raw_to_parquet(settings: AppSettings, dataset_version: str = "1.0.0"):
    """
    Reads raw JSONL files from all collectors, normalizes them, and writes to Parquet.
    """
    raw_dir = settings.paths.data_dir / "raw"
    normalized_dir = settings.paths.data_dir / "normalized"
    normalized_dir.mkdir(parents=True, exist_ok=True)

    for collector_type, normalizer_func in NORMALIZER_MAP.items():
        collector_raw_dir = raw_dir / collector_type
        if not collector_raw_dir.exists():
            continue

        for jsonl_file in collector_raw_dir.rglob("*.jsonl"):
            # We construct a matching parquet file name
            # Incorporate parent directory name (e.g. date=2026-08-01) to avoid conflicts if same run_id across dates
            date_dir = jsonl_file.parent.name
            target_dir = normalized_dir / collector_type / date_dir
            target_dir.mkdir(parents=True, exist_ok=True)
            
            parquet_file = target_dir / f"{jsonl_file.stem}.parquet"
            if parquet_file.exists():
                # Skip already processed
                continue

            normalized_items = []
            with open(jsonl_file, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    envelope = json.loads(line)
                    items = normalizer_func(envelope, dataset_version)
                    normalized_items.extend(items)

            if normalized_items:
                write_normalized_to_parquet(parquet_file, normalized_items)


def build_raw_timeline(db: DuckDBQueryLayer, settings: AppSettings):
    """
    Mounts parquet files into DuckDB views and stitches them into the raw_timeline.
    """
    normalized_dir = settings.paths.data_dir / "normalized"

    # Map duckdb view names to (subdir, time_col) for deduplication
    views = {
        "kline": ("klines", "close_time"),
        "open_interest": ("open_interest", "period_end"),
        "taker_volume": ("taker_ratio", "period_end"),
        "global_ratio": ("global_ratio", "period_end"),
        "top_ratio": ("top_ratio", "period_end"),
        "funding": ("funding", "event_time"),
    }

    # Create base views over parquet files
    for view_name, (subdir, time_col) in views.items():
        path_pattern = str(normalized_dir / subdir / "**/*.parquet").replace("\\", "/")
        # We check if there are any parquet files first.
        if list((normalized_dir / subdir).rglob("*.parquet")):
            for kind in ("VIEW", "TABLE"):
                try:
                    db.conn.execute(f"DROP {kind} {view_name}")
                except Exception:
                    pass

            db.conn.execute(f"""
                CREATE OR REPLACE VIEW {view_name} AS 
                SELECT * FROM read_parquet('{path_pattern}', union_by_name=true)
                QUALIFY row_number() OVER (PARTITION BY symbol, {time_col} ORDER BY available_time DESC) = 1
            """)
        else:
            # Create an empty view with the right schema? 
            # For MVP, we assume data exists because we just collected it.
            logger.warning(f"No parquet files found for {view_name} at {path_pattern}")

    # Build the intermediate exact 5m alignment
    align_exact_5m(db, output_view="aligned_5m")

    # Build the final raw_timeline by adding funding asof
    align_funding_asof(db, output_view="raw_timeline", aligned_view="aligned_5m")
