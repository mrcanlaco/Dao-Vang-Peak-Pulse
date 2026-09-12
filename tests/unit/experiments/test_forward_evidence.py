"""Evidence-contract tests for release-facing frozen-model forward evaluation."""

import json
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from dao_vang.experiments.forward_evidence import (
    ForwardTestProtocol,
    canonical_metadata_sha256,
    evaluate_forward_evidence,
    load_forward_test_protocol,
)
from dao_vang.experiments.forward_test import FrozenModelInfo, freeze_model


def _freeze_test_bundle(tmp_path: Path) -> FrozenModelInfo:
    features = pd.DataFrame(
        {
            "feature_a": [-3.0, -2.0, -1.0, 1.0, 2.0, 3.0] * 8,
            "feature_b": [0.0] * 48,
        }
    )
    labels = np.asarray([0, 0, 0, 1, 1, 1] * 8, dtype=int)
    model = LogisticRegression(random_state=42).fit(features, labels)
    raw_probabilities = model.predict_proba(features)[:, 1]
    calibrator = IsotonicRegression(out_of_bounds="clip").fit(
        raw_probabilities,
        labels,
    )
    return freeze_model(
        model=model,
        threshold=0.5,
        feature_cols=["feature_a", "feature_b"],
        config={"hypothesis_id": "forward-evidence-test"},
        train_cutoff=pd.Timestamp("2026-01-01T00:00:00Z"),
        calibrator=calibrator,
        label_spec={
            "version": "distribution_short_v1",
            "horizon_hours": 24,
        },
        artifact_dir=tmp_path,
    )


def _protocol(info: FrozenModelInfo) -> ForwardTestProtocol:
    return ForwardTestProtocol(
        schema_version="forward_evidence_v1",
        model_id=info.model_id,
        evaluation_start=info.freeze_time,
        evaluation_end=None,
        cutoff_policy="max_train_cutoff_and_freeze_time",
        universe_policy={
            "mode": "all_scored_rows",
            "source": "feature_results",
            "post_hoc_symbol_filtering": False,
        },
        label_version="distribution_short_v1",
        label_horizon_hours=24,
        event_gap_minutes=240,
        min_evaluated_rows=8,
        min_positive_events=4,
        min_predicted_events=4,
        min_evaluation_days=1.0,
        expected_model_sha256=info.checksums["model_sha256"],
        expected_calibrator_sha256=info.checksums["calibrator_sha256"],
        expected_metadata_sha256=canonical_metadata_sha256(info.metadata_path),
        external_api_cost_per_1000_rows_usd=0.0,
        compute_cost_per_hour_usd=None,
    )


def _forward_rows(info: FrozenModelInfo) -> tuple[pd.DataFrame, pd.Timestamp]:
    start = pd.Timestamp(info.freeze_time).tz_convert("UTC") + pd.Timedelta(hours=1)
    times = pd.date_range(start, periods=8, freq="6h")
    positives = np.asarray([0, 1, 0, 1, 0, 1, 0, 1], dtype=int)
    frame = pd.DataFrame(
        {
            "feature_time": times,
            "symbol": ["BTCUSDT"] * len(times),
            "feature_a": np.where(positives == 1, 3.0, -3.0),
            "feature_b": 0.0,
            "is_distribution": positives,
            "label_version": "distribution_short_v1",
            "horizon_hours": 24,
        }
    )
    return frame, times[-1] + pd.Timedelta(hours=25)


def test_protocol_round_trip_and_fingerprint(tmp_path: Path) -> None:
    info = _freeze_test_bundle(tmp_path)
    protocol = _protocol(info)
    path = tmp_path / "protocol.json"
    path.write_text(
        json.dumps(asdict(protocol)),
        encoding="utf-8",
    )

    loaded = load_forward_test_protocol(path)

    assert loaded == protocol
    assert loaded.fingerprint == protocol.fingerprint
    assert len(loaded.fingerprint) == 64

    metadata_crlf = tmp_path / "metadata-crlf.json"
    metadata_minified = tmp_path / "metadata-minified.json"
    metadata_crlf.write_text(
        '{\r\n  "b": 2,\r\n  "a": 1\r\n}\r\n',
        encoding="utf-8",
    )
    metadata_minified.write_text('{"a":1,"b":2}', encoding="utf-8")
    assert canonical_metadata_sha256(
        metadata_crlf
    ) == canonical_metadata_sha256(metadata_minified)


def test_metrics_publish_only_after_all_predeclared_gates_pass(
    tmp_path: Path,
) -> None:
    info = _freeze_test_bundle(tmp_path)
    protocol = _protocol(info)
    frame, as_of = _forward_rows(info)

    report = evaluate_forward_evidence(
        info.model_id,
        frame,
        protocol,
        artifact_dir=tmp_path,
        as_of=as_of,
    )

    assert report["status"] == "ok"
    assert report["bundle"]["verified"] is True
    assert all(gate["passed"] for gate in report["gates"].values())
    assert report["counts"]["evaluated_rows"] == 8
    assert report["counts"]["positive_events"] == 4
    assert report["counts"]["predicted_events"] == 4
    assert report["metrics"]["event_precision"] == 1.0
    assert report["metrics"]["event_recall"] == 1.0
    assert report["metrics"]["row_precision"] == 1.0
    assert report["metrics"]["row_recall"] == 1.0
    assert report["operational"]["external_api_cost_usd"] == 0.0
    assert report["operational"]["compute_cost_status"] == "not_metered"


def test_insufficient_sample_gate_withholds_all_performance_metrics(
    tmp_path: Path,
) -> None:
    info = _freeze_test_bundle(tmp_path)
    protocol = replace(_protocol(info), min_evaluated_rows=9)
    frame, as_of = _forward_rows(info)

    report = evaluate_forward_evidence(
        info.model_id,
        frame,
        protocol,
        artifact_dir=tmp_path,
        as_of=as_of,
    )

    assert report["status"] == "insufficient_evidence"
    assert report["metrics"] is None
    assert report["gates"]["minimum_evaluated_rows"] == {
        "passed": False,
        "actual": 8,
        "required": 9,
    }


def test_window_excludes_pre_freeze_and_immature_labels(tmp_path: Path) -> None:
    info = _freeze_test_bundle(tmp_path)
    protocol = _protocol(info)
    frame, as_of = _forward_rows(info)
    pre_freeze = frame.iloc[[0]].copy()
    pre_freeze["feature_time"] = (
        pd.Timestamp(info.freeze_time).tz_convert("UTC") - pd.Timedelta(hours=1)
    )
    immature = frame.iloc[[0]].copy()
    immature["feature_time"] = as_of - pd.Timedelta(hours=23)
    expanded = pd.concat([pre_freeze, frame, immature], ignore_index=True)

    report = evaluate_forward_evidence(
        info.model_id,
        expanded,
        protocol,
        artifact_dir=tmp_path,
        as_of=as_of,
    )

    assert report["status"] == "ok"
    assert report["counts"]["source_rows"] == 10
    assert report["counts"]["forward_rows"] == 8
    assert report["window"]["evaluation_start"] == pd.Timestamp(
        info.freeze_time
    ).tz_convert("UTC").isoformat()


def test_checksum_or_label_contract_failure_never_publishes_metrics(
    tmp_path: Path,
) -> None:
    info = _freeze_test_bundle(tmp_path)
    protocol = _protocol(info)
    frame, as_of = _forward_rows(info)

    bad_bundle = evaluate_forward_evidence(
        info.model_id,
        frame,
        replace(protocol, expected_model_sha256="0" * 64),
        artifact_dir=tmp_path,
        as_of=as_of,
    )
    assert bad_bundle["status"] == "invalid_bundle"
    assert bad_bundle["metrics"] is None

    original_metadata = info.metadata_path.read_text(encoding="utf-8")
    mutated_metadata = json.loads(original_metadata)
    mutated_metadata["threshold"] = 0.99
    info.metadata_path.write_text(
        json.dumps(mutated_metadata),
        encoding="utf-8",
    )
    bad_metadata = evaluate_forward_evidence(
        info.model_id,
        frame,
        protocol,
        artifact_dir=tmp_path,
        as_of=as_of,
    )
    assert bad_metadata["status"] == "invalid_bundle"
    assert (
        bad_metadata["bundle"]["checks"]["metadata_matches_protocol"]
        is False
    )
    assert bad_metadata["metrics"] is None
    info.metadata_path.write_text(original_metadata, encoding="utf-8")

    frame["label_version"] = "unlocked_label"
    bad_labels = evaluate_forward_evidence(
        info.model_id,
        frame,
        protocol,
        artifact_dir=tmp_path,
        as_of=as_of,
    )
    assert bad_labels["status"] == "insufficient_evidence"
    assert bad_labels["gates"]["label_contract_verified"]["passed"] is False
    assert bad_labels["metrics"] is None


def test_protocol_model_and_freeze_cutoff_mismatches_fail_closed(
    tmp_path: Path,
) -> None:
    info = _freeze_test_bundle(tmp_path)
    protocol = _protocol(info)
    frame, as_of = _forward_rows(info)

    wrong_model = evaluate_forward_evidence(
        "frozen_other",
        frame,
        protocol,
        artifact_dir=tmp_path,
        as_of=as_of,
    )
    assert wrong_model["status"] == "protocol_mismatch"
    assert wrong_model["metrics"] is None

    pre_freeze_protocol = replace(
        protocol,
        evaluation_start="2026-01-02T00:00:00Z",
    )
    invalid_cutoff = evaluate_forward_evidence(
        info.model_id,
        frame,
        pre_freeze_protocol,
        artifact_dir=tmp_path,
        as_of=as_of,
    )
    assert invalid_cutoff["status"] == "invalid_protocol"
    assert invalid_cutoff["metrics"] is None
