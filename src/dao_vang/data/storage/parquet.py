import os
import tempfile
from pathlib import Path
from typing import Sequence

import pyarrow as pa  # type: ignore
import pyarrow.parquet as pq  # type: ignore

from dao_vang.data.schemas import NormalizedBase
from dao_vang.data.storage.writer import compute_checksum


def write_normalized_to_parquet(
    target_path: Path, items: Sequence[NormalizedBase]
) -> str:
    """
    Atomically write a sequence of normalized models to a Parquet file.
    Returns the SHA-256 checksum of the written file.
    """
    if not items:
        raise ValueError("Cannot write an empty list to Parquet without a schema.")

    target_path.parent.mkdir(parents=True, exist_ok=True)

    data = [item.model_dump(mode="python") for item in items]
    table = pa.Table.from_pylist(data)  # type: ignore

    fd, temp_path = tempfile.mkstemp(
        dir=target_path.parent,
        prefix=".tmp_",
        suffix=".parquet",
    )
    os.close(fd)

    try:
        pq.write_table(table, temp_path)  # type: ignore
        checksum = compute_checksum(Path(temp_path))
        os.replace(temp_path, target_path)
        return checksum
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise
