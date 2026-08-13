"""Feature-group ablation planning and execution helpers.

Ablations are descriptive OOS experiments.  This module only constructs the
feature variants; model selection remains the caller's responsibility on a
validation split.  It never mutates the source table.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Mapping

import duckdb

FEATURE_GROUPS: dict[str, tuple[str, ...]] = {
    "price": (
        "price_ret_5m",
        "price_ret_1h",
        "price_ret_4h",
        "price_ret_24h",
        "price_volatility_24h",
        "distance_from_high_24h",
        "momentum_deceleration_4h",
        "fake_breakout_1h",
    ),
    "volume": ("volume_percentile_24h",),
    "funding": ("funding_rate_raw", "funding_zscore_30d"),
    "oi": ("oi_change_1h", "oi_change_4h", "oi_change_24h"),
    "taker": ("taker_buy_ratio", "taker_buy_ratio_change_1h"),
    "ratios": (
        "global_long_short_ratio",
        "top_long_short_account_ratio",
        "top_long_short_position_ratio",
    ),
}

ABLATION_MATRIX: dict[str, tuple[str, ...]] = {
    "full": (),
    "price_only": (
        "volume",
        "funding",
        "oi",
        "taker",
        "ratios",
    ),
    "price_volume": ("funding", "oi", "taker", "ratios"),
    "price_derivs": ("volume",),
    "no_funding": ("funding",),
    "no_oi": ("oi",),
    "no_taker": ("taker",),
    "no_ratios": ("ratios",),
}


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"Unsafe SQL identifier: {value!r}")
    return value


def _columns(db: duckdb.DuckDBPyConnection, table_name: str) -> list[str]:
    table = _safe_identifier(table_name)
    return [str(row[0]) for row in db.execute(f"DESCRIBE {table}").fetchall()]


def generate_ablation_queries(
    db: duckdb.DuckDBPyConnection,
    table_name: str,
    *,
    matrix: Mapping[str, tuple[str, ...]] | None = None,
) -> dict[str, str]:
    """Generate deterministic SELECT queries that null selected groups."""

    table = _safe_identifier(table_name)
    all_cols = _columns(db, table)
    resolved_matrix = matrix or ABLATION_MATRIX
    queries: dict[str, str] = {}
    for experiment_name, groups_to_drop in resolved_matrix.items():
        null_cols = {
            column
            for group in groups_to_drop
            for column in FEATURE_GROUPS.get(group, (group,))
        }
        select_clause = [
            f"NULL AS {column}" if column in null_cols else column
            for column in all_cols
        ]
        queries[experiment_name] = f"SELECT {', '.join(select_clause)} FROM {table}"
    return queries


def run_ablation_matrix(
    db: duckdb.DuckDBPyConnection,
    table_name: str,
    evaluator: Callable[[Any, str], Mapping[str, Any]],
    *,
    matrix: Mapping[str, tuple[str, ...]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Run a caller-provided OOS evaluator for each ablation variant.

    ``evaluator`` receives a pandas DataFrame and the variant name.  Keeping
    evaluation outside this module prevents an ablation from accidentally
    choosing a model using the test fold.
    """

    queries = generate_ablation_queries(db, table_name, matrix=matrix)
    results: dict[str, dict[str, Any]] = {}
    for name, query in queries.items():
        frame = db.execute(query).df()
        results[name] = dict(evaluator(frame, name))
    return results


def feature_group_for_column(column: str) -> str | None:
    """Return the evidence/ablation group owning a feature."""

    for group, columns in FEATURE_GROUPS.items():
        if column in columns:
            return group
    return None


def dropped_columns_for_variant(
    variant: str, *, matrix: Mapping[str, tuple[str, ...]] | None = None
) -> tuple[str, ...]:
    """Expose a stable list of columns nulled by one variant."""

    resolved_matrix = matrix or ABLATION_MATRIX
    if variant not in resolved_matrix:
        raise KeyError(f"Unknown ablation variant {variant!r}")
    return tuple(
        column
        for group in resolved_matrix[variant]
        for column in FEATURE_GROUPS.get(group, (group,))
    )
