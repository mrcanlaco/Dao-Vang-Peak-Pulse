"""Leakage-safe V3 pattern discovery and held-out evidence.

This module is deliberately research-only.  It discovers deterministic market
templates from point-in-time price, volume, funding and open-interest features,
then evaluates a fixed set of five score thresholds on one common chronological
holdout.  No threshold is selected from the holdout and no result promotes a
model or changes the V3 champion gate.

The historical ``distribution_v3_training.duckdb`` artifact is known to carry
the older Entry-1 label under both ``label_value`` and
``entry1_label_value``.  The loader detects that provenance and marks its
metrics ``diagnostic_entry1``; it never presents them as compact weighted-
average evidence.  A caller must provide an explicit ``compact_policy_label``
column (and provenance) to obtain compact-policy metrics.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import duckdb
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans

from dao_vang.labels.specs.distribution_short_v3 import SPEC

PATTERN_MODEL_VERSION = "v3_pattern_templates_v1"
RESEARCH_REPORT_VERSION = "v3_pattern_research_v1"
DEFAULT_THRESHOLDS: tuple[float, ...] = (0.20, 0.30, 0.40, 0.50, 0.60)
CONDITION_THRESHOLDS: dict[str, tuple[float, ...]] = {
    "pump": (0.15, 0.20, 0.25, 0.30, 0.35),
    "reversal": (-0.01, -0.02, -0.03, -0.04, -0.05),
    "funding_percentile": (0.60, 0.70, 0.80, 0.90, 0.95),
    "funding_change_8h": (0.0, 0.0001, 0.0005, 0.001, 0.002),
    "reference_score": (0.29, 0.34, 0.39, 0.44, 0.49),
}
# Only these explicitly named columns are accepted for the user-defined
# reference-score condition.  Generic ``score``/``probability`` fields are
# intentionally not guessed as reference-model provenance.
REFERENCE_SCORE_COLUMNS: tuple[str, ...] = (
    "reference_score",
    "reference_model_score",
)

# Feature order is intentionally explicit and stable.  Columns absent from a
# source are omitted from a fitted model; they are not fabricated or silently
# filled from future rows.
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
        "lower_high_4h",
    ),
    "volume": (
        "volume_percentile_24h",
        "volume_zscore_24h",
        "volume_ratio_1h",
        "volume_dry_up_1h",
        "quote_volume_24h",
    ),
    "funding": (
        "funding_rate_raw",
        "funding_percentile_7d",
        "funding_percentile_30d",
        "funding_zscore_30d",
        "funding_change_8h",
        "funding_change_24h",
        "funding_persistence_7d",
        "funding_accumulated_3d",
        "funding_accumulated_7d",
        "funding_rate_streak",
    ),
    "oi": (
        "oi_change_1h",
        "oi_change_4h",
        "oi_change_24h",
        "oi_zscore_7d",
        "oi_acceleration_1h",
        "price_oi_divergence_1h",
    ),
}
DEFAULT_FEATURE_COLUMNS: tuple[str, ...] = tuple(
    column for group in FEATURE_GROUPS.values() for column in group
)


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def canonical(value: Any) -> str:
    return json.dumps(
        value,
        default=_json_default,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest(value: Any) -> str:
    return sha256(canonical(value).encode("utf-8")).hexdigest()


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _utc(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _feature_columns(frame: pd.DataFrame, requested: Iterable[str] | None) -> list[str]:
    candidates = list(requested or DEFAULT_FEATURE_COLUMNS)
    result = []
    for column in candidates:
        if column not in frame.columns:
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        # A feature with no finite development values provides no template
        # information and must remain an explicit missing feature.
        if int(numeric.notna().sum()) > 0:
            result.append(column)
    return result


def _feature_group(column: str) -> str:
    for group, columns in FEATURE_GROUPS.items():
        if column in columns:
            return group
    return "other"


def _pattern_type(center: Mapping[str, float]) -> str:
    """Give a descriptive name to a discovered template, not a probability."""

    pump = center.get("price_ret_24h", 0.0)
    reversal = center.get("distance_from_high_24h", 0.0)
    momentum = center.get("momentum_deceleration_4h", 0.0)
    funding = center.get("funding_percentile_30d", center.get("funding_percentile_7d", 0.0))
    oi = center.get("oi_change_4h", center.get("oi_change_1h", 0.0))
    volume = center.get("volume_percentile_24h", 0.0)
    if pump >= 0.25 and reversal <= -0.02 and momentum >= 0:
        return "climax_exhaustion"
    if funding >= 0.80 and oi >= 0:
        return "crowded_long_build"
    if oi < 0 and reversal <= 0:
        return "oi_unwind"
    if volume < 0.35 and reversal <= 0:
        return "volume_exhaustion"
    if reversal <= -0.02:
        return "distribution_rollover"
    return "mixed_market_state"


def classify_stage(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Classify stage from contemporaneous features only.

    Thresholds are a published descriptive convention, not a trained outcome
    model.  Missing price context yields ``unknown`` with explicit reasons.
    """

    values = {key: _finite(snapshot.get(key)) for key in (
        "price_ret_1h",
        "price_ret_4h",
        "price_ret_24h",
        "distance_from_high_24h",
        "momentum_deceleration_4h",
        "fake_breakout_1h",
    )}
    missing = [key for key, value in values.items() if value is None]
    if values["price_ret_24h"] is None or values["distance_from_high_24h"] is None:
        return {
            "stage": "unknown",
            "status": "unknown",
            "reason": "price_context_missing",
            "missing_features": missing,
        }
    pump = values["price_ret_24h"] or 0.0
    distance = values["distance_from_high_24h"] or 0.0
    one_hour = values["price_ret_1h"]
    momentum = values["momentum_deceleration_4h"]
    fake_breakout = values["fake_breakout_1h"]
    if distance <= -0.05:
        stage = "post_peak"
    elif distance <= -0.02 and (
        (momentum is not None and momentum >= 0.0)
        or (fake_breakout is not None and fake_breakout > 0.0)
        or (one_hour is not None and one_hour <= 0.0)
    ):
        stage = "distributing"
    elif distance <= -0.01 or (momentum is not None and momentum >= 0.0):
        stage = "exhausting"
    elif pump >= 0.15:
        stage = "pumping"
    else:
        stage = "forming"
    return {
        "stage": stage,
        "status": "determined" if not missing else "partial",
        "reason": "descriptive_price_stage",
        "missing_features": missing,
    }


@dataclass(frozen=True)
class PatternModel:
    version: str
    feature_columns: tuple[str, ...]
    medians: tuple[float, ...]
    scales: tuple[float, ...]
    centers: tuple[tuple[float, ...], ...]
    pattern_ids: tuple[str, ...]
    pattern_types: tuple[str, ...]
    pattern_counts: tuple[int, ...]
    pattern_radii: tuple[float, ...]
    max_missing_fraction: float
    fit_rows: int
    fit_start: str | None
    fit_end: str | None
    random_state: int
    source_label_kind: str
    evidence_status: str
    checksum: str = field(default="", compare=False)

    def body(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "feature_columns": list(self.feature_columns),
            "medians": list(self.medians),
            "scales": list(self.scales),
            "centers": [list(center) for center in self.centers],
            "pattern_ids": list(self.pattern_ids),
            "pattern_types": list(self.pattern_types),
            "pattern_counts": list(self.pattern_counts),
            "pattern_radii": list(self.pattern_radii),
            "max_missing_fraction": self.max_missing_fraction,
            "fit_rows": self.fit_rows,
            "fit_start": self.fit_start,
            "fit_end": self.fit_end,
            "random_state": self.random_state,
            "source_label_kind": self.source_label_kind,
            "evidence_status": self.evidence_status,
        }

    def to_dict(self) -> dict[str, Any]:
        body = self.body()
        body["checksum"] = self.checksum or digest(body)
        return body

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(canonical(self.to_dict()), encoding="utf-8")


def load_pattern_model(path: Path) -> PatternModel:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("version") != PATTERN_MODEL_VERSION:
        raise ValueError("unsupported pattern model version")
    checksum = payload.get("checksum")
    body = {key: value for key, value in payload.items() if key != "checksum"}
    if not isinstance(checksum, str) or checksum != digest(body):
        raise ValueError("pattern model checksum mismatch")
    model = PatternModel(
        version=payload["version"],
        feature_columns=tuple(payload["feature_columns"]),
        medians=tuple(float(value) for value in payload["medians"]),
        scales=tuple(float(value) for value in payload["scales"]),
        centers=tuple(tuple(float(value) for value in center) for center in payload["centers"]),
        pattern_ids=tuple(payload["pattern_ids"]),
        pattern_types=tuple(payload["pattern_types"]),
        pattern_counts=tuple(int(value) for value in payload["pattern_counts"]),
        pattern_radii=tuple(float(value) for value in payload.get("pattern_radii", [3.0] * len(payload["pattern_ids"]))),
        max_missing_fraction=float(payload["max_missing_fraction"]),
        fit_rows=int(payload["fit_rows"]),
        fit_start=payload.get("fit_start"),
        fit_end=payload.get("fit_end"),
        random_state=int(payload["random_state"]),
        source_label_kind=str(payload.get("source_label_kind", "unknown")),
        evidence_status=str(payload.get("evidence_status", "exploratory")),
        checksum=checksum,
    )
    if len(model.feature_columns) != len(model.medians) or len(model.centers) != len(model.pattern_ids):
        raise ValueError("malformed pattern model dimensions")
    return model


def fit_pattern_model(
    frame: pd.DataFrame,
    *,
    feature_columns: Iterable[str] | None = None,
    n_patterns: int = 5,
    random_state: int = 42,
    max_missing_fraction: float = 0.20,
    source_label_kind: str = "unknown",
    evidence_status: str = "exploratory",
) -> PatternModel:
    """Fit unsupervised templates on development rows only."""

    if n_patterns < 1:
        raise ValueError("n_patterns must be positive")
    if frame.empty:
        raise ValueError("cannot fit patterns on an empty frame")
    columns = _feature_columns(frame, feature_columns)
    if not columns:
        raise ValueError("no finite pattern features available")
    values = frame[columns].apply(pd.to_numeric, errors="coerce")
    medians = values.median(axis=0, skipna=True).fillna(0.0)
    filled = values.fillna(medians)
    scales = (filled.quantile(0.75) - filled.quantile(0.25)).replace(0, np.nan)
    scales = scales.fillna(filled.std(ddof=0)).replace(0, np.nan).fillna(1.0)
    scaled = ((filled - medians) / scales).to_numpy(dtype=float)
    distinct_count = max(1, int(np.unique(np.round(scaled, decimals=10), axis=0).shape[0]))
    cluster_count = min(n_patterns, len(scaled), distinct_count)
    if cluster_count == 1:
        labels = np.zeros(len(scaled), dtype=int)
        centers = np.mean(scaled, axis=0, keepdims=True)
    else:
        cluster = KMeans(
            n_clusters=cluster_count,
            n_init=20,
            random_state=random_state,
            algorithm="lloyd",
        ).fit(scaled)
        labels = np.asarray(cluster.labels_, dtype=int)
        centers = np.asarray(cluster.cluster_centers_, dtype=float)
    # Stable IDs independent of KMeans' internal cluster numbering.
    order = sorted(range(cluster_count), key=lambda idx: tuple(np.round(centers[idx], 10)))
    remap = {old: new for new, old in enumerate(order)}
    centers = centers[order]
    labels = np.asarray([remap[int(label)] for label in labels], dtype=int)
    pattern_ids = tuple(f"pattern_{index + 1:02d}" for index in range(cluster_count))
    pattern_types = tuple(
        _pattern_type(
            {
                column: float(medians[column] + centers[index, j] * scales[column])
                for j, column in enumerate(columns)
            }
        )
        for index in range(cluster_count)
    )
    counts = tuple(int((labels == index).sum()) for index in range(cluster_count))
    radii_values: list[float] = []
    for index in range(cluster_count):
        member = scaled[labels == index]
        distances = np.sqrt(np.mean((member - centers[index]) ** 2, axis=1)) if len(member) else np.asarray([3.0])
        # Radius is fit on development rows only.  It lets a complete but
        # out-of-distribution snapshot remain unknown while retaining its
        # nearest template and feature discrepancies.
        radii_values.append(float(max(1.5, np.quantile(distances, 0.95) + 0.25)))
    feature_time = pd.to_datetime(frame.get("feature_time"), utc=True, errors="coerce")
    valid_times = feature_time.dropna()
    model = PatternModel(
        version=PATTERN_MODEL_VERSION,
        feature_columns=tuple(columns),
        medians=tuple(float(medians[column]) for column in columns),
        scales=tuple(float(scales[column]) for column in columns),
        centers=tuple(tuple(float(value) for value in center) for center in centers),
        pattern_ids=pattern_ids,
        pattern_types=pattern_types,
        pattern_counts=counts,
        pattern_radii=tuple(radii_values),
        max_missing_fraction=float(max_missing_fraction),
        fit_rows=len(frame),
        fit_start=valid_times.min().isoformat() if not valid_times.empty else None,
        fit_end=valid_times.max().isoformat() if not valid_times.empty else None,
        random_state=random_state,
        source_label_kind=source_label_kind,
        evidence_status=evidence_status,
    )
    return PatternModel(**{**asdict(model), "checksum": digest(model.body())})


def classify_snapshot(snapshot: Mapping[str, Any], model: PatternModel) -> dict[str, Any]:
    """Classify a current snapshot using only its contemporaneous features."""

    values: list[float | None] = [
        _finite(snapshot.get(column)) for column in model.feature_columns
    ]
    missing = [
        column for column, value in zip(model.feature_columns, values, strict=True)
        if value is None
    ]
    available_indices = [index for index, value in enumerate(values) if value is not None]
    stage = classify_stage(snapshot)
    if not available_indices:
        return {
            "pattern_id": "unknown",
            "pattern_type": "unknown",
            "stage": stage["stage"],
            "status": "unknown",
            "nearest_pattern": None,
            "distance": None,
            "radius": None,
            "unknown_reason": "no_available_pattern_features",
            "discrepancies": [],
            "missing_features": missing,
            "quality_status": "unconfirmed",
            "model_version": model.version,
        }
    standard = np.zeros(len(model.feature_columns), dtype=float)
    for index, value in enumerate(values):
        if value is not None:
            standard[index] = (value - model.medians[index]) / model.scales[index]
    available = np.asarray(available_indices, dtype=int)
    centers = np.asarray(model.centers, dtype=float)
    distances = np.sqrt(np.mean((centers[:, available] - standard[available]) ** 2, axis=1))
    nearest_index = int(np.argmin(distances))
    nearest_distance = float(distances[nearest_index])
    missing_fraction = len(missing) / len(model.feature_columns)
    radius = model.pattern_radii[nearest_index] if nearest_index < len(model.pattern_radii) else 3.0
    in_radius = nearest_distance <= radius
    status = "determined" if missing_fraction <= model.max_missing_fraction and in_radius else "unknown"
    unknown_reason = None
    if missing_fraction > model.max_missing_fraction:
        unknown_reason = "too_many_missing_features"
    elif not in_radius:
        unknown_reason = "nearest_template_distance_exceeds_train_radius"
    discrepancies = []
    for index in available_indices:
        discrepancy = abs(float(standard[index] - centers[nearest_index, index]))
        discrepancies.append(
            {
                "feature": model.feature_columns[index],
                "group": _feature_group(model.feature_columns[index]),
                "value": float(values[index]),
                "template_value": float(
                    model.medians[index] + centers[nearest_index, index] * model.scales[index]
                ),
                "standardized_abs_error": float(discrepancy),
            }
        )
    discrepancies.sort(key=lambda item: (-item["standardized_abs_error"], item["feature"]))
    return {
        "pattern_id": model.pattern_ids[nearest_index] if status == "determined" else "unknown",
        "pattern_type": model.pattern_types[nearest_index] if status == "determined" else "unknown",
        "stage": stage["stage"],
        "status": status,
        "nearest_pattern": model.pattern_ids[nearest_index],
        "nearest_pattern_type": model.pattern_types[nearest_index],
        "distance": nearest_distance,
        "radius": float(radius),
        "unknown_reason": unknown_reason,
        "discrepancies": discrepancies[:8],
        "missing_features": missing,
        "quality_status": "unconfirmed",
        "model_version": model.version,
    }


def _label_kind(frame: pd.DataFrame, label_column: str | None = None) -> tuple[str, str, str | None]:
    """Return (column, metric kind, reason) without guessing compact labels."""

    if label_column and label_column not in frame.columns:
        raise ValueError(f"label column not found: {label_column}")
    if label_column:
        column = label_column
    elif "compact_policy_label" in frame.columns:
        column = "compact_policy_label"
    elif "actual_policy_label" in frame.columns:
        column = "actual_policy_label"
    elif "entry1_label_value" in frame.columns:
        column = "entry1_label_value"
    elif "label_value" in frame.columns:
        column = "label_value"
    else:
        return "", "unsupported", "no_outcome_label"
    if column in {"entry1_label_value", "entry1_label", "entry1_target_label"}:
        return column, "diagnostic_entry1", "entry1_label_not_compact_weighted_average"
    if column == "label_value" and "entry1_label_value" in frame.columns:
        equal = frame[column].fillna(-1).eq(frame["entry1_label_value"].fillna(-1)).all()
        if equal:
            return column, "diagnostic_entry1", "label_equals_entry1_label"
    if column in {"compact_policy_label", "actual_policy_label"}:
        # A friendly column name is not provenance.  The caller must provide
        # an exact contract/version/checksum/mode sidecar before these rows can
        # be called compact-policy evidence.
        return column, "declared_compact_unverified", "compact_contract_sidecar_required"
    return column, "unknown", "label_contract_not_declared"


def _compact_provenance_verified(provenance: Mapping[str, Any] | None) -> bool:
    value = dict(provenance or {})
    return (
        value.get("outcome_contract") == SPEC.version
        and value.get("outcome_contract_checksum") == SPEC.checksum
        and value.get("engine_version") == SPEC.engine_version
        and value.get("outcome_mode") == "compact_policy"
        and value.get("label_column") in {"compact_policy_label", "actual_policy_label"}
        and value.get("eligibility_verified") is True
    )


def load_research_frame(
    dataset_db: Path,
    *,
    table: str = "distribution_v3_hourly_candidates",
    label_column: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Read an offline dataset read-only and classify label provenance."""

    connection = duckdb.connect(str(dataset_db), read_only=True)
    try:
        # Identifiers cannot be query parameters; require a conservative SQL
        # identifier instead of interpolating arbitrary input.
        if not table.replace("_", "").isalnum():
            raise ValueError("invalid dataset table name")
        frame = connection.execute(f'SELECT * FROM "{table}"').fetchdf()
    finally:
        connection.close()
    if "feature_time" not in frame.columns:
        raise ValueError("dataset requires feature_time")
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True, errors="coerce")
    frame = frame[frame["feature_time"].notna()].copy()
    frame = frame.sort_values(["feature_time", "symbol"] if "symbol" in frame.columns else ["feature_time"])
    column, kind, reason = _label_kind(frame, label_column)
    if column:
        frame["_outcome_label"] = pd.to_numeric(frame[column], errors="coerce")
        frame.loc[~frame["_outcome_label"].isin([0, 1]), "_outcome_label"] = np.nan
    else:
        frame["_outcome_label"] = np.nan
    provenance = {
        "dataset_path": str(dataset_db),
        "dataset_table": table,
        "rows": int(len(frame)),
        "labeled_rows": int(frame["_outcome_label"].notna().sum()),
        "label_column": column or None,
        "label_kind": kind,
        "label_contract_reason": reason,
        "compact_contract_verified": kind == "compact_policy",
        "actual_contract": SPEC.version if kind == "compact_policy" else None,
    }
    return frame.reset_index(drop=True), provenance


def _episode_ids(frame: pd.DataFrame, gap_hours: int = 6) -> pd.Series:
    if frame.empty:
        return pd.Series(dtype="string")
    working = frame.copy()
    working["_position"] = np.arange(len(working))
    working = working.sort_values(["symbol", "feature_time"] if "symbol" in working else ["feature_time"])
    if "symbol" in working:
        gap = working.groupby("symbol", sort=False)["feature_time"].diff()
        start = gap.isna() | (gap > pd.Timedelta(hours=gap_hours))
        number = start.groupby(working["symbol"], sort=False).cumsum().astype(int)
        ids = working["symbol"].astype(str) + ":" + number.astype(str)
    else:
        gap = working["feature_time"].diff()
        ids = (gap.isna() | (gap > pd.Timedelta(hours=gap_hours))).cumsum().astype(str)
    output = pd.Series(ids.to_numpy(), index=working["_position"])
    return output.reindex(np.arange(len(frame))).astype("string")


def common_temporal_split(
    frame: pd.DataFrame,
    *,
    purge_hours: int = SPEC.horizon_hours,
    train_fraction: float = 0.60,
    policy_fraction: float = 0.20,
) -> dict[str, pd.DataFrame | dict[str, Any]]:
    """Create one split shared by every threshold and baseline.

    Boundaries are chosen from unique timestamps, then a 48-hour embargo is
    applied on both sides of each boundary.  The holdout is never passed to
    fitting or threshold selection.
    """

    if frame.empty:
        raise ValueError("cannot split an empty frame")
    times = pd.Series(frame["feature_time"].dropna().drop_duplicates()).sort_values()
    if len(times) < 5:
        raise ValueError("insufficient unique timestamps for temporal split")
    train_fraction = float(train_fraction)
    policy_fraction = float(policy_fraction)
    if not 0 < train_fraction < 1 or not 0 < policy_fraction < 1 or train_fraction + policy_fraction >= 1:
        raise ValueError("invalid temporal split fractions")
    train_boundary = times.iloc[min(len(times) - 1, max(1, int(len(times) * train_fraction)))]
    holdout_boundary = times.iloc[min(len(times) - 1, max(2, int(len(times) * (train_fraction + policy_fraction))))]
    purge = pd.Timedelta(hours=purge_hours)
    # A short synthetic fixture (or a thin historical slice) may leave no
    # policy rows after two 48-hour embargoes.  Widen the common middle window
    # deterministically; never relax the embargo itself or inspect labels.
    if holdout_boundary - train_boundary <= purge * 2:
        train_index = max(1, int(len(times) * 0.35))
        holdout_index = min(len(times) - 1, max(train_index + 1, int(len(times) * 0.75)))
        train_boundary = times.iloc[train_index]
        holdout_boundary = times.iloc[holdout_index]
    train = frame[frame["feature_time"] < train_boundary - purge].copy()
    policy = frame[
        (frame["feature_time"] >= train_boundary + purge)
        & (frame["feature_time"] < holdout_boundary - purge)
    ].copy()
    holdout = frame[frame["feature_time"] >= holdout_boundary + purge].copy()
    windows = {
        "train": {
            "rows": int(len(train)),
            "start": train["feature_time"].min().isoformat() if not train.empty else None,
            "end": train["feature_time"].max().isoformat() if not train.empty else None,
        },
        "policy": {
            "rows": int(len(policy)),
            "start": policy["feature_time"].min().isoformat() if not policy.empty else None,
            "end": policy["feature_time"].max().isoformat() if not policy.empty else None,
        },
        "heldout": {
            "rows": int(len(holdout)),
            "start": holdout["feature_time"].min().isoformat() if not holdout.empty else None,
            "end": holdout["feature_time"].max().isoformat() if not holdout.empty else None,
        },
        "purge_hours": purge_hours,
        "train_boundary": train_boundary.isoformat(),
        "heldout_boundary": holdout_boundary.isoformat(),
        "common_across_variants": True,
    }
    return {"train": train, "policy": policy, "heldout": holdout, "metadata": windows}


def _dedupe_signals(frame: pd.DataFrame, threshold_mask: pd.Series, cooldown_hours: int = SPEC.horizon_hours) -> pd.DataFrame:
    candidates = frame.loc[threshold_mask].copy().sort_values("feature_time")
    if candidates.empty:
        candidates["_selected_episode"] = pd.Series(dtype=bool, index=candidates.index)
        return candidates
    accepted: list[int] = []
    last: dict[str, pd.Timestamp] = {}
    for index, row in candidates.iterrows():
        symbol = str(row.get("symbol", "__all__"))
        timestamp = _utc(row["feature_time"])
        if symbol in last and timestamp < last[symbol] + pd.Timedelta(hours=cooldown_hours):
            continue
        accepted.append(index)
        last[symbol] = timestamp
    selected = candidates.loc[accepted].copy()
    selected["_selected_episode"] = True
    return selected


def _pattern_scores(
    policy: pd.DataFrame,
    model: PatternModel,
) -> dict[str, float]:
    if policy.empty or "_outcome_label" not in policy:
        return {pattern_id: 0.0 for pattern_id in model.pattern_ids}
    # Match the evaluation cohort's event/cooldown handling.  Overlapping
    # hourly rows cannot inflate a pattern's policy rate.
    policy = _dedupe_signals(policy, pd.Series(True, index=policy.index))
    rates: dict[str, list[float]] = {pattern_id: [] for pattern_id in model.pattern_ids}
    for _, row in policy.iterrows():
        result = classify_snapshot(row.to_dict(), model)
        pattern_id = result.get("pattern_id")
        label = _finite(row.get("_outcome_label"))
        if pattern_id in rates and label is not None:
            rates[pattern_id].append(label)
    return {
        pattern_id: (float(np.mean(values)) if values else 0.0)
        for pattern_id, values in rates.items()
    }


def _pattern_support(policy: pd.DataFrame, model: PatternModel) -> dict[str, int]:
    """Count resolved, cooldown-deduped policy rows per pattern."""

    if policy.empty:
        return {pattern_id: 0 for pattern_id in model.pattern_ids}
    policy = _dedupe_signals(policy, pd.Series(True, index=policy.index))
    support = {pattern_id: 0 for pattern_id in model.pattern_ids}
    for _, row in policy.iterrows():
        if _finite(row.get("_outcome_label")) is None:
            continue
        pattern_id = classify_snapshot(row.to_dict(), model).get("pattern_id")
        if pattern_id in support:
            support[pattern_id] += 1
    return support


def champion_mask(frame: pd.DataFrame) -> pd.Series:
    """Locked V3 champion predicate, kept unchanged as the comparator."""

    values = {
        column: pd.to_numeric(frame.get(column, pd.Series(np.nan, index=frame.index)), errors="coerce")
        for column in (
            "price_ret_24h",
            "distance_from_high_24h",
            "funding_percentile_30d",
            "funding_persistence_7d",
            "funding_change_8h",
        )
    }
    return (
        values["price_ret_24h"].ge(0.25)
        & values["distance_from_high_24h"].le(-0.02)
        & values["funding_percentile_30d"].ge(0.80)
        & values["funding_persistence_7d"].gt(0.0)
        & values["funding_change_8h"].gt(0.0)
    ).fillna(False)


def _condition_mask(frame: pd.DataFrame, condition: str, threshold: float) -> pd.Series:
    """Apply one independently varied champion condition.

    The other four conditions stay at the locked champion values.  This is an
    ablation report, not a selector: all values are scored on the same holdout
    and none is promoted automatically.
    """

    def values(column: str) -> pd.Series:
        return pd.to_numeric(
            frame.get(column, pd.Series(np.nan, index=frame.index)), errors="coerce"
        )

    reference_column = next(
        (
            column
            for column in REFERENCE_SCORE_COLUMNS
            if column in frame.columns
        ),
        None,
    )
    # The score is the fifth user-defined condition.  It is not safe to
    # ablate the other four while silently dropping that condition when a
    # source omitted the reference-model score.  Such a cohort is explicitly
    # unavailable for the exact-five study rather than a partial proxy.
    if reference_column is None:
        return pd.Series(False, index=frame.index)
    reference_values = values(reference_column)
    predicates: dict[str, pd.Series] = {
        "pump": values("price_ret_24h").ge(threshold),
        "reversal": values("distance_from_high_24h").le(threshold),
        "funding_percentile": values("funding_percentile_30d").ge(threshold),
        "funding_change_8h": values("funding_change_8h").gt(threshold),
        "reference_score": (
            reference_values.ge(threshold)
        ),
    }
    fixed = {
        "pump": values("price_ret_24h").ge(0.25),
        "reversal": values("distance_from_high_24h").le(-0.02),
        "funding_percentile": values("funding_percentile_30d").ge(0.80),
        "funding_change_8h": values("funding_change_8h").gt(0.0),
    }
    mask = pd.Series(True, index=frame.index)
    for name, predicate in fixed.items():
        mask &= predicates[name] if name == condition else predicate
    # Keep the fifth score condition fixed for the four market ablations and
    # vary it only in the score ablation.  Persistence is the existing scout
    # gate and remains an additional fixed policy condition, not a substitute
    # for the user-defined reference score.
    mask &= predicates["reference_score"] if condition == "reference_score" else reference_values.ge(0.39)
    mask &= values("funding_persistence_7d").gt(0.0)
    return mask.fillna(False)


def _wilson_lower(successes: int, trials: int, z: float = 1.959963984540054) -> float | None:
    if trials <= 0:
        return None
    p = successes / trials
    denominator = 1.0 + z * z / trials
    center = p + z * z / (2.0 * trials)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials)
    return float(max(0.0, (center - margin) / denominator))


def _metric(frame: pd.DataFrame, mask: pd.Series, *, label_kind: str) -> dict[str, Any]:
    selected = _dedupe_signals(frame, mask)
    labels = pd.to_numeric(selected.get("_outcome_label", pd.Series(dtype=float)), errors="coerce")
    labels = labels[labels.notna()]
    symbols = selected["symbol"].nunique() if "symbol" in selected else len(selected)
    windows = (
        selected["feature_time"].dt.tz_localize(None).dt.to_period("W").nunique()
        if not selected.empty
        else 0
    )
    positive = int((labels == 1).sum())
    resolved = int(len(labels))
    precision = float(positive / resolved) if resolved else None
    target_rate = float(positive / resolved) if resolved else None
    conservative_ev = (
        target_rate * SPEC.target - (1.0 - target_rate) * SPEC.stop - 0.002
        if target_rate is not None
        else None
    )
    net_column = next(
        (column for column in ("net_return_planned", "actual_net_return", "net_return") if column in selected.columns),
        None,
    )
    net_values = pd.to_numeric(selected[net_column], errors="coerce").dropna() if net_column else pd.Series(dtype=float)
    return {
        "rows_selected": int(len(selected)),
        "episodes_selected": int(selected["episode_id"].nunique()) if "episode_id" in selected else int(len(selected)),
        "symbols_selected": int(symbols),
        "resolved": resolved,
        "excluded_or_unlabeled": int(len(selected) - resolved),
        "positive": positive,
        "precision": precision,
        "target_rate": target_rate,
        "wilson_lower_95": _wilson_lower(positive, resolved),
        "conservative_ev": conservative_ev,
        "actual_ev": float(net_values.mean()) if not net_values.empty else None,
        "paired_ev_lower_bound": None,
        "ece": None,
        "windows": int(windows),
        "metric_kind": label_kind,
        "event_dedupe": "symbol_cooldown_48h_after_common_split",
    }


def _quality(
    variant: dict[str, Any],
    champion: dict[str, Any],
    *,
    compact_verified: bool,
    min_episodes: int,
    min_windows: int,
    min_relative_improvement: float,
    min_absolute_improvement: float,
) -> dict[str, Any]:
    precision = variant.get("precision")
    champion_precision = champion.get("precision")
    improvement = (
        float(precision - champion_precision)
        if precision is not None and champion_precision is not None
        else None
    )
    relative = (
        improvement / champion_precision
        if improvement is not None and champion_precision
        else None
    )
    checks = {
        "compact_contract_verified": compact_verified,
        "min_holdout_resolved_episodes": variant.get("resolved", 0) >= min_episodes,
        "min_holdout_windows": variant.get("windows", 0) >= min_windows,
        "target_rate_at_least_50pct": (variant.get("target_rate") or -1.0) >= 0.50,
        "wilson_lower_above_45pct": (variant.get("wilson_lower_95") or -1.0) > 0.45,
        "absolute_precision_improvement": improvement is not None and improvement >= min_absolute_improvement,
        "relative_precision_improvement": relative is not None and relative >= min_relative_improvement,
        "actual_ev_positive": (variant.get("actual_ev") or -1.0) > 0.0,
        "conservative_ev_positive": (variant.get("conservative_ev") or -1.0) > 0.0,
        "paired_ev_lower_bound_positive": (variant.get("paired_ev_lower_bound") or -1.0) > 0.0,
        "ece_at_most_005": (variant.get("ece") or 1.0) <= 0.05,
    }
    return {
        "status": "high_quality" if all(checks.values()) else "unconfirmed",
        "checks": checks,
        "improvement_vs_champion": improvement,
        "relative_improvement_vs_champion": relative,
        "criteria": {
            "min_holdout_episodes": min_episodes,
            "min_holdout_windows": min_windows,
            "min_relative_improvement": min_relative_improvement,
            "min_absolute_improvement": min_absolute_improvement,
        },
    }


def run_pattern_research(
    frame: pd.DataFrame,
    *,
    source_provenance: Mapping[str, Any] | None = None,
    thresholds: Sequence[float] = DEFAULT_THRESHOLDS,
    n_patterns: int = 5,
    random_state: int = 42,
    purge_hours: int = SPEC.horizon_hours,
    min_holdout_episodes: int = 100,
    min_holdout_windows: int = 3,
    min_pattern_policy_resolved: int = 30,
    min_relative_improvement: float = 0.10,
    min_absolute_improvement: float = 0.05,
) -> tuple[dict[str, Any], PatternModel]:
    """Fit on development/policy and evaluate all thresholds once on holdout."""

    if len(thresholds) != 5:
        raise ValueError("exactly five thresholds must be evaluated independently")
    thresholds = tuple(float(value) for value in thresholds)
    if any(not 0 < value < 1 for value in thresholds):
        raise ValueError("thresholds must be in (0, 1)")
    if min_pattern_policy_resolved < 1:
        raise ValueError("min_pattern_policy_resolved must be positive")
    frame = frame.copy()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True, errors="coerce")
    frame = frame[frame["feature_time"].notna()].sort_values("feature_time").reset_index(drop=True)
    if "symbol" not in frame:
        frame["symbol"] = "__all__"
    frame["episode_id"] = _episode_ids(frame)
    supplied_provenance = dict(source_provenance or {})
    compact_verified = _compact_provenance_verified(supplied_provenance)
    raw_label_kind = str(supplied_provenance.get("label_kind", "unknown"))
    label_kind = "compact_policy" if compact_verified else (
        "diagnostic_entry1" if raw_label_kind == "diagnostic_entry1" else "unsupported"
    )
    split = common_temporal_split(frame, purge_hours=purge_hours)
    train = split["train"]
    policy = split["policy"]
    heldout = split["heldout"]
    assert isinstance(train, pd.DataFrame)
    assert isinstance(policy, pd.DataFrame)
    assert isinstance(heldout, pd.DataFrame)
    if train.empty or policy.empty or heldout.empty:
        raise ValueError("common temporal split lacks train, policy, or heldout rows")
    model = fit_pattern_model(
        train,
        n_patterns=n_patterns,
        random_state=random_state,
        source_label_kind=label_kind,
        evidence_status="compact_verified" if compact_verified else "exploratory_legacy_label",
    )
    scores = _pattern_scores(policy, model)
    pattern_support = _pattern_support(policy, model)
    heldout_results: list[dict[str, Any]] = []
    champion = _metric(heldout, champion_mask(heldout), label_kind=label_kind)
    for threshold in thresholds:
        # Every threshold is evaluated independently; no heldout row is used
        # to choose a winner.  A nearest-pattern policy score is learned only
        # from the policy partition.
        def threshold_mask(row: pd.Series) -> bool:
            classified = classify_snapshot(row.to_dict(), model)
            pattern_id = classified.get("pattern_id")
            return (
                bool(champion_mask(pd.DataFrame([row])).iloc[0])
                and classified.get("status") == "determined"
                and pattern_id != "unknown"
                and pattern_support.get(pattern_id, 0) >= min_pattern_policy_resolved
                and scores.get(pattern_id, 0.0) >= threshold
            )

        mask = heldout.apply(threshold_mask, axis=1) if not heldout.empty else pd.Series(dtype=bool, index=heldout.index)
        variant = _metric(heldout, mask, label_kind=label_kind)
        heldout_results.append(
            {
                "threshold": threshold,
                "variant_id": f"pattern_score_ge_{threshold:.2f}",
                "policy_pattern_scores": scores,
                "metrics": variant,
                "quality": _quality(
                    variant,
                    champion,
                    compact_verified=compact_verified,
                    min_episodes=min_holdout_episodes,
                    min_windows=min_holdout_windows,
                    min_relative_improvement=min_relative_improvement,
                    min_absolute_improvement=min_absolute_improvement,
                ),
            }
        )
    # Independently vary each of the five originally published conditions.  A
    # common holdout and fixed champion comparator make this an auditable
    # ablation, not a hidden replacement for the live gate.
    reference_score_column = next(
        (
            column
            for column in REFERENCE_SCORE_COLUMNS
            if column in heldout.columns
        ),
        None,
    )
    condition_results: list[dict[str, Any]] = []
    for condition, candidate_values in CONDITION_THRESHOLDS.items():
        variants: list[dict[str, Any]] = []
        for threshold in candidate_values:
            mask = _condition_mask(heldout, condition, threshold)
            metrics = _metric(heldout, mask, label_kind=label_kind)
            variants.append({
                "threshold": threshold,
                "metrics": metrics,
                "quality": _quality(
                    metrics,
                    champion,
                    compact_verified=compact_verified,
                    min_episodes=min_holdout_episodes,
                    min_windows=min_holdout_windows,
                    min_relative_improvement=min_relative_improvement,
                    min_absolute_improvement=min_absolute_improvement,
                ),
            })
        condition_results.append({
            "condition": condition,
            "locked_other_conditions": True,
            "exact_five_available": reference_score_column is not None,
            "reference_score_column": reference_score_column,
            "unavailable_reason": (
                None
                if reference_score_column is not None
                else "reference_score_not_recorded_in_common_cohort"
            ),
            "additional_fixed_policy_gates": ["funding_persistence_7d>0"],
            "min_pattern_policy_resolved": min_pattern_policy_resolved,
            "variants": variants,
        })
    report_contract = SPEC.version if compact_verified else (
        "diagnostic_entry1_legacy" if label_kind == "diagnostic_entry1" else "unknown_outcome_contract"
    )
    report = {
        "version": RESEARCH_REPORT_VERSION,
        "contract": report_contract,
        "contract_checksum": SPEC.checksum if compact_verified else None,
        "reference_contract": SPEC.version,
        "reference_contract_checksum": SPEC.checksum,
        "evidence_kind": "recycled_historical" if not compact_verified else "chronological_holdout",
        "evidence_status": "unsupported_compact_outcome" if not compact_verified else "heldout_only",
        "promotion_eligible": False,
        "selection": {
            "thresholds_evaluated_independently": list(thresholds),
            "threshold_selected_from_holdout": False,
            "pattern_fit_partition": "train_only",
            "threshold_score_fit_partition": "policy_only",
            "heldout_used_for_selection": False,
            "common_split_for_all_variants": True,
            "five_condition_contract": [
                "pump",
                "reversal",
                "funding_percentile",
                "funding_change_8h",
                "reference_score",
            ],
            "five_condition_reference_score_column": reference_score_column,
            "five_condition_available": reference_score_column is not None,
            "additional_fixed_policy_gates": ["funding_persistence_7d>0"],
            "min_pattern_policy_resolved": min_pattern_policy_resolved,
        },
        "provenance": dict(source_provenance or {}),
        "split": split["metadata"],
        "development": {
            "train_rows": int(len(train)),
            "policy_rows": int(len(policy)),
            "heldout_rows": int(len(heldout)),
            "pattern_count": len(model.pattern_ids),
            "pattern_ids": list(model.pattern_ids),
            "pattern_types": list(model.pattern_types),
            "pattern_counts": list(model.pattern_counts),
            "pattern_scores_fit_on_policy": scores,
            "pattern_resolved_support_fit_on_policy": pattern_support,
            "min_pattern_policy_resolved": min_pattern_policy_resolved,
        },
        "champion_baseline": champion,
        "heldout": heldout_results,
        "condition_ablation": condition_results,
        "limitations": [
            "Pattern similarity is descriptive and is not a probability of target success.",
            "Unknown or incomplete feature vectors are not treated as wins or losses.",
            "Historical source labels are diagnostic Entry-1 unless an explicit compact policy label is supplied.",
            "No automatic threshold/model promotion is performed.",
        ],
    }
    report["report_checksum"] = digest(report)
    return report, model


def run_pattern_research_from_db(
    dataset_db: Path,
    *,
    table: str = "distribution_v3_hourly_candidates",
    label_column: str | None = None,
    output_path: Path | None = None,
    artifact_path: Path | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    frame, provenance = load_research_frame(
        dataset_db,
        table=table,
        label_column=label_column,
    )
    report, model = run_pattern_research(frame, source_provenance=provenance, **kwargs)
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(canonical(report), encoding="utf-8")
    if artifact_path is not None:
        model.save(artifact_path)
    return report


__all__ = [
    "PATTERN_MODEL_VERSION",
    "RESEARCH_REPORT_VERSION",
    "DEFAULT_THRESHOLDS",
    "PatternModel",
    "canonical",
    "champion_mask",
    "classify_stage",
    "classify_snapshot",
    "common_temporal_split",
    "fit_pattern_model",
    "load_pattern_model",
    "load_research_frame",
    "run_pattern_research",
    "run_pattern_research_from_db",
]
