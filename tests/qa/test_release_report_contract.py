from __future__ import annotations

import pandas as pd

from dao_vang.validation.report import build_release_report


def test_release_report_preserves_versioned_evidence_from_manifest() -> None:
    predictions = pd.DataFrame(
        [
            {
                "prediction_id": "p1",
                "probability": 0.8,
                "label_value": 1,
                "threshold": 0.6,
                "event_id": "event-1",
                "fold_idx": 0,
                "split": "test",
            },
            {
                "prediction_id": "p2",
                "probability": 0.2,
                "label_value": 0,
                "threshold": 0.6,
                "event_id": "event-2",
                "fold_idx": 0,
                "split": "test",
            },
        ]
    )
    baseline = predictions.assign(probability=0.5)
    report = build_release_report(
        predictions,
        model_id="candidate-v1",
        baseline_predictions=baseline,
        evidence={
            "dataset_sha256": "dataset",
            "commit_sha": "commit",
            "label_version": "label-v1",
            "feature_set_version": "features-v1",
            "lockfile_sha256": "lock",
            "threshold_policy_version": "threshold-v1",
            "split_version": "split-v1",
        },
    )
    assert report["gates"]["missing_evidence"] == []
    assert report["policy"]["threshold_policy_version"] == "threshold-v1"
    assert report["policy"]["split_version"] == "split-v1"
