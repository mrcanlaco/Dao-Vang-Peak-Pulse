"""Point-in-time label engine for ``distribution_short_v2`` (20%/24h)."""

from __future__ import annotations

from collections.abc import Iterable

import duckdb

from dao_vang.labels.engine_v1 import DistributionLabelEngineV1, _identifier
from dao_vang.labels.specs.distribution_short_v2 import (
    DistributionShortV2Spec,
    specs,
)


class DistributionLabelEngineV2(DistributionLabelEngineV1):
    """Materialize the 20%/24h contract without mutating the v1 history."""

    def __init__(self, spec: DistributionShortV2Spec):
        if spec.horizon_hours != 24:
            raise ValueError("distribution_short_v2 supports only the 24h horizon")
        super().__init__(spec)  # type: ignore[arg-type]

    def compute_all_horizons_to_table(
        self,
        db: duckdb.DuckDBPyConnection,
        input_table: str,
        output_table: str,
        horizons: Iterable[int] = (24,),
    ) -> None:
        requested = tuple(dict.fromkeys(int(h) for h in horizons))
        invalid = [h for h in requested if h not in specs]
        if not requested or invalid:
            raise ValueError(
                "distribution_short_v2 horizons must contain only 24; "
                f"invalid={invalid}"
            )

        target = _identifier(output_table)
        temp_tables: list[str] = []
        try:
            for horizon in requested:
                temp = f"_labels_v2_{horizon}h"
                temp_tables.append(temp)
                DistributionLabelEngineV2(specs[horizon]).compute_all_to_table(
                    db, input_table, temp
                )
            union_sql = " UNION ALL ".join(
                f"SELECT * FROM {temp}" for temp in temp_tables
            )
            for statement in (
                f"DROP TABLE IF EXISTS {target}",
                f"DROP VIEW IF EXISTS {target}",
            ):
                try:
                    db.execute(statement)
                except Exception:
                    pass
            db.execute(f"CREATE TABLE {target} AS {union_sql}")
        finally:
            for temp in temp_tables:
                try:
                    db.execute(f"DROP TABLE IF EXISTS {temp}")
                except Exception:
                    pass


__all__ = ["DistributionLabelEngineV2"]
