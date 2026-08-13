"""Generate a baseline report from materialized prediction evidence.

The previous version of this command emitted a set of hand-written numbers.
That is unsafe for a release gate: a report must be reproducible from the
snapshot, labels and predictions that produced it.  This command therefore
fails closed when evidence is missing or incomplete and never invents a
metric.

Example::

    python scripts/generate_baseline_report.py \
        --baseline-dir artifacts/baselines/sprint0_baseline \
        --predictions artifacts/research/predictions.parquet \
        --labels artifacts/research/labels.parquet

The prediction file must contain ``probability``, ``label_value``,
``threshold`` and ``model`` (``model`` may be omitted for a single-model
file).  ``event_id`` is required for event metrics; rows without a materialized
label are rejected instead of silently being counted as negatives.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from dao_vang.domain.time import system_now


class EvidenceError(ValueError):
    """Raised when a baseline cannot be reproduced from supplied evidence."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_reference(raw: str, baseline_dir: Path) -> Path:
    """Resolve manifest paths from repo root or the baseline folder."""
    reference = Path(raw)
    if reference.is_absolute():
        return reference
    candidates = [Path.cwd() / reference, baseline_dir / reference]
    parents = baseline_dir.resolve().parents
    if len(parents) >= 3:
        candidates.append(parents[2] / reference)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _read_table(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.is_file():
        raise EvidenceError(f"Evidence file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=suffix != ".json")
    if suffix == ".csv":
        return pd.read_csv(path)
    raise EvidenceError(
        f"Unsupported evidence format {suffix!r}; use CSV, Parquet or JSON"
    )


def _require_columns(frame: pd.DataFrame, required: Iterable[str], name: str) -> None:
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise EvidenceError(f"{name} is missing required columns: {', '.join(missing)}")


def _normalise_predictions(
    predictions: pd.DataFrame, labels: pd.DataFrame | None
) -> pd.DataFrame:
    frame = predictions.copy()
    if "model" not in frame.columns:
        frame["model"] = "model"

    # A prediction artifact may carry labels after materialization, but a
    # separate labels artifact is also supported.  Never use an inner join
    # that would silently discard unresolved rows.
    if "label_value" not in frame.columns:
        if labels is None:
            raise EvidenceError(
                "Predictions must contain label_value or --labels must be supplied"
            )
        if "prediction_id" in frame.columns and "prediction_id" in labels.columns:
            _require_columns(labels, ["prediction_id", "label_value"], "labels")
            if labels["prediction_id"].duplicated().any():
                raise EvidenceError("labels contains duplicate prediction_id values")
            frame = frame.merge(
                labels[["prediction_id", "label_value"]],
                on="prediction_id",
                how="left",
                validate="one_to_one",
            )
        else:
            _require_columns(frame, ["symbol", "signal_time"], "predictions")
            _require_columns(labels, ["symbol", "signal_time", "label_value"], "labels")
            key = ["symbol", "signal_time"]
            if labels.duplicated(key).any():
                raise EvidenceError("labels contains duplicate symbol/signal_time keys")
            frame = frame.merge(
                labels[key + ["label_value"]],
                on=key,
                how="left",
                validate="one_to_one",
            )

    _require_columns(
        frame,
        ["probability", "label_value", "threshold", "model", "event_id"],
        "predictions",
    )
    if frame.empty:
        raise EvidenceError("Prediction evidence is empty")
    if frame["event_id"].notna().sum() == 0:
        raise EvidenceError("Prediction evidence has no materialized event_id values")
    if frame["label_value"].isna().any():
        n = int(frame["label_value"].isna().sum())
        raise EvidenceError(f"{n} predictions do not have materialized labels")
    frame["probability"] = pd.to_numeric(frame["probability"], errors="coerce")
    frame["threshold"] = pd.to_numeric(frame["threshold"], errors="coerce")
    frame["label_value"] = pd.to_numeric(frame["label_value"], errors="coerce")
    if frame[["probability", "threshold", "label_value"]].isna().any().any():
        raise EvidenceError("probability, threshold and label_value must be numeric")
    if ((frame["probability"] < 0) | (frame["probability"] > 1)).any():
        raise EvidenceError("probability values must be in [0, 1]")
    if ((frame["threshold"] < 0) | (frame["threshold"] > 1)).any():
        raise EvidenceError("threshold values must be in [0, 1]")
    if (~frame["label_value"].isin([0, 1])).any():
        raise EvidenceError("label_value must be binary 0/1")
    threshold_counts = frame.groupby("model")["threshold"].nunique()
    if (threshold_counts > 1).any():
        drifting = ", ".join(
            str(name) for name in threshold_counts[threshold_counts > 1].index
        )
        raise EvidenceError(f"threshold policy drift within model(s): {drifting}")
    return frame


def _binary_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    actual = frame["label_value"].astype(int).to_numpy()
    predicted = (
        frame["probability"].to_numpy() >= frame["threshold"].to_numpy()
    ).astype(int)
    tp = int(((predicted == 1) & (actual == 1)).sum())
    fp = int(((predicted == 1) & (actual == 0)).sum())
    fn = int(((predicted == 0) & (actual == 1)).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    result: dict[str, Any] = {
        "n_rows": int(len(frame)),
        "n_positive": int(actual.sum()),
        "n_predicted_positive": int(predicted.sum()),
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "brier": float(np.mean((frame["probability"].to_numpy() - actual) ** 2)),
    }
    if "event_id" in frame.columns:
        valid = frame[frame["event_id"].notna()].copy()
        if not valid.empty:
            # One alert and one outcome per event.  This prevents a sequence
            # of positive candles from inflating event-level precision.
            event = valid.groupby("event_id", sort=True).agg(
                label_value=("label_value", "max"),
                probability=("probability", "max"),
                threshold=("threshold", "max"),
            )
            event_pred = (event["probability"] >= event["threshold"]).astype(int)
            event_actual = event["label_value"].astype(int)
            etp = int(((event_pred == 1) & (event_actual == 1)).sum())
            efp = int(((event_pred == 1) & (event_actual == 0)).sum())
            efn = int(((event_pred == 0) & (event_actual == 1)).sum())
            result["event"] = {
                "n_events": int(len(event)),
                "precision": etp / (etp + efp) if etp + efp else 0.0,
                "recall": etp / (etp + efn) if etp + efn else 0.0,
            }
    if "lead_time_minutes" in frame.columns:
        lead = pd.to_numeric(frame["lead_time_minutes"], errors="coerce").dropna()
        if not lead.empty:
            result["lead_time_minutes"] = {
                "p25": float(lead.quantile(0.25)),
                "median": float(lead.quantile(0.50)),
                "p75": float(lead.quantile(0.75)),
            }
    return result


def build_report(
    baseline_dir: Path, predictions_path: Path, labels_path: Path | None = None
) -> dict[str, Any]:
    manifest_path = baseline_dir / "manifest.json"
    if not manifest_path.exists():
        raise EvidenceError(f"Baseline manifest does not exist: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("baseline_id"):
        raise EvidenceError("manifest.baseline_id is required")
    for key in ("commit_sha", "label_version", "feature_set_version"):
        if not manifest.get(key):
            raise EvidenceError(f"manifest.{key} is required for release provenance")
    dataset = manifest.get("datasets", {})
    for key in ("database_path", "database_sha256", "universe", "window"):
        if not dataset.get(key):
            raise EvidenceError(f"manifest.datasets.{key} is required")
    dependencies = manifest.get("dependencies", {})
    for key in ("lockfile", "lockfile_sha256"):
        if not dependencies.get(key):
            raise EvidenceError(f"manifest.dependencies.{key} is required")
    lockfile_path = _resolve_reference(str(dependencies["lockfile"]), baseline_dir)
    if not lockfile_path.exists():
        raise EvidenceError(f"Lockfile does not exist: {lockfile_path}")
    actual_lock_hash = sha256_file(lockfile_path)
    if actual_lock_hash != str(dependencies["lockfile_sha256"]).lower().removeprefix(
        "sha256:"
    ):
        raise EvidenceError("Lockfile checksum does not match manifest")
    dataset_path = _resolve_reference(str(dataset["database_path"]), baseline_dir)
    if not dataset_path.exists():
        raise EvidenceError(f"Snapshot database does not exist: {dataset_path}")
    expected_dataset_hash = dataset.get("database_sha256")
    actual_dataset_hash = sha256_file(dataset_path)
    if not expected_dataset_hash or expected_dataset_hash != actual_dataset_hash:
        raise EvidenceError("Snapshot checksum does not match manifest")

    predictions = _read_table(predictions_path)
    labels = _read_table(labels_path) if labels_path else None
    frame = _normalise_predictions(predictions, labels)
    models = {
        str(model): _binary_metrics(group.copy())
        for model, group in frame.groupby("model", sort=True)
    }
    return {
        "baseline_id": manifest["baseline_id"],
        "generated_at": system_now().isoformat(),
        "evidence": {
            "manifest_sha256": sha256_file(manifest_path),
            "snapshot_sha256": actual_dataset_hash,
            "predictions_sha256": sha256_file(predictions_path),
            "labels_sha256": sha256_file(labels_path) if labels_path else None,
            "predictions_path": str(predictions_path),
            "labels_path": str(labels_path) if labels_path else None,
        },
        "models": models,
        "n_rows": int(len(frame)),
        "dataset_window": dataset.get("window"),
        "commit_sha": manifest["commit_sha"],
        "label_version": manifest["label_version"],
        "feature_set_version": manifest["feature_set_version"],
        "lockfile_sha256": actual_lock_hash,
        "environment": manifest.get("environment", {}),
    }


def write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "baseline_report.json"
    markdown_path = output_dir / "baseline_report.md"
    if json_path.exists() or markdown_path.exists():
        raise EvidenceError(
            f"Baseline report already exists in {output_dir}; use a new baseline id"
        )
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        f"# Baseline Report: {report['baseline_id']}",
        f"Generated: {report['generated_at']}",
        f"Rows: {report['n_rows']}",
        "",
        "## Evidence",
    ]
    for key, value in report["evidence"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "## Models",
            "",
            "| Model | Rows | Precision | Recall | F1 | Brier |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for model, metrics in report["models"].items():
        lines.append(
            f"| {model} | {metrics['n_rows']} | {metrics['precision']:.6f} | "
            f"{metrics['recall']:.6f} | {metrics['f1']:.6f} | {metrics['brier']:.6f} |"
        )
    markdown_path.write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    output_dir = args.output_dir or args.baseline_dir
    try:
        report = build_report(args.baseline_dir, args.predictions, args.labels)
        write_report(report, output_dir)
    except (EvidenceError, OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    print(
        f"Created baseline report from {report['n_rows']} materialized rows "
        f"at {output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
