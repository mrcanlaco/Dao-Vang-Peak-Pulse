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
            "per_fold": [],
            "aggregate": {},
        },
    }
