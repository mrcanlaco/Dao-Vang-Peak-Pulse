from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from dao_vang.data.manifests.models import CollectionRunManifest, DatasetManifest
from dao_vang.domain.enums import RunStatus


def test_collection_run_manifest_valid() -> None:
    now = datetime.now(timezone.utc)
    manifest = CollectionRunManifest(
        collection_run_id="run-1",
        started_at=now,
        status=RunStatus.RUNNING,
        data_type="klines",
        range_start=now,
        range_end=now,
        collector_version="v1",
    )
    assert manifest.collection_run_id == "run-1"
    assert manifest.rows_raw == 0


def test_collection_run_manifest_invalid_status() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        CollectionRunManifest(
            collection_run_id="run-1",
            started_at=now,
            status="invalid_status",  # type: ignore
            data_type="klines",
            range_start=now,
            range_end=now,
            collector_version="v1",
        )


def test_dataset_manifest_valid() -> None:
    now = datetime.now(timezone.utc)
    manifest = DatasetManifest(
        dataset_version="ds-v1",
        created_at=now,
        source_versions={"klines": "src-v1"},
        input_files=["file1.parquet"],
        input_hashes=["hash1"],
        schema_version="schema-v1",
        alignment_version="align-v1",
        row_count=100,
        min_time=now,
        max_time=now,
        fingerprint_sha256="abcd",
    )
    assert manifest.dataset_version == "ds-v1"
    assert manifest.row_count == 100


def test_dataset_manifest_invalid_negative_rows() -> None:
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        DatasetManifest(
            dataset_version="ds-v1",
            created_at=now,
            source_versions={"klines": "src-v1"},
            input_files=["file1.parquet"],
            input_hashes=["hash1"],
            schema_version="schema-v1",
            alignment_version="align-v1",
            row_count=-5,
            min_time=now,
            max_time=now,
            fingerprint_sha256="abcd",
        )
