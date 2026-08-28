from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dao_vang.experiments.walk_forward_backtest import (
    compute_backtest_metrics,
    run_walk_forward_validation,
)


def test_compute_backtest_metrics_basic():
    scores = np.array([0.9, 0.8, 0.7, 0.4, 0.3, 0.2])
    labels = np.array([1, 1, 0, 0, 0, 1])

    m = compute_backtest_metrics(scores, labels, threshold=0.5)
    assert m.total_samples == 6
    assert m.total_signals == 3
    assert m.positive_events == 3
    # 2 true positives (0.9, 0.8), 1 false positive (0.7)
    assert round(m.precision, 2) == 0.67
    assert round(m.recall, 2) == 0.67
    assert m.false_positives == 1


def test_run_walk_forward_validation():
    dates = pd.date_range("2026-01-01", periods=150, freq="h")
    scores = np.random.uniform(0.1, 0.9, size=150)
    labels = (scores > 0.45).astype(int)

    df = pd.DataFrame({
        "feature_time": dates,
        "score": scores,
        "label": labels,
    })

    summary = run_walk_forward_validation(
        df,
        score_col="score",
        label_col="label",
        n_splits=3,
        threshold=0.5,
        min_train_size=30,
        version_name="test_v3",
    )

    assert summary.version_name == "test_v3"
    assert summary.n_folds >= 1
    assert summary.mean_out_of_sample_win_rate >= 0.0
    report_dict = summary.to_dict()
    assert "folds" in report_dict
