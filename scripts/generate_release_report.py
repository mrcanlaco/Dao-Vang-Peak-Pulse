"""Create an immutable Sprint 5 release report from materialised evidence.

The command intentionally fails closed.  It will not manufacture a baseline,
fill an unresolved label as a negative, or overwrite a report directory.

Example::

    python scripts/generate_release_report.py \
      --predictions artifacts/research/test_predictions.parquet \
      --baseline-predictions artifacts/research/heuristic_predictions.parquet \
      --manifest artifacts/baselines/sprint0_baseline/manifest.json \
      --model-id frozen_20260811_candidate \
      --output-dir artifacts/release/run_20260811
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pandas as pd

from dao_vang.validation.report import (
    ReleaseReportError,
    build_release_report,
    write_release_report,
)


def _read_table(path: Path) -> pd.DataFrame:
    if not path.exists() or not path.is_file():
        raise ReleaseReportError(f"evidence file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".json", ".jsonl", ".ndjson"}:
        return pd.read_json(path, lines=suffix != ".json")
    raise ReleaseReportError(f"unsupported evidence format: {suffix}")


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ReleaseReportError(f"manifest does not exist: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReleaseReportError(f"invalid manifest JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ReleaseReportError("manifest must be a JSON object")
    datasets = value.get("datasets", {})
    dependencies = value.get("dependencies", {})
    if not isinstance(datasets, dict) or not isinstance(dependencies, dict):
        raise ReleaseReportError("manifest datasets/dependencies must be objects")

    def resolve_reference(reference: Any) -> Path | None:
        if not isinstance(reference, str) or not reference:
            return None
        candidate = Path(reference)
        if candidate.is_absolute() and candidate.exists():
            return candidate
        candidates = [path.parent / candidate, Path(__file__).resolve().parents[1] / candidate]
        return next((item for item in candidates if item.exists() and item.is_file()), None)

    lockfile_ref = dependencies.get("lockfile") or dependencies.get("lockfile_path")
    lockfile_sha = dependencies.get("lockfile_sha256")
    if lockfile_sha:
        lockfile_path = resolve_reference(lockfile_ref)
        if lockfile_path is None:
            raise ReleaseReportError("manifest lockfile is missing")
        actual_lockfile_sha = _sha256(lockfile_path)
        if actual_lockfile_sha.lower() != str(lockfile_sha).lower().removeprefix("sha256:"):
            raise ReleaseReportError("manifest lockfile checksum mismatch")

    dataset_ref = datasets.get("database_path") or datasets.get("snapshot_path")
    dataset_sha = datasets.get("database_sha256") or datasets.get("snapshot_sha256")
    if dataset_sha and not dataset_ref:
        raise ReleaseReportError("manifest dataset snapshot path is missing")
    if dataset_sha and dataset_ref:
        dataset_path = resolve_reference(dataset_ref)
        if dataset_path is None:
            raise ReleaseReportError("manifest dataset snapshot is missing")
        actual_dataset_sha = _sha256(dataset_path)
        if actual_dataset_sha.lower() != str(dataset_sha).lower().removeprefix("sha256:"):
            raise ReleaseReportError("manifest dataset checksum mismatch")
    evidence = {
        "manifest_path": str(path),
        "manifest_sha256": _sha256(path),
        "dataset_sha256": datasets.get("database_sha256")
        or datasets.get("snapshot_sha256"),
        "commit_sha": value.get("commit_sha"),
        "label_version": value.get("label_version"),
        "feature_set_version": value.get("feature_set_version"),
        "lockfile_sha256": lockfile_sha,
    }
    return {key: value for key, value in evidence.items() if value not in (None, "")}


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _attach_labels(predictions: pd.DataFrame, labels: pd.DataFrame) -> pd.DataFrame:
    if "label_value" in predictions.columns:
        return predictions
    if "prediction_id" in predictions.columns and "prediction_id" in labels.columns:
        required = {"prediction_id", "label_value"}
        if not required.issubset(labels.columns):
            raise ReleaseReportError("labels missing prediction_id/label_value")
        if labels["prediction_id"].duplicated().any():
            raise ReleaseReportError("labels has duplicate prediction_id values")
        return predictions.merge(
            labels[["prediction_id", "label_value"]],
            on="prediction_id",
            how="left",
            validate="one_to_one",
        )
    keys = ["symbol", "signal_time"]
    if not set(keys).issubset(predictions.columns) or not set(
        keys + ["label_value"]
    ).issubset(labels.columns):
        raise ReleaseReportError(
            "labels must join by prediction_id or by symbol/signal_time"
        )
    if labels.duplicated(keys).any():
        raise ReleaseReportError("labels has duplicate symbol/signal_time keys")
    return predictions.merge(
        labels[keys + ["label_value"]], on=keys, how="left", validate="one_to_one"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--baseline-predictions", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--threshold-policy-version")
    parser.add_argument("--split-version")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    try:
        predictions = _read_table(args.predictions)
        if args.labels:
            predictions = _attach_labels(predictions, _read_table(args.labels))
        baseline = (
            _read_table(args.baseline_predictions)
            if args.baseline_predictions
            else None
        )
        evidence = _load_manifest(args.manifest)
        report = build_release_report(
            predictions,
            model_id=args.model_id,
            baseline_predictions=baseline,
            evidence=evidence,
            threshold_policy_version=args.threshold_policy_version,
            split_version=args.split_version,
            seed=args.seed,
        )
        paths = write_release_report(report, args.output_dir)
    except (ReleaseReportError, OSError, ValueError, TypeError) as exc:
        print(f"BLOCKED: {exc}")
        return 2
    print(f"Created immutable release report: {paths[0]}")
    print(f"Gate status: {report['gates']['status']}")
    return 0 if report["gates"]["status"] == "passed" else 3


if __name__ == "__main__":
    raise SystemExit(main())
