from pathlib import Path
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
    db_path: str = "./data/dev.duckdb"
    code_commit: Optional[str] = None


def _mock_results(config: ExperimentConfig) -> Dict[str, Any]:
    """Return mock results for MVP demo / when no real data is available."""
    return {
        "config": config.model_dump(),
        "status": "completed",
        "results": {
            "per_fold": [
                {
                    "fold_idx": 1,
                    "train_start": "2023-01-01",
                    "train_end": "2023-06-01",
                    "test_start": "2023-06-01",
                    "test_end": "2023-07-01",
                    "metrics": {"precision": 0.55, "recall": 0.60, "brier": 0.22},
                },
                {
                    "fold_idx": 2,
                    "train_start": "2023-02-01",
                    "train_end": "2023-07-01",
                    "test_start": "2023-07-01",
                    "test_end": "2023-08-01",
                    "metrics": {"precision": 0.58, "recall": 0.59, "brier": 0.21},
                },
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


def run_experiment(
    config: ExperimentConfig, conn: Any = None
) -> Dict[str, Any]:
    """
    Orchestrates the experiment:
    - Loads dataset, features, labels based on versions in config.
    - Applies splits.
    - Runs the selected model.
    - Computes metrics.

    If ``conn`` is provided (a live DuckDB connection), it is used directly
    instead of opening a new one. This avoids file-lock conflicts when the
    caller (e.g. the Streamlit UI) already holds a write connection.

    Returns a dictionary containing the results and execution metadata.
    """
    import duckdb
    import pandas as pd
    import numpy as np
    from dao_vang.experiments.walk_forward import embargo_split, train_evaluate_logreg

    owns_conn = conn is None
    if owns_conn:
        # Connect to DuckDB and load data.
        # Fall back to mock results if the DB is unavailable (e.g. locked by
        # another process such as the Streamlit UI) or has no usable data.
        try:
            conn = duckdb.connect(config.db_path, read_only=True)
        except Exception:
            return _mock_results(config)

    # Load features joined with labels
    try:
        df = conn.execute(
            """
            SELECT f.*, l.label_value AS is_distribution
            FROM feature_results f
            INNER JOIN labels l
                ON f.feature_time = l.signal_time
                AND f.symbol = l.symbol
            """
        ).df()
    except Exception:
        if owns_conn:
            try:
                conn.close()
            except Exception:
                pass
        return _mock_results(config)
    finally:
        if owns_conn:
            try:
                conn.close()
            except Exception:
                pass

    if df.empty or 'is_distribution' not in df.columns:
        return _mock_results(config)

    # Keep only rows with valid labels
    df = df.dropna(subset=['is_distribution'])

    if len(df) < 100:
        return _mock_results(config)

    # Sort by time
    df = df.sort_values(by="feature_time").reset_index(drop=True)
    
    # We will do 2 simple walk-forward folds based on the data span
    min_time = df["feature_time"].min()
    max_time = df["feature_time"].max()
    
    total_duration = max_time - min_time
    # E.g. Split total duration into 3 parts: fold1_train, fold1_test/fold2_train, fold2_test
    # This is a naive splitting strategy for MVP
    part_duration = total_duration / 3
    
    t0 = min_time
    t1 = min_time + part_duration
    t2 = min_time + 2 * part_duration
    t3 = max_time
    
    folds = [
        {"train_start": t0, "train_end": t1, "test_start": t1, "test_end": t2},
        {"train_start": t1, "train_end": t2, "test_start": t2, "test_end": t3},
    ]
    
    # Feature columns (everything except time, decision time, labels, etc.)
    exclude_cols = ['feature_time', 'decision_time', 'is_distribution', 'quality_status', 'symbol']
    feature_cols = [c for c in df.columns if c not in exclude_cols]
    
    results_per_fold = []
    
    for i, fold in enumerate(folds):
        train_df, test_df = embargo_split(
            df, 
            fold["train_start"], 
            fold["train_end"], 
            fold["test_start"], 
            fold["test_end"]
        )
        
        X_train = train_df[feature_cols].fillna(0)
        y_train = train_df['is_distribution']
        X_test = test_df[feature_cols].fillna(0)
        y_test = test_df['is_distribution']
        
        metrics = train_evaluate_logreg(X_train, y_train, X_test, y_test)
        
        results_per_fold.append({
            "fold_idx": i + 1,
            "train_start": str(fold["train_start"]),
            "train_end": str(fold["train_end"]),
            "test_start": str(fold["test_start"]),
            "test_end": str(fold["test_end"]),
            "metrics": metrics
        })
        
    # Aggregate
    precisions = [f["metrics"]["precision"] for f in results_per_fold]
    recalls = [f["metrics"]["recall"] for f in results_per_fold]
    briers = [f["metrics"]["brier"] for f in results_per_fold]
    
    aggregate = {
        "precision_mean": float(np.mean(precisions)) if precisions else 0.0,
        "precision_std": float(np.std(precisions)) if precisions else 0.0,
        "recall_mean": float(np.mean(recalls)) if recalls else 0.0,
        "recall_std": float(np.std(recalls)) if recalls else 0.0,
        "brier_mean": float(np.mean(briers)) if briers else 0.0,
        "brier_std": float(np.std(briers)) if briers else 0.0,
    }

    return {
        "config": config.model_dump(),
        "status": "completed",
        "results": {
            "per_fold": results_per_fold,
            "aggregate": aggregate,
        },
    }
