"""Auditable, immutable research release reports.

The report builder is intentionally evidence-first: it accepts only
materialised out-of-sample predictions and labels, stores those predictions
by fold, and refuses to replace an existing report.  Missing provenance or
baseline evidence does not turn into a passing report; the gate evaluator
returns ``blocked`` and explains which evidence is absent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from dao_vang.domain.time import system_now
from dao_vang.validation.bootstrap import calculate_bootstrap_ci
from dao_vang.validation.metrics import (
    compute_event_metrics,
    compute_expected_calibration_error,
    compute_row_metrics,
    reliability_table,
)


class ReleaseReportError(ValueError):
    """Raised when release evidence is malformed or cannot be reproduced."""


@dataclass(frozen=True)
class ReleaseGateThresholds:
    """Research release KPI floors from the project plan."""

    precision_min: float = 0.35
    precision_ci_lower_min: float = 0.25
    event_recall_min: float = 0.20
    median_lead_time_min: float = 240.0
    ece_max: float = 0.05
    relative_precision_improvement_min: float = 0.20
    min_events: int = 50


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f"unsupported JSON value: {type(value)!r}")


def _canonical_frame(frame: pd.DataFrame) -> bytes:
    """Serialize rows deterministically for provenance/checksum purposes."""

    records = frame.copy()
    for column in records.columns:
        if pd.api.types.is_datetime64_any_dtype(records[column]):
            records[column] = records[column].map(
                lambda value: value.isoformat() if pd.notna(value) else None
            )
    records = records.where(pd.notna(records), None)
    rows = records.to_dict(orient="records")
    rows.sort(key=lambda item: str(item.get("prediction_id", item)))
    return json.dumps(
        rows, sort_keys=True, separators=(",", ":"), default=_json_default
    ).encode("utf-8")


def _as_frame(value: Any, name: str) -> pd.DataFrame:
    if isinstance(value, pd.DataFrame):
        frame = value.copy()
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        frame = pd.DataFrame(list(value))
    else:
        raise ReleaseReportError(f"{name} must be a pandas DataFrame or row sequence")
    if frame.empty:
        raise ReleaseReportError(f"{name} is empty; release evidence is unavailable")
    return frame


def _validate_predictions(
    frame: pd.DataFrame, name: str = "predictions"
) -> pd.DataFrame:
    required = {"probability", "label_value", "threshold", "event_id", "fold_idx"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ReleaseReportError(
            f"{name} is missing required columns: {', '.join(missing)}"
        )
    result = frame.copy()
    if "prediction_id" not in result.columns:
        result.insert(0, "prediction_id", [f"row-{i}" for i in range(len(result))])
    if result["prediction_id"].duplicated().any():
        raise ReleaseReportError(f"{name} contains duplicate prediction_id values")
    if "split" in result.columns:
        non_test = result["split"].notna() & (
            result["split"].astype(str).str.lower() != "test"
        )
        if non_test.any():
            raise ReleaseReportError(
                f"{name} contains non-test rows; release evaluation must use "
                "held-out test rows"
            )
    for column in ("probability", "threshold", "label_value"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    if result[["probability", "threshold", "label_value"]].isna().any().any():
        raise ReleaseReportError(
            f"{name} probability, threshold and label_value must be "
            "materialized numeric values"
        )
    if ((result["probability"] < 0) | (result["probability"] > 1)).any():
        raise ReleaseReportError(f"{name} probability values must be in [0, 1]")
    if ((result["threshold"] < 0) | (result["threshold"] > 1)).any():
        raise ReleaseReportError(f"{name} threshold values must be in [0, 1]")
    if (~result["label_value"].isin([0, 1])).any():
        raise ReleaseReportError(f"{name} label_value must be binary 0/1")
    # A policy may differ by explicitly versioned horizon, but it must never
    # drift inside one model/horizon/fold without a recorded policy version.
    group_columns = [
        column for column in ("model", "horizon_hours") if column in result
    ]
    if not group_columns:
        group_columns = ["fold_idx"]
    threshold_counts = result.groupby(group_columns, dropna=False)[
        "threshold"
    ].nunique()
    if (threshold_counts > 1).any():
        raise ReleaseReportError(
            "threshold policy drift detected within a model/horizon"
        )
    if result["event_id"].notna().sum() == 0:
        raise ReleaseReportError(f"{name} has no materialized event_id values")
    result["pred_value"] = (result["probability"] >= result["threshold"]).astype(int)
    return result


def _lead_summary(metrics: Mapping[str, Any]) -> dict[str, float | None]:
    value = metrics.get("lead_time_minutes", {})
    if isinstance(value, Mapping):
        return {
            key: (float(value[key]) if value.get(key) is not None else None)
            for key in ("p25", "median", "p75")
        }
    median = metrics.get("median_lead_time")
    return {"p25": None, "median": float(median) if median else None, "p75": None}


def _frame_metric_bundle(frame: pd.DataFrame) -> dict[str, Any]:
    threshold = float(frame["threshold"].iloc[0])
    row = compute_row_metrics(frame["label_value"], frame["probability"], threshold)
    event = compute_event_metrics(frame)
    ece = compute_expected_calibration_error(frame["label_value"], frame["probability"])
    return {
        "n_rows": int(len(frame)),
        "row": row,
        "event": event,
        "pr_auc": row["pr_auc"],
        "precision": row["precision"],
        "recall": row["recall"],
        "f1": row["f1"],
        "brier_score": row["brier_score"],
        "ece": ece,
        "expected_calibration_error": ece,
        "reliability": reliability_table(frame["label_value"], frame["probability"]),
        "lead_time_minutes": _lead_summary(event),
    }


def _event_precision_from_rows(actual: list[bool], predicted: list[bool]) -> float:
    tp = sum(bool(a) and bool(p) for a, p in zip(actual, predicted))
    fp = sum((not bool(a)) and bool(p) for a, p in zip(actual, predicted))
    return tp / (tp + fp) if tp + fp else 0.0


def _event_bootstrap(frame: pd.DataFrame, seed: int) -> dict[str, float | int | None]:
    """Bootstrap whole events, never individual candles."""

    event = frame.copy()
    event["_event_key"] = event["event_id"].astype(str)
    event.loc[event["event_id"].isna(), "_event_key"] = [
        f"__unresolved_{index}" for index in event.index[event["event_id"].isna()]
    ]
    event = event.groupby("_event_key", sort=True).agg(
        actual=("label_value", "max"), predicted=("pred_value", "max")
    )
    if len(event) < 2:
        return {
            "n_events": int(len(event)),
            "precision_ci_lower": None,
            "precision_ci_upper": None,
        }
    lower, upper = calculate_bootstrap_ci(
        event["actual"].astype(bool).tolist(),
        event["predicted"].astype(bool).tolist(),
        metric_fn=_event_precision_from_rows,
        seed=seed,
    )
    return {
        "n_events": int(len(event)),
        "precision_ci_lower": float(lower),
        "precision_ci_upper": float(upper),
    }


def _normalise_baselines(
    model: pd.DataFrame, baseline_predictions: Any | None
) -> dict[str, dict[str, Any]]:
    """Compute baseline metrics on exactly the same prediction IDs."""

    baseline_frames: dict[str, pd.DataFrame] = {}
    if baseline_predictions is not None:
        if isinstance(baseline_predictions, Mapping):
            for name, value in baseline_predictions.items():
                baseline_frames[str(name)] = _as_frame(value, f"baseline[{name}]")
        else:
            baseline_frames["baseline"] = _as_frame(
                baseline_predictions, "baseline_predictions"
            )
    for column in [
        column for column in model.columns if column.endswith("_probability")
    ]:
        name = column.removesuffix("_probability") or "baseline"
        threshold_column = f"{name}_threshold"
        if threshold_column not in model.columns:
            threshold_column = "threshold"
        baseline_frames[name] = pd.DataFrame(
            {
                "prediction_id": model["prediction_id"],
                "fold_idx": model["fold_idx"],
                "event_id": model["event_id"],
                "probability": model[column],
                "threshold": model[threshold_column],
                "label_value": model["label_value"],
            }
        )
    result: dict[str, dict[str, Any]] = {}
    model_ids = set(model["prediction_id"].astype(str))
    for name, frame in baseline_frames.items():
        if "prediction_id" not in frame.columns:
            raise ReleaseReportError(f"baseline[{name}] must contain prediction_id")
        if set(frame["prediction_id"].astype(str)) != model_ids:
            raise ReleaseReportError(
                f"baseline[{name}] rows do not match the model test prediction IDs"
            )
        checked = _validate_predictions(frame, f"baseline[{name}]")
        result[name] = _frame_metric_bundle(checked)
    return result


def _required_evidence(report: Mapping[str, Any]) -> list[str]:
    evidence = report.get("evidence", {})
    policy = report.get("policy", {})
    # Accept the manifest's conventional ``snapshot_sha256``/``database_sha256``
    # spellings while normalising the gate vocabulary to ``dataset_sha256``.
    if not evidence.get("dataset_sha256"):
        if evidence.get("snapshot_sha256"):
            evidence = {**evidence, "dataset_sha256": evidence["snapshot_sha256"]}
        elif evidence.get("database_sha256"):
            evidence = {**evidence, "dataset_sha256": evidence["database_sha256"]}
    if not evidence.get("threshold_policy_version"):
        evidence = {
            **evidence,
            "threshold_policy_version": policy.get("threshold_policy_version"),
        }
    if not evidence.get("split_version"):
        evidence = {**evidence, "split_version": policy.get("split_version")}
    required = (
        "predictions_sha256",
        "dataset_sha256",
        "commit_sha",
        "label_version",
        "feature_set_version",
        "lockfile_sha256",
        "threshold_policy_version",
        "split_version",
    )
    return [key for key in required if not evidence.get(key)]


def evaluate_release_gates(
    report: Mapping[str, Any], thresholds: ReleaseGateThresholds | None = None
) -> dict[str, Any]:
    """Evaluate G4/G5 and fail closed when evidence/KPIs are incomplete."""

    policy = thresholds or ReleaseGateThresholds()
    missing = _required_evidence(report)
    checks: dict[str, dict[str, Any]] = {}
    aggregate = report.get("aggregate", {})
    event = aggregate.get("event", {}) if isinstance(aggregate, Mapping) else {}
    ci = (
        aggregate.get("event_precision_ci", {})
        if isinstance(aggregate, Mapping)
        else {}
    )
    baselines = report.get("baselines", {})
    if not isinstance(baselines, Mapping) or not baselines:
        missing.append("baselines")

    def check(name: str, actual: Any, expected: Any, passed: bool, reason: str) -> None:
        checks[name] = {
            "passed": bool(passed),
            "actual": actual,
            "expected": expected,
            "reason": reason if passed else reason,
        }

    precision = aggregate.get("precision") if isinstance(aggregate, Mapping) else None
    if precision is None and isinstance(aggregate, Mapping):
        precision = aggregate.get("row", {}).get("precision")
    lower_ci = ci.get("lower") if isinstance(ci, Mapping) else None
    if lower_ci is None and isinstance(ci, Mapping):
        lower_ci = ci.get("precision_ci_lower")
    ece = aggregate.get("ece") if isinstance(aggregate, Mapping) else None
    if ece is None and isinstance(aggregate, Mapping):
        ece = aggregate.get("expected_calibration_error")
    lead = (
        aggregate.get("lead_time_minutes", {}) if isinstance(aggregate, Mapping) else {}
    )
    median_lead = lead.get("median") if isinstance(lead, Mapping) else None
    recall = event.get("event_recall") if isinstance(event, Mapping) else None
    pr_auc = aggregate.get("pr_auc") if isinstance(aggregate, Mapping) else None
    baseline_pr = [
        float(value.get("pr_auc"))
        for value in baselines.values()
        if isinstance(value, Mapping) and value.get("pr_auc") is not None
    ]
    baseline_precision = [
        float(value.get("precision"))
        for value in baselines.values()
        if isinstance(value, Mapping) and value.get("precision") is not None
    ]
    best_baseline_precision = max(baseline_precision) if baseline_precision else None
    relative_improvement = (
        (float(precision) - best_baseline_precision) / best_baseline_precision
        if best_baseline_precision not in (None, 0) and precision is not None
        else None
    )
    check(
        "pr_auc_beats_all_baselines",
        pr_auc,
        "> max baseline PR-AUC",
        pr_auc is not None and bool(baseline_pr) and float(pr_auc) > max(baseline_pr),
        "model PR-AUC must beat every baseline on identical test rows",
    )
    check(
        "relative_precision_improvement",
        relative_improvement,
        policy.relative_precision_improvement_min,
        relative_improvement is not None
        and relative_improvement >= policy.relative_precision_improvement_min,
        "precision improvement is measured against the best locked baseline",
    )
    check(
        "precision_floor",
        precision,
        policy.precision_min,
        precision is not None and float(precision) >= policy.precision_min,
        "high-confidence precision floor",
    )
    check(
        "precision_ci_lower_floor",
        lower_ci,
        policy.precision_ci_lower_min,
        lower_ci is not None and float(lower_ci) >= policy.precision_ci_lower_min,
        "event-bootstrap 95% CI lower bound",
    )
    check(
        "event_recall_floor",
        recall,
        policy.event_recall_min,
        recall is not None and float(recall) >= policy.event_recall_min,
        "event recall floor",
    )
    check(
        "median_lead_time_floor",
        median_lead,
        policy.median_lead_time_min,
        median_lead is not None and float(median_lead) >= policy.median_lead_time_min,
        "median lead time is measured from signal to first target touch",
    )
    check(
        "ece_ceiling",
        ece,
        policy.ece_max,
        ece is not None and float(ece) <= policy.ece_max,
        "out-of-sample ECE ceiling",
    )
    threshold_values = report.get("policy", {}).get("thresholds", [])
    check(
        "threshold_policy_locked",
        threshold_values,
        "one threshold per model/horizon",
        bool(threshold_values) and not report.get("policy", {}).get("drift", True),
        "threshold policy must be versioned and drift-free before test",
    )
    n_events = int(event.get("n_events", 0) or 0) if isinstance(event, Mapping) else 0
    check(
        "materialized_events",
        n_events,
        policy.min_events,
        n_events >= policy.min_events,
        "release evidence must contain enough materialized events",
    )
    failed = [name for name, value in checks.items() if not value["passed"]]
    status = "blocked" if missing else ("passed" if not failed else "failed")
    return {
        "status": status,
        "go": status == "passed",
        "missing_evidence": sorted(set(missing)),
        "failed_checks": failed,
        "checks": checks,
    }


def build_release_report(
    predictions: Any,
    *,
    model_id: str,
    baseline_predictions: Any | None = None,
    evidence: Mapping[str, Any] | None = None,
    threshold_policy_version: str | None = None,
    split_version: str | None = None,
    seed: int = 42,
) -> dict[str, Any]:
    """Build a release report from materialised fold predictions.

    No aggregate supplied by a caller is trusted; all metrics are recomputed
    from the rows that are stored in the report.
    """

    if not model_id:
        raise ReleaseReportError("model_id is required")
    frame = _validate_predictions(_as_frame(predictions, "predictions"))
    evidence_input = dict(evidence or {})
    if threshold_policy_version:
        policy_version = threshold_policy_version
    elif "threshold_policy_version" in frame.columns:
        values = frame["threshold_policy_version"].dropna().astype(str).unique()
        policy_version = values[0] if len(values) == 1 else None
    else:
        policy_version = evidence_input.get("threshold_policy_version")
    if "split_version" in frame.columns and split_version is None:
        values = frame["split_version"].dropna().astype(str).unique()
        split_version = values[0] if len(values) == 1 else None
    elif split_version is None:
        split_version = evidence_input.get("split_version")
    baseline_metrics = _normalise_baselines(frame, baseline_predictions)
    bundle = _frame_metric_bundle(frame)
    fold_reports: list[dict[str, Any]] = []
    predictions_by_fold: dict[str, list[dict[str, Any]]] = {}
    for fold_idx, fold in frame.groupby("fold_idx", sort=True):
        fold = fold.sort_values("prediction_id")
        fold_bundle = _frame_metric_bundle(fold)
        fold_rows = fold.drop(columns=["pred_value"], errors="ignore").to_dict(
            orient="records"
        )
        fold_key = str(fold_idx)
        predictions_by_fold[fold_key] = fold_rows
        fold_reports.append(
            {
                "fold_idx": fold_idx.item() if hasattr(fold_idx, "item") else fold_idx,
                "n_rows": int(len(fold)),
                "metrics": fold_bundle,
            }
        )
    event_ci = _event_bootstrap(frame, seed)
    aggregate = dict(bundle)
    aggregate["event_precision_ci"] = {
        "lower": event_ci.get("precision_ci_lower"),
        "upper": event_ci.get("precision_ci_upper"),
        "method": "event_bootstrap",
        "n_events": event_ci["n_events"],
    }
    aggregate["n_folds"] = int(frame["fold_idx"].nunique())
    aggregate["alert_per_day"] = None
    if "signal_time" in frame.columns:
        times = pd.to_datetime(frame["signal_time"], errors="coerce", utc=True).dropna()
        if not times.empty:
            days = max((times.max() - times.min()).total_seconds() / 86400.0, 1.0)
            aggregate["alert_per_day"] = float(frame["pred_value"].sum() / days)
    thresholds = sorted(float(value) for value in frame["threshold"].unique())
    evidence_out = evidence_input
    evidence_out["predictions_sha256"] = _sha256_bytes(_canonical_frame(frame))
    evidence_out["n_prediction_rows"] = int(len(frame))
    evidence_out["n_folds"] = int(frame["fold_idx"].nunique())
    evidence_out.setdefault("generated_at", system_now().isoformat())
    if baseline_predictions is not None:
        baseline_frame = (
            baseline_predictions
            if isinstance(baseline_predictions, pd.DataFrame)
            else pd.DataFrame(baseline_predictions)
        )
        evidence_out["baseline_predictions_sha256"] = _sha256_bytes(
            _canonical_frame(baseline_frame)
        )
    policy = {
        "threshold_policy_version": policy_version,
        "split_version": split_version,
        "thresholds": thresholds,
        "drift": len(thresholds) > 1
        and not {"model", "horizon_hours"}.issubset(frame.columns),
    }
    evidence_out["threshold_policy_version"] = policy_version
    evidence_out["split_version"] = split_version
    report: dict[str, Any] = {
        "schema_version": "release_report.v1",
        "status": "complete",
        "model_id": model_id,
        "evidence": evidence_out,
        "policy": policy,
        "aggregate": aggregate,
        "folds": fold_reports,
        "predictions_by_fold": predictions_by_fold,
        "baselines": baseline_metrics,
        "worst_fold": min(
            fold_reports,
            key=lambda item: item["metrics"].get("precision", 0.0),
        ),
    }
    report["gates"] = evaluate_release_gates(report)
    return report


def _report_markdown(report: Mapping[str, Any]) -> str:
    aggregate = report.get("aggregate", {})
    gates = report.get("gates", {})
    lines = [
        f"# Release Report: {report.get('model_id', 'UNKNOWN')}",
        "",
        f"Status: **{report.get('status', 'unknown')}**",
        f"Gate: **{gates.get('status', 'blocked')}**",
        "",
        "## Evidence",
    ]
    for key, value in report.get("evidence", {}).items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Aggregate metrics"])
    for key in (
        "precision",
        "recall",
        "pr_auc",
        "brier_score",
        "ece",
        "n_rows",
    ):
        if key in aggregate:
            lines.append(f"- {key}: {aggregate[key]}")
    lines.extend(["", "## Gate checks"])
    for name, check in gates.get("checks", {}).items():
        lines.append(
            f"- {'PASS' if check.get('passed') else 'FAIL'} {name}: "
            f"{check.get('actual')}"
        )
    lines.extend(["", "## Fold metrics"])
    for fold in report.get("folds", []):
        lines.append(f"### Fold {fold.get('fold_idx')}")
        metrics = fold.get("metrics", {})
        lines.append(f"- precision: {metrics.get('precision')}")
        lines.append(f"- recall: {metrics.get('recall')}")
        lines.append(f"- PR-AUC: {metrics.get('pr_auc')}")
    return "\n".join(lines) + "\n"


def write_release_report(report: Mapping[str, Any], out_dir: Path) -> tuple[Path, Path]:
    """Write JSON/Markdown exactly once; never overwrite an existing report."""

    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "release_report.json"
    markdown_path = out_dir / "release_report.md"
    checksum_path = out_dir / "release_report.sha256"
    if json_path.exists() or markdown_path.exists() or checksum_path.exists():
        raise ReleaseReportError(
            f"release report already exists in {out_dir}; choose a new run directory"
        )
    payload = json.dumps(
        report, sort_keys=True, indent=2, default=_json_default
    ).encode("utf-8")
    json_path.write_bytes(payload)
    markdown_path.write_text(_report_markdown(report), encoding="utf-8")
    checksum_path.write_text(_sha256_bytes(payload) + "\n", encoding="ascii")
    return json_path, markdown_path


def generate_release_report(
    model_id: str,
    fold_metrics: list[dict[str, Any]],
    aggregate_metrics: Mapping[str, Any],
    out_dir: Path,
) -> None:
    """Compatibility wrapper for the old API.

    The old API only supplied aggregate numbers, which are not acceptable for
    a release gate.  It now requires each fold to carry materialised
    ``predictions`` and intentionally ignores the caller's aggregate numbers.
    """

    rows: list[Mapping[str, Any]] = []
    for fold in fold_metrics:
        predictions = fold.get("predictions")
        if not predictions:
            raise ReleaseReportError(
                "fold_metrics must include materialized predictions; "
                "aggregate-only reports are blocked"
            )
        rows.extend(
            {
                **row,
                "fold_idx": row.get("fold_idx", fold.get("fold_idx")),
            }
            for row in predictions
        )
    report = build_release_report(rows, model_id=model_id)
    write_release_report(report, out_dir)
