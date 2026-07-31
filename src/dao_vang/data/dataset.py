import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.data.timeline import align_exact_5m, align_funding_asof


def hash_file(path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()


class DatasetBuilder:
    """Builds the final aligned Parquet dataset and computes its fingerprint."""

    def __init__(self, db: DuckDBQueryLayer):
        self.db = db

    def build_dataset(
        self,
        output_path: Path,
        kline_path: Path,
        oi_path: Path,
        taker_path: Path,
        global_ratio_path: Path,
        top_ratio_path: Path,
        funding_path: Path,
        dataset_version: str = "1.0",
    ) -> Dict[str, Any]:
        """
        Builds the aligned dataset and exports it to parquet.
        Returns the dataset fingerprint manifest.
        """

        self.db.register_parquet_view("kline", kline_path)
        self.db.register_parquet_view("open_interest", oi_path)
        self.db.register_parquet_view("taker_volume", taker_path)
        self.db.register_parquet_view("global_ratio", global_ratio_path)
        self.db.register_parquet_view("top_ratio", top_ratio_path)
        self.db.register_parquet_view("funding", funding_path)

        align_exact_5m(self.db, "aligned_5m")
        align_funding_asof(
            self.db, "final_dataset", aligned_view="aligned_5m", funding_view="funding"
        )

        # Export to parquet
        self.db.conn.execute(
            f"COPY (SELECT * FROM final_dataset) TO '{output_path}' (FORMAT PARQUET)"
        )

        # Calculate fingerprint
        stats = self.db.query(
            "SELECT COUNT(*) as count, CAST(MIN(feature_time) AS VARCHAR) as min_t, CAST(MAX(feature_time) AS VARCHAR) as max_t FROM final_dataset"
        ).fetchone()

        if not stats:
            stats = (0, None, None)

        fingerprint_data = {
            "dataset_version": dataset_version,
            "inputs": {
                "kline": hash_file(kline_path),
                "open_interest": hash_file(oi_path),
                "taker_volume": hash_file(taker_path),
                "global_ratio": hash_file(global_ratio_path),
                "top_ratio": hash_file(top_ratio_path),
                "funding": hash_file(funding_path),
            },
            "rows": int(stats[0]),
            "min_time": str(stats[1]) if stats[1] else None,
            "max_time": str(stats[2]) if stats[2] else None,
        }

        fp_str = json.dumps(fingerprint_data, sort_keys=True)
        fingerprint_hash = hashlib.sha256(fp_str.encode()).hexdigest()
        fingerprint_data["fingerprint"] = fingerprint_hash

        return fingerprint_data
