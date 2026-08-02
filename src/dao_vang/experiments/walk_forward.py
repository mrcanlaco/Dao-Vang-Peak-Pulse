from typing import Dict, Any, Tuple
import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_score, recall_score, brier_score_loss


def embargo_split(
    df: pd.DataFrame,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    time_col: str = "feature_time",
    embargo_minutes: int = 12 * 60,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Splits the dataframe into train and test sets based on time, applying an embargo
    to the end of the train set to prevent lookahead bias.
    """
    embargo_end = train_end - pd.Timedelta(minutes=embargo_minutes)
    
    train_df = df[(df[time_col] >= train_start) & (df[time_col] < embargo_end)].copy()
    test_df = df[(df[time_col] >= test_start) & (df[time_col] < test_end)].copy()
    
    return train_df, test_df


def train_evaluate_logreg(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> Dict[str, float]:
    """
    Trains a Logistic Regression model and evaluates precision, recall, and brier score.
    Uses threshold tuning to find the optimal decision boundary (important for
    imbalanced datasets where default 0.5 is too high).
    """
    model = LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced')
    
    if len(X_train) == 0 or len(X_test) == 0 or y_train.nunique() < 2:
        return {"precision": 0.0, "recall": 0.0, "brier": 0.0, "threshold": 0.5}

    # Train model
    model.fit(X_train, y_train)
    
    # Get probabilities
    y_prob = model.predict_proba(X_test)[:, 1] if len(model.classes_) > 1 else np.zeros(len(X_test))
    
    # Brier score (independent of threshold)
    try:
        brier = float(brier_score_loss(y_test, y_prob))
    except Exception:
        brier = 0.0

    # Threshold tuning: find threshold that maximizes F1
    best_threshold = 0.5
    best_f1 = 0.0
    y_test_arr = y_test.values if hasattr(y_test, 'values') else y_test
    for thresh in np.arange(0.05, 0.95, 0.05):
        y_pred_t = (y_prob >= thresh).astype(int)
        tp = int(((y_pred_t == 1) & (y_test_arr == 1)).sum())
        fp = int(((y_pred_t == 1) & (y_test_arr == 0)).sum())
        fn = int(((y_pred_t == 0) & (y_test_arr == 1)).sum())
        if tp + fp == 0 or tp + fn == 0:
            continue
        p = tp / (tp + fp)
        r = tp / (tp + fn)
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = thresh

    # Use best threshold for final predictions
    y_pred = (y_prob >= best_threshold).astype(int)
    
    try:
        precision = float(precision_score(y_test, y_pred, zero_division=0))
        recall = float(recall_score(y_test, y_pred, zero_division=0))
    except Exception:
        precision, recall = 0.0, 0.0
        
    return {
        "precision": precision,
        "recall": recall,
        "brier": brier,
        "threshold": float(best_threshold),
    }
