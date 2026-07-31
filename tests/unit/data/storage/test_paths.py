from datetime import date
from pathlib import Path
from dao_vang.data.storage.paths import (
    get_raw_path,
    get_normalized_path,
    get_aligned_path,
    get_features_path,
    get_metadata_path,
    get_artifacts_path,
)

def test_get_raw_path() -> None:
    base = Path("/data")
    dt = date(2026, 1, 1)
    assert get_raw_path(base, "klines", dt) == Path("/data/raw/klines/date=2026-01-01")

def test_get_normalized_path() -> None:
    base = Path("/data")
    dt = date(2026, 1, 1)
    assert get_normalized_path(base, "klines", "5m", dt) == Path("/data/normalized/klines/interval=5m/date=2026-01-01")

def test_get_aligned_path() -> None:
    base = Path("/data")
    assert get_aligned_path(base, "v1") == Path("/data/aligned/dataset_version=v1")

def test_get_features_path() -> None:
    base = Path("/data")
    assert get_features_path(base, "v1") == Path("/data/features/feature_set_version=v1")

def test_get_metadata_path() -> None:
    base = Path("/data")
    assert get_metadata_path(base) == Path("/data/metadata")

def test_get_artifacts_path() -> None:
    base = Path("/data")
    assert get_artifacts_path(base, "exp1") == Path("/data/artifacts/experiment_id=exp1")
