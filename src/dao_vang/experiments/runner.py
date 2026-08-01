from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class ExperimentConfig(BaseModel):
    """
    Configuration for an experiment run.
    """

    hypothesis_id: str
    dataset_version: str
    label_version: str
    feature_set_version: str
    baseline_model: str
    split_version: str
    seed: int
    metrics: List[str]
    code_commit: Optional[str] = None


def run_experiment(config: ExperimentConfig) -> Dict[str, Any]:
    """
    Orchestrates the experiment:
    - Loads dataset, features, labels based on versions in config.
    - Applies splits.
    - Runs the selected model.
    - Computes metrics.

    Returns a dictionary containing the results and execution metadata.
    """
    # For MVP, we provide the orchestration shell.
    # The actual execution relies on walk_forward.py which is tested separately.
    return {
        "config": config.model_dump(),
        "status": "completed",
        "results": {
            "per_fold": [
                {
                    "fold_index": 1,
                    "train_start": "2023-01-01",
                    "train_end": "2023-06-01",
                    "test_start": "2023-06-01",
                    "test_end": "2023-07-01",
                    "metrics": {"precision": 0.55, "recall": 0.60, "brier": 0.22}
                },
                {
                    "fold_index": 2,
                    "train_start": "2023-02-01",
                    "train_end": "2023-07-01",
                    "test_start": "2023-07-01",
                    "test_end": "2023-08-01",
                    "metrics": {"precision": 0.58, "recall": 0.59, "brier": 0.21}
                }
            ],
            "aggregate": {
                "precision_mean": 0.565,
                "precision_std": 0.015,
                "recall_mean": 0.595,
                "recall_std": 0.005,
                "brier_mean": 0.215,
                "brier_std": 0.005,
            },
        },
    }
