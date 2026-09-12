"""Fail-closed evidence contract for independent frozen-model forward tests.

The legacy evaluator is retained for historical experiments. This module is
the release-facing path: it starts no earlier than the model freeze time,
verifies the exact model and calibrator, applies a fingerprinted universe
policy, groups correlated rows into events, and withholds performance metrics
until every pre-declared sample gate passes.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, cast

import numpy as np
import pandas as pd

from dao_vang.config.settings import ThresholdPolicy
from dao_vang.domain.time import system_now
from dao_vang.experiments.batch_evaluator import score_snapshot_batch
from dao_vang.experiments.forward_test import load_frozen_model

PROTOCOL_SCHEMA_VERSION = "forward_evidence_v1"
SUPPORTED_UNIVERSE_MODES = {"all_scored_rows", "explicit_symbols"}


@dataclass(frozen=True)
class ForwardTestProtocol:
    """Pre-declared controls that make a forward-test run auditable."""

    schema_version: str
    model_id: str
    evaluation_start: str
    evaluation_end: str | None
    cutoff_policy: str
    universe_policy: dict[str, Any]
    label_version: str
    label_horizon_hours: int
    event_gap_minutes: int
    min_evaluated_rows: int
    min_positive_events: int
    min_predicted_events: int
    min_evaluation_days: float
    expected_model_sha256: str
    expected_calibrator_sha256: str
    expected_metadata_sha256: str
    external_api_cost_per_1000_rows_usd: float
    compute_cost_per_hour_usd: float | None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> "ForwardTestProtocol":
        protocol = cls(
            schema_version=str(payload.get("schema_version") or ""),
            model_id=str(payload.get("model_id") or ""),
            evaluation_start=str(payload.get("evaluation_start") or ""),
            evaluation_end=(
                str(payload["evaluation_end"])
                if payload.get("evaluation_end")
                else None
            ),
            cutoff_policy=str(payload.get("cutoff_policy") or ""),
            universe_policy=dict(payload.get("universe_policy") or {}),
            label_version=str(payload.get("label_version") or ""),
            label_horizon_hours=int(payload.get("label_horizon_hours") or 0),
            event_gap_minutes=int(payload.get("event_gap_minutes") or 0),
            min_evaluated_rows=int(payload.get("min_evaluated_rows") or 0),
            min_positive_events=int(payload.get("min_positive_events") or 0),
            min_predicted_events=int(payload.get("min_predicted_events") or 0),
            min_evaluation_days=float(payload.get("min_evaluation_days") or 0.0),
            expected_model_sha256=str(payload.get("expected_model_sha256") or ""),
            expected_calibrator_sha256=str(
                payload.get("expected_calibrator_sha256") or ""
            ),
            expected_metadata_sha256=str(
                payload.get("expected_metadata_sha256") or ""
            ),
            external_api_cost_per_1000_rows_usd=float(
                payload.get("external_api_cost_per_1000_rows_usd") or 0.0
            ),
            compute_cost_per_hour_usd=(
                float(payload["compute_cost_per_hour_usd"])
                if payload.get("compute_cost_per_hour_usd") is not None
                else None
            ),
        )
        protocol.validate()
        return protocol

    def validate(self) -> None:
        if self.schema_version != PROTOCOL_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported forward-test protocol: {self.schema_version}"
            )
        if not self.model_id:
            raise ValueError("Forward-test protocol must lock model_id")
        _utc_timestamp(self.evaluation_start)
        if self.evaluation_end is not None:
            if _utc_timestamp(self.evaluation_end) <= _utc_timestamp(
                self.evaluation_start
            ):
                raise ValueError("evaluation_end must be after evaluation_start")
        if self.cutoff_policy != "max_train_cutoff_and_freeze_time":
            raise ValueError("cutoff_policy must fail closed at model freeze time")
        universe_mode = str(self.universe_policy.get("mode") or "")
        if universe_mode not in SUPPORTED_UNIVERSE_MODES:
            raise ValueError(f"Unsupported universe mode: {universe_mode}")
        if universe_mode == "explicit_symbols":
            symbols = self.universe_policy.get("symbols")
            if not isinstance(symbols, list) or not symbols:
                raise ValueError("explicit_symbols universe requires symbols")
            normalized_symbols = {
                str(symbol).upper().strip()
                for symbol in symbols
                if str(symbol).strip()
            }
            if not normalized_symbols:
                raise ValueError(
                    "explicit_symbols universe requires non-empty symbols"
                )
        if not self.label_version or self.label_horizon_hours <= 0:
            raise ValueError("Forward-test label contract is incomplete")
        for name, value in (
            ("event_gap_minutes", self.event_gap_minutes),
            ("min_evaluated_rows", self.min_evaluated_rows),
            ("min_positive_events", self.min_positive_events),
            ("min_predicted_events", self.min_predicted_events),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if self.min_evaluation_days <= 0:
            raise ValueError("min_evaluation_days must be positive")
        for name, value in (
            ("expected_model_sha256", self.expected_model_sha256),
            ("expected_calibrator_sha256", self.expected_calibrator_sha256),
            ("expected_metadata_sha256", self.expected_metadata_sha256),
        ):
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{name} must be a lowercase SHA-256 digest")
        if self.external_api_cost_per_1000_rows_usd < 0:
            raise ValueError("external API cost cannot be negative")
        if (
            self.compute_cost_per_hour_usd is not None
            and self.compute_cost_per_hour_usd < 0
        ):
            raise ValueError("compute cost cannot be negative")

    @property
    def fingerprint(self) -> str:
        canonical = json.dumps(
            asdict(self),
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()


def load_forward_test_protocol(path: Path) -> ForwardTestProtocol:
    """Load and validate an immutable JSON protocol manifest."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Forward-test protocol root must be an object")
    return ForwardTestProtocol.from_mapping(payload)


def _utc_timestamp(value: Any) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if not isinstance(timestamp, pd.Timestamp):
        raise ValueError(f"Invalid timestamp: {value}")
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_metadata_sha256(path: Path) -> str:
    """Hash metadata semantics independently of JSON whitespace/EOL style."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _dataset_fingerprint(frame: pd.DataFrame, feature_cols: list[str]) -> str:
    columns = ["symbol", "feature_time", "is_distribution", *feature_cols]
    normalized = frame.loc[:, columns].copy()
    normalized["feature_time"] = normalized["feature_time"].astype(str)
    canonical_csv = normalized.to_csv(
        index=False,
        lineterminator="\n",
        float_format="%.17g",
    )
    return hashlib.sha256(canonical_csv.encode("utf-8")).hexdigest()


def _event_groups(
    symbols: list[str],
    timestamps: list[pd.Timestamp],
    active: np.ndarray,
    gap_minutes: int,
) -> list[list[int]]:
    positions: dict[str, list[int]] = defaultdict(list)
    for index, enabled in enumerate(active.tolist()):
        if enabled:
            positions[symbols[index]].append(index)

    max_gap = pd.Timedelta(minutes=gap_minutes)
    groups: list[list[int]] = []
    for symbol in sorted(positions):
        symbol_positions = sorted(
            positions[symbol],
            key=lambda position: timestamps[position],
        )
        current: list[int] = []
        previous_time: pd.Timestamp | None = None
        for position in symbol_positions:
            timestamp = timestamps[position]
            if (
                current
                and previous_time is not None
                and timestamp - previous_time > max_gap
            ):
                groups.append(current)
                current = []
            current.append(position)
            previous_time = timestamp
        if current:
            groups.append(current)
    return groups


def _bundle_evidence(
    protocol: ForwardTestProtocol,
    artifact_dir: Path,
) -> tuple[dict[str, Any], Any]:
    info = load_frozen_model(protocol.model_id, artifact_dir)
    actual_model = _sha256(info.model_path) if info.model_path.is_file() else None
    actual_calibrator = (
        _sha256(info.calibrator_path)
        if info.calibrator_path is not None and info.calibrator_path.is_file()
        else None
    )
    actual_metadata = canonical_metadata_sha256(info.metadata_path)
    metadata_checksums = info.checksums or {}
    checks = {
        "model_matches_protocol": actual_model == protocol.expected_model_sha256,
        "calibrator_matches_protocol": (
            actual_calibrator == protocol.expected_calibrator_sha256
        ),
        "metadata_matches_protocol": (
            actual_metadata == protocol.expected_metadata_sha256
        ),
        "model_matches_metadata": (
            actual_model == metadata_checksums.get("model_sha256")
        ),
        "calibrator_matches_metadata": (
            actual_calibrator == metadata_checksums.get("calibrator_sha256")
        ),
    }
    evidence = {
        "verified": all(checks.values()),
        "checks": checks,
        "model_sha256": actual_model,
        "calibrator_sha256": actual_calibrator,
        "metadata_sha256": actual_metadata,
        "metadata_sha256_algorithm": "canonical_json_sha256_v1",
        "calibrator_id": info.calibrator_id,
    }
    return evidence, info


def _base_report(
    protocol: ForwardTestProtocol,
    as_of: pd.Timestamp,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "model_id": protocol.model_id,
        "protocol_fingerprint": protocol.fingerprint,
        "evaluated_as_of": as_of.isoformat(),
        "protocol": asdict(protocol),
        "bundle": bundle,
        "metrics": None,
    }


def evaluate_forward_evidence(
    model_id: str,
    df: pd.DataFrame,
    protocol: ForwardTestProtocol,
    artifact_dir: Path = Path("artifacts"),
    as_of: Any | None = None,
) -> dict[str, Any]:
    """Evaluate one immutable forward window and withhold weak metrics."""

    protocol.validate()
    as_of_timestamp = _utc_timestamp(as_of if as_of is not None else system_now())

    if model_id != protocol.model_id:
        return {
            **_base_report(protocol, as_of_timestamp, {}),
            "status": "protocol_mismatch",
            "message": "Requested model does not match the locked protocol model.",
        }

    try:
        bundle, info = _bundle_evidence(protocol, artifact_dir)
    except (FileNotFoundError, OSError, KeyError, ValueError) as exc:
        return {
            **_base_report(protocol, as_of_timestamp, {}),
            "status": "invalid_bundle",
            "message": f"Frozen bundle could not be verified: {type(exc).__name__}",
        }
    if not bundle["verified"]:
        return {
            **_base_report(protocol, as_of_timestamp, bundle),
            "status": "invalid_bundle",
            "message": "Model or calibrator checksum does not match the protocol.",
        }

    required_columns = {"symbol", "feature_time", "is_distribution"}
    missing_columns = sorted(required_columns.difference(df.columns))
    if missing_columns:
        return {
            **_base_report(protocol, as_of_timestamp, bundle),
            "status": "invalid_dataset",
            "message": f"Missing required columns: {','.join(missing_columns)}",
        }

    evaluation_start = _utc_timestamp(protocol.evaluation_start)
    train_cutoff = _utc_timestamp(info.train_cutoff)
    freeze_time = _utc_timestamp(info.freeze_time)
    locked_cutoff = max(train_cutoff, freeze_time)
    cutoff_verified = evaluation_start >= locked_cutoff
    if not cutoff_verified:
        return {
            **_base_report(protocol, as_of_timestamp, bundle),
            "status": "invalid_protocol",
            "message": (
                "evaluation_start must be no earlier than both train_cutoff "
                "and freeze_time."
            ),
            "window": {
                "train_cutoff": train_cutoff.isoformat(),
                "freeze_time": freeze_time.isoformat(),
                "evaluation_start": evaluation_start.isoformat(),
            },
        }

    maturity_cutoff = as_of_timestamp - pd.Timedelta(
        hours=protocol.label_horizon_hours
    )
    protocol_end = (
        _utc_timestamp(protocol.evaluation_end)
        if protocol.evaluation_end is not None
        else maturity_cutoff
    )
    evaluation_end = min(protocol_end, maturity_cutoff)

    work = df.copy()
    work["symbol"] = work["symbol"].astype(str).str.upper().str.strip()
    work["feature_time"] = pd.to_datetime(
        work["feature_time"],
        utc=True,
        errors="coerce",
    )
    work["is_distribution"] = pd.to_numeric(
        work["is_distribution"],
        errors="coerce",
    )
    n_source_rows = len(work)
    valid_base = (
        work["feature_time"].notna()
        & work["is_distribution"].isin([0, 1])
        & work["symbol"].ne("")
    )
    work = work.loc[valid_base].copy()
    work = work.loc[
        (work["feature_time"] > evaluation_start)
        & (work["feature_time"] <= evaluation_end)
    ].copy()

    universe_mode = str(protocol.universe_policy["mode"])
    n_out_of_universe_rows = 0
    if universe_mode == "explicit_symbols":
        allowed_symbols = {
            str(symbol).upper().strip()
            for symbol in protocol.universe_policy["symbols"]
            if str(symbol).strip()
        }
        in_universe = work["symbol"].isin(allowed_symbols)
        n_out_of_universe_rows = int((~in_universe).sum())
        work = work.loc[in_universe].copy()

    label_versions = (
        {str(value) for value in work["label_version"].dropna().tolist()}
        if "label_version" in work.columns
        else set()
    )
    label_horizons: set[int] = set()
    if "horizon_hours" in work.columns:
        numeric_horizons = cast(
            pd.Series,
            pd.to_numeric(
                work["horizon_hours"],
                errors="coerce",
            ),
        )
        label_horizons = {
            int(value)
            for value in numeric_horizons.dropna().tolist()
        }
    label_contract_verified = (
        label_versions == {protocol.label_version}
        and label_horizons == {protocol.label_horizon_hours}
    )

    duplicate_mask = work.duplicated(
        subset=["symbol", "feature_time"],
        keep=False,
    )
    n_duplicate_rows = int(duplicate_mask.sum())
    if n_duplicate_rows:
        return {
            **_base_report(protocol, as_of_timestamp, bundle),
            "status": "invalid_dataset",
            "message": "Duplicate symbol/feature_time rows would bias the evaluation.",
            "counts": {
                "source_rows": n_source_rows,
                "duplicate_rows": n_duplicate_rows,
            },
        }

    work = work.sort_values(["symbol", "feature_time"]).reset_index(drop=True)
    n_forward_rows = len(work)
    if n_forward_rows == 0:
        return {
            **_base_report(protocol, as_of_timestamp, bundle),
            "status": "no_forward_data",
            "message": "No mature labeled rows exist in the locked forward window.",
            "window": {
                "evaluation_start": evaluation_start.isoformat(),
                "evaluation_end": evaluation_end.isoformat(),
                "label_maturity_cutoff": maturity_cutoff.isoformat(),
            },
            "counts": {
                "source_rows": n_source_rows,
                "forward_rows": 0,
                "out_of_universe_rows": n_out_of_universe_rows,
            },
        }

    safe_policy = ThresholdPolicy(
        high_confidence_min_prob=float(info.threshold),
        watch_min_prob=min(0.10, float(info.threshold) * 0.5),
    )
    started_at = perf_counter()
    try:
        scored = score_snapshot_batch(work, info, safe_policy).reset_index(drop=True)
    except Exception as exc:
        return {
            **_base_report(protocol, as_of_timestamp, bundle),
            "status": "inference_error",
            "message": f"Verified batch inference failed: {type(exc).__name__}",
        }
    elapsed_seconds = perf_counter() - started_at

    usable_mask = scored["is_usable"].to_numpy(dtype=bool)
    excluded_reasons = {
        str(reason): int(count)
        for reason, count in scored.loc[~usable_mask, "reason"]
        .value_counts()
        .to_dict()
        .items()
    }
    n_evaluated = int(usable_mask.sum())
    n_excluded = n_forward_rows - n_evaluated
    if n_evaluated == 0:
        return {
            **_base_report(protocol, as_of_timestamp, bundle),
            "status": "quality_failed",
            "message": "No usable rows remained after fail-closed inference checks.",
            "counts": {
                "source_rows": n_source_rows,
                "forward_rows": n_forward_rows,
                "evaluated_rows": 0,
                "excluded_rows": n_excluded,
            },
            "exclusion_reasons": excluded_reasons,
        }

    evaluated = work.loc[usable_mask].reset_index(drop=True)
    probabilities = scored.loc[
        usable_mask,
        "calibrated_probability",
    ].to_numpy(dtype=float)
    y_true = evaluated["is_distribution"].to_numpy(dtype=int)
    threshold = float(scored.loc[usable_mask, "threshold"].iloc[0])
    y_pred = probabilities >= threshold
    timestamps = [
        _utc_timestamp(value) for value in evaluated["feature_time"].tolist()
    ]
    symbols = [str(value) for value in evaluated["symbol"].tolist()]

    truth_events = _event_groups(
        symbols,
        timestamps,
        y_true.astype(bool),
        protocol.event_gap_minutes,
    )
    predicted_events = _event_groups(
        symbols,
        timestamps,
        y_pred,
        protocol.event_gap_minutes,
    )
    predicted_event_hits = sum(
        any(bool(y_true[position]) for position in event)
        for event in predicted_events
    )
    detected_truth_events = sum(
        any(bool(y_pred[position]) for position in event)
        for event in truth_events
    )

    observed_start = min(timestamps)
    observed_end = max(timestamps)
    observed_days = max(
        0.0,
        (observed_end - observed_start).total_seconds() / 86400.0,
    )
    universe_fingerprint = hashlib.sha256(
        json.dumps(
            protocol.universe_policy,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    observed_symbols = sorted(set(symbols))

    gate_values = {
        "bundle_verified": bool(bundle["verified"]),
        "cutoff_locked_after_freeze": cutoff_verified,
        "label_contract_verified": label_contract_verified,
        "universe_policy_locked": bool(universe_fingerprint),
        "minimum_evaluated_rows": n_evaluated >= protocol.min_evaluated_rows,
        "minimum_positive_events": (
            len(truth_events) >= protocol.min_positive_events
        ),
        "minimum_predicted_events": (
            len(predicted_events) >= protocol.min_predicted_events
        ),
        "minimum_evaluation_days": observed_days >= protocol.min_evaluation_days,
    }
    gates: dict[str, dict[str, bool | int | float]] = {
        name: {"passed": passed}
        for name, passed in gate_values.items()
    }
    gates["minimum_evaluated_rows"]["actual"] = n_evaluated
    gates["minimum_evaluated_rows"]["required"] = protocol.min_evaluated_rows
    gates["minimum_positive_events"]["actual"] = len(truth_events)
    gates["minimum_positive_events"]["required"] = protocol.min_positive_events
    gates["minimum_predicted_events"]["actual"] = len(predicted_events)
    gates["minimum_predicted_events"]["required"] = protocol.min_predicted_events
    gates["minimum_evaluation_days"]["actual"] = observed_days
    gates["minimum_evaluation_days"]["required"] = protocol.min_evaluation_days
    publish_metrics = all(gate_values.values())

    external_api_cost = (
        n_evaluated
        / 1000.0
        * protocol.external_api_cost_per_1000_rows_usd
    )
    compute_cost = (
        elapsed_seconds
        / 3600.0
        * protocol.compute_cost_per_hour_usd
        if protocol.compute_cost_per_hour_usd is not None
        else None
    )
    report = {
        **_base_report(protocol, as_of_timestamp, bundle),
        "status": "ok" if publish_metrics else "insufficient_evidence",
        "message": (
            "All pre-declared gates passed; protocol-scoped metrics are available."
            if publish_metrics
            else "Performance metrics are withheld until every evidence gate passes."
        ),
        "window": {
            "train_cutoff": train_cutoff.isoformat(),
            "freeze_time": freeze_time.isoformat(),
            "evaluation_start": evaluation_start.isoformat(),
            "evaluation_end": evaluation_end.isoformat(),
            "label_maturity_cutoff": maturity_cutoff.isoformat(),
            "observed_start": observed_start.isoformat(),
            "observed_end": observed_end.isoformat(),
            "observed_days": observed_days,
        },
        "universe": {
            "policy": protocol.universe_policy,
            "policy_fingerprint": universe_fingerprint,
            "observed_symbol_count": len(observed_symbols),
            "observed_symbols": observed_symbols,
        },
        "dataset": {
            "fingerprint_algorithm": "canonical_csv_sha256_v1",
            "fingerprint": _dataset_fingerprint(evaluated, info.feature_cols),
        },
        "counts": {
            "source_rows": n_source_rows,
            "forward_rows": n_forward_rows,
            "evaluated_rows": n_evaluated,
            "excluded_rows": n_excluded,
            "out_of_universe_rows": n_out_of_universe_rows,
            "positive_rows": int(y_true.sum()),
            "predicted_positive_rows": int(y_pred.sum()),
            "positive_events": len(truth_events),
            "predicted_events": len(predicted_events),
            "predicted_event_hits": predicted_event_hits,
            "detected_positive_events": detected_truth_events,
        },
        "exclusion_reasons": excluded_reasons,
        "gates": gates,
        "operational": {
            "inference_elapsed_seconds": elapsed_seconds,
            "inference_ms_per_1000_rows": (
                elapsed_seconds * 1_000_000.0 / n_evaluated
            ),
            "external_api_calls": 0,
            "external_api_cost_usd": external_api_cost,
            "compute_cost_usd": compute_cost,
            "compute_cost_status": (
                "metered"
                if protocol.compute_cost_per_hour_usd is not None
                else "not_metered"
            ),
        },
    }

    if publish_metrics:
        from sklearn.metrics import brier_score_loss, precision_score, recall_score

        report["metrics"] = {
            "event_precision": predicted_event_hits / len(predicted_events),
            "event_recall": detected_truth_events / len(truth_events),
            "row_precision": float(precision_score(y_true, y_pred)),
            "row_recall": float(recall_score(y_true, y_pred)),
            "brier": float(brier_score_loss(y_true, probabilities)),
            "threshold": threshold,
        }
    return report
