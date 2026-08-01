from dao_vang.experiments.runner import ExperimentConfig, run_experiment


def test_experiment_runner():
    config = ExperimentConfig(
        hypothesis_id="HYP-001",
        dataset_version="v1.0",
        label_version="v1.0",
        feature_set_version="v1.0",
        baseline_model="logistic_regression",
        split_version="v1.0",
        seed=42,
        metrics=["precision", "brier_score"],
        code_commit="abcdef123",
    )

    result = run_experiment(config)

    assert result["status"] == "completed"
    assert result["config"]["hypothesis_id"] == "HYP-001"
    assert "per_fold" in result["results"]
    assert "aggregate" in result["results"]
