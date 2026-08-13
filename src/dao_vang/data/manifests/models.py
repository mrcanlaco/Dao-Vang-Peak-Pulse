from datetime import datetime

from pydantic import BaseModel, Field

from dao_vang.domain.enums import RunStatus


class CollectionRunManifest(BaseModel):
    """Manifest for a collection run."""

    collection_run_id: str = Field(..., description="Unique ID for this run")
    started_at: datetime = Field(
        ..., description="Start time in Asia/Ho_Chi_Minh (UTC+7)"
    )
    completed_at: datetime | None = None
    status: RunStatus = Field(..., description="Status of the run")
    data_type: str = Field(..., description="Type of data collected (e.g. klines)")
    range_start: datetime = Field(..., description="Start of requested time range")
    range_end: datetime = Field(..., description="End of requested time range")
    rows_raw: int = Field(default=0, ge=0, description="Raw records collected")
    rows_normalized: int = Field(
        default=0, ge=0, description="Normalized records produced"
    )
    error_count: int = Field(default=0, ge=0, description="Errors encountered")
    collector_version: str = Field(..., description="Version of the collector")


class DatasetManifest(BaseModel):
    """Manifest for an aligned dataset."""

    dataset_version: str = Field(..., description="Unique dataset version identifier")
    created_at: datetime = Field(
        ..., description="Creation time in Asia/Ho_Chi_Minh (UTC+7)"
    )
    source_versions: dict[str, str] = Field(
        ..., description="data_type to source_version"
    )
    input_files: list[str] = Field(..., description="Input files used to build dataset")
    input_hashes: list[str] = Field(..., description="SHA256 hashes of input files")
    schema_version: str = Field(..., description="Schema version of the output dataset")
    alignment_version: str = Field(..., description="Alignment rules version used")
    row_count: int = Field(..., ge=0, description="Total number of rows in the dataset")
    min_time: datetime = Field(..., description="Earliest feature_time in dataset")
    max_time: datetime = Field(..., description="Latest feature_time in dataset")
    fingerprint_sha256: str = Field(..., description="Deterministic fingerprint hash")
