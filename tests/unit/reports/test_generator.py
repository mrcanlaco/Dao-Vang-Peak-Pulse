from dao_vang.reports.generator import generate_markdown_report


def test_generate_markdown_report():
    dummy_artifact = {
        "artifact_id": "exp_123",
        "created_at": "2023-01-01T00:00:00",
        "data": {
            "config": {
                "hypothesis_id": "HYP-1",
                "baseline_model": "logreg",
            },
            "results": {
                "aggregate": {"precision": 0.85, "recall": 0.60},
                "per_fold": [
                    {"fold_idx": 0, "metrics": {"precision": 0.9}},
                    {"fold_idx": 1, "metrics": {"precision": 0.8}},
                ],
            },
        },
    }

    md = generate_markdown_report(dummy_artifact)

    assert "# Experiment Report: exp_123" in md
    assert "**Hypothesis ID:** HYP-1" in md
    assert "- **precision:** 0.8500" in md
    assert "- **recall:** 0.6000" in md
    assert "### Fold 0" in md
    assert "- precision: 0.9000" in md
    assert "### Fold 1" in md
