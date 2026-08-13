import numpy as np
import pandas as pd
from datetime import datetime

from dao_vang.validation.metrics import compute_row_metrics, compute_event_metrics

def test_compute_row_metrics():
    y_true = np.array([1, 1, 0, 0])
    y_prob = np.array([0.9, 0.4, 0.8, 0.1])
    
    metrics = compute_row_metrics(y_true, y_prob, threshold=0.5)
    
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5

def test_compute_event_metrics():
    df = pd.DataFrame({
        "event_id": ["e1", "e1", "e2", "e3", None],
        "label_value": [1, 1, 1, 0, 0],
        "pred_value": [0, 1, 0, 1, 0],
        "signal_time": [datetime(2023,1,1), datetime(2023,1,2), datetime(2023,1,3), datetime(2023,1,4), datetime(2023,1,5)],
        "target_time": [datetime(2023,1,3), datetime(2023,1,3), datetime(2023,1,4), None, None]
    })
    
    metrics = compute_event_metrics(df)
    
    assert metrics["event_recall"] == 0.5  # e1 caught, e2 missed
    assert metrics["median_lead_time"] == 1440.0  # 1 day (e1 target_time - e1 first_pred_time)
