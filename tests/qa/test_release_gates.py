"""Regression tests for the non-negotiable release gates.

These tests intentionally exercise evidence contracts rather than model
quality on a convenient synthetic score.  A green unit-test suite cannot
substitute for a deterministic baseline, leakage-safe threshold selection or
an auditable frozen bundle.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from dao_vang.config.settings import ScoringConfig, ThresholdPolicy
from dao_vang.experiments.forward_test import freeze_model
from dao_vang.experiments.walk_forward import train_evaluate_logreg
from dao_vang.labels.engine_v1 import DistributionLabelEngineV1
from dao_vang.labels.specs.distribution_short_v1 import DistributionShortV1Spec
from dao_vang.scoring.btc_context import classify_btc
from dao_vang.scoring.frozen_inference import assess_snapshot_quality, score_snapshot
from dao_vang.validation.event_split import enforce_event_grouping_in_splits

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_baseline_inputs(tmp_path: Path) -> tuple[Path, Path]:
    baseline_dir = tmp_path / "baseline"
    baseline_dir.mkdir()
    snapshot = baseline_dir / "snapshot.bin"
    snapshot.write_bytes(b"immutable snapshot for test")
    manifest = {
        "baseline_id": "qa_baseline",
        "commit_sha": "qa-commit",
        "label_version": "distribution_short_v1",
        "feature_set_version": "qa_features_v1",
        "datasets": {
            "database_path": str(snapshot),
            "database_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
            "universe": "TEST",
            "window": "test",
        },
        "dependencies": {
            "lockfile": "uv.lock",
            "lockfile_sha256": hashlib.sha256(
                (REPO_ROOT / "uv.lock").read_bytes()
            ).hexdigest(),
        },
        "environment": {"timezone": "UTC", "seed": 7},
    }
    (baseline_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    predictions = tmp_path / "predictions.csv"
    pd.DataFrame(
        {
            "prediction_id": ["p1", "p2", "p3", "p4"],
            "model": ["heuristic", "heuristic", "logreg", "logreg"],
            "probability": [0.9, 0.1, 0.8, 0.2],
            "threshold": [0.5, 0.5, 0.5, 0.5],
            "label_value": [1, 0, 1, 1],
            "event_id": ["e1", "e2", "e1", "e3"],
            "lead_time_minutes": [60, 0, 90, 120],
        }
    ).to_csv(predictions, index=False)
    return baseline_dir, predictions


def test_baseline_generator_fails_closed_without_materialized_evidence(tmp_path: Path):
    """The command must never recreate the old hand-written report."""
    baseline_dir, _ = _write_baseline_inputs(tmp_path)
    report = baseline_dir / "baseline_report.json"
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "generate_baseline_report.py"),
            "--baseline-dir",
            str(baseline_dir),
            "--predictions",
            str(tmp_path / "does-not-exist.csv"),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert not report.exists(), "missing evidence must not create a report"


def test_baseline_report_metrics_are_computed_from_input(tmp_path: Path):
    """A valid evidence set yields provenance and data-derived metrics."""
    baseline_dir, predictions = _write_baseline_inputs(tmp_path)
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "generate_baseline_report",
        REPO_ROOT / "scripts" / "generate_baseline_report.py",
    )
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.build_report(baseline_dir, predictions)

    assert report["n_rows"] == 4
    assert report["evidence"]["predictions_sha256"]
    assert report["models"]["heuristic"]["precision"] == pytest.approx(1.0)
    assert report["models"]["logreg"]["recall"] == pytest.approx(0.5)
    assert report["models"]["logreg"]["event"]["n_events"] == 2
    output_dir = tmp_path / "report"
    module.write_report(report, output_dir)
    with pytest.raises(module.EvidenceError, match="already exists"):
        module.write_report(report, output_dir)


def test_baseline_rejects_manifest_lockfile_drift(tmp_path: Path):
    """A report cannot be reproduced when the dependency lock changed."""
    baseline_dir, predictions = _write_baseline_inputs(tmp_path)
    manifest_path = baseline_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["dependencies"]["lockfile_sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "generate_baseline_report",
        REPO_ROOT / "scripts" / "generate_baseline_report.py",
    )
    assert spec and spec.loader
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(module.EvidenceError, match="Lockfile checksum"):
        module.build_report(baseline_dir, predictions)


def test_threshold_selection_does_not_depend_on_test_labels():
    """Changing held-out labels must not change a frozen threshold.

    A threshold chosen on ``y_test`` is leakage even if aggregate metrics look
    plausible.  This behavioral check remains valid when implementation
    details of the validation split change.
    """
    x_train = pd.DataFrame({"x": [-3, -2, -1, -0.5, 0.5, 1, 2, 3]})
    y_train = pd.Series([0, 0, 0, 0, 1, 1, 1, 1])
    x_test = pd.DataFrame({"x": [-2, -1.5, -1, -0.5, 0, 0.5, 1, 1.5, 2, 2.5]})
    y_test = pd.Series([0, 0, 0, 0, 0, 1, 1, 1, 1, 1])
    leaked_labels = 1 - y_test

    first = train_evaluate_logreg(x_train, y_train, x_test, y_test)
    second = train_evaluate_logreg(x_train, y_train, x_test, leaked_labels)

    assert second["threshold"] == pytest.approx(first["threshold"])


@pytest.mark.parametrize(
    "function_name", ["train_evaluate_logreg", "train_evaluate_lightgbm"]
)
def test_threshold_helper_never_receives_test_labels(function_name: str):
    """Static guard against reintroducing test-fold threshold tuning."""
    import dao_vang.experiments.walk_forward as walk_forward

    if not hasattr(walk_forward, function_name):
        pytest.fail(f"missing canonical experiment function: {function_name}")
    tree = ast.parse(inspect.getsource(getattr(walk_forward, function_name)))
    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        fn = call.func
        name = (
            fn.id
            if isinstance(fn, ast.Name)
            else fn.attr
            if isinstance(fn, ast.Attribute)
            else ""
        )
        if name != "_precision_first_threshold":
            continue
        names = [node.id for node in ast.walk(call) if isinstance(node, ast.Name)]
        assert "y_test" not in names, f"{function_name} tunes threshold on test labels"


def _candles_with_full_horizon(
    *, quality: str = "valid", gap: bool = False, n: int = 73
) -> pd.DataFrame:
    base = datetime(2024, 1, 1)
    rows: list[dict[str, object]] = []
    current = base
    for i in range(n):
        rows.append(
            {
                "symbol": "BTC",
                "timestamp": current,
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "quality_status": quality,
            }
        )
        # Keep the series monotonic while inserting one genuine 20-minute gap.
        current += timedelta(minutes=20 if gap and i == 1 else 5)
    return pd.DataFrame(rows)


@pytest.mark.parametrize(
    ("quality", "gap", "reason"),
    [
        (
            "invalid",
            False,
            {"invalid_signal_quality", "quality_invalid", "invalid_quality"},
        ),
        ("valid", True, {"data_gap", "gap_exceeds_threshold"}),
    ],
)
def test_label_exclusions_are_null_not_negative(
    quality: str, gap: bool, reason: set[str]
):
    """Rows excluded for quality/gap must not enter training as label 0."""
    db = duckdb.connect(":memory:")
    try:
        db.register("candles_in", _candles_with_full_horizon(quality=quality, gap=gap))
        engine = DistributionLabelEngineV1(DistributionShortV1Spec(horizon_hours=6))
        engine.compute_all_to_table(db, "candles_in", "labels_out")
        row = db.execute(
            "SELECT label_value, exclusion_reason FROM labels_out "
            "WHERE signal_time = '2024-01-01 00:00:00'"
        ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] in reason
    finally:
        db.close()


def test_event_split_rejects_event_crossing_fold_boundary():
    """An event crossing train/test cannot silently leak into both folds."""
    db = duckdb.connect(":memory:")
    try:
        db.execute(
            "CREATE TABLE labels (event_id VARCHAR, signal_time TIMESTAMP, "
            "label_value INTEGER)"
        )
        db.executemany(
            "INSERT INTO labels VALUES (?, ?, ?)",
            [
                ("event-1", datetime(2024, 1, 1, 23, 55), 1),
                ("event-1", datetime(2024, 1, 2, 0, 5), 1),
                ("event-2", datetime(2024, 1, 2, 1, 0), 1),
            ],
        )
        result = enforce_event_grouping_in_splits(
            db,
            "labels",
            {
                "train": (datetime(2024, 1, 1), datetime(2024, 1, 2)),
                "test": (datetime(2024, 1, 2), datetime(2024, 1, 3)),
            },
        )
        assert result["ok"] is False
        assert result["n_dropped"] >= 1
        assert "event-1" in result["dropped_event_ids"]
    finally:
        db.close()


def test_frozen_bundle_contains_auditable_schema_and_checksums(tmp_path: Path):
    """A serving artifact must bind model, preprocessing and policy versions."""
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression().fit([[0.0], [1.0]], [0, 1])
    info = freeze_model(
        model=model,
        threshold=0.5,
        feature_cols=["feature_a"],
        config={"feature_set_version": "qa", "threshold_policy_version": "qa"},
        train_cutoff=datetime(2024, 1, 1),
        label_spec={"horizon_hours": 6, "version": "distribution_short_v1"},
        artifact_dir=tmp_path,
    )
    metadata = json.loads(info.metadata_path.read_text(encoding="utf-8"))
    assert metadata.get("schema_version") or metadata.get("artifact_schema_version")
    assert metadata["feature_cols"] == ["feature_a"]
    assert metadata.get("label_spec", {}).get("version")
    assert metadata.get("threshold_policy") or metadata.get("thresholds")
    assert metadata.get("calibrator_id") or metadata.get("calibrator")
    checksums = metadata.get("checksums") or metadata.get("artifact_checksums")
    assert isinstance(checksums, dict)
    model_hash = checksums.get("model_sha256") or checksums.get("model.joblib")
    assert model_hash == hashlib.sha256(info.model_path.read_bytes()).hexdigest()


def test_stale_or_invalid_snapshot_is_not_alertable(tmp_path: Path):
    """Freshness/quality failures must fail closed before model inference."""
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression().fit([[0.0], [1.0]], [0, 1])
    info = freeze_model(
        model=model,
        threshold=0.5,
        feature_cols=["feature_a"],
        config={},
        train_cutoff=datetime(2024, 1, 1),
        artifact_dir=tmp_path,
    )
    now = datetime(2024, 1, 1, 0, 20)
    stale_features = {
        "feature_a": 1.0,
        "feature_time": datetime(2024, 1, 1, 0, 9),
        "quality_status": "valid",
        "data_quality_score": 1.0,
    }
    quality = assess_snapshot_quality(
        stale_features,
        info,
        now=now,
        max_feature_age_minutes=10,
    )
    assert quality.status == "invalid"
    assert "feature_stale" in quality.reason_codes

    result = score_snapshot(
        symbol="BTCUSDT",
        feature_dict=stale_features,
        btc_context=classify_btc(0.0, 0.0, 0.0, ScoringConfig()),
        frozen_info=info,
        config=ScoringConfig(),
        threshold_policy=ThresholdPolicy(),
        quality=quality,
        now=now,
        max_feature_age_minutes=10,
    )
    assert result.risk_tier == "WAIT"
    assert result.calibrated_probability is None
    assert result.alertable is False


    invalid_quality = dict(stale_features)
    invalid_quality["feature_time"] = now
    invalid_quality["quality_status"] = "invalid"
    result = score_snapshot(
        symbol="BTCUSDT",
        feature_dict=invalid_quality,
        btc_context=classify_btc(0.0, 0.0, 0.0, ScoringConfig()),
        frozen_info=info,
        config=ScoringConfig(),
        threshold_policy=ThresholdPolicy(),
        now=now,
        max_feature_age_minutes=10,
    )
    assert result.risk_tier == "WAIT"
    assert result.calibrated_probability is None
    assert result.alertable is False


def test_identity_calibration_is_not_alertable(tmp_path: Path):
    """Raw model probabilities must not bypass the calibration gate."""
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression().fit([[0.0], [1.0]], [0, 1])
    info = freeze_model(
        model=model,
        threshold=0.5,
        feature_cols=["feature_a"],
        config={},
        train_cutoff=datetime(2024, 1, 1),
        artifact_dir=tmp_path,
    )
    result = score_snapshot(
        symbol="BTCUSDT",
        feature_dict={"feature_a": 1.0, "quality_status": "valid"},
        btc_context=classify_btc(0.0, 0.0, 0.0, ScoringConfig()),
        frozen_info=info,
        config=ScoringConfig(),
        threshold_policy=ThresholdPolicy(),
    )
    assert result.risk_tier == "WAIT"
    assert result.calibrated_probability is None
    assert "calibrator_unvalidated_identity" in result.quality.reason_codes


def test_bundle_checksum_mismatch_fails_closed(tmp_path: Path):
    """Serving must refuse a tampered model instead of scoring it."""
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression().fit([[0.0], [1.0]], [0, 1])
    info = freeze_model(
        model=model,
        threshold=0.5,
        feature_cols=["feature_a"],
        config={},
        train_cutoff=datetime(2024, 1, 1),
        artifact_dir=tmp_path,
    )
    info.model_path.write_bytes(info.model_path.read_bytes() + b"tamper")
    result = score_snapshot(
        symbol="BTCUSDT",
        feature_dict={"feature_a": 1.0, "quality_status": "valid"},
        btc_context=classify_btc(0.0, 0.0, 0.0, ScoringConfig()),
        frozen_info=info,
        config=ScoringConfig(),
        threshold_policy=ThresholdPolicy(),
    )
    assert result.risk_tier == "WAIT"
    assert result.calibrated_probability is None
    assert "model_checksum_mismatch" in result.quality.reason_codes
