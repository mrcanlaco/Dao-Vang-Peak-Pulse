from pathlib import Path
from datetime import date

def get_raw_path(base_dir: Path, data_type: str, dt: date) -> Path:
    return base_dir / "raw" / data_type / f"date={dt.isoformat()}"

def get_normalized_path(base_dir: Path, data_type: str, interval: str, dt: date) -> Path:
    return base_dir / "normalized" / data_type / f"interval={interval}" / f"date={dt.isoformat()}"

def get_aligned_path(base_dir: Path, dataset_version: str) -> Path:
    return base_dir / "aligned" / f"dataset_version={dataset_version}"

def get_features_path(base_dir: Path, feature_set_version: str) -> Path:
    return base_dir / "features" / f"feature_set_version={feature_set_version}"

def get_metadata_path(base_dir: Path) -> Path:
    return base_dir / "metadata"

def get_artifacts_path(base_dir: Path, experiment_id: str) -> Path:
    return base_dir / "artifacts" / f"experiment_id={experiment_id}"
