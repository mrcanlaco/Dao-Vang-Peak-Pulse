import json
import logging
from pathlib import Path
from typing import Dict, Callable, Any

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
            try:
                db.conn.execute(f"DROP VIEW IF EXISTS {view_name}")
                db.conn.execute(f"DROP TABLE IF EXISTS {view_name}")
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
