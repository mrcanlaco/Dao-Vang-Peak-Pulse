from typing import Dict, Any, Tuple
import pandas as pd
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
    """
    # Initialize baseline logistic regression model
    model = LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced')
    
    if len(X_train) == 0 or len(X_test) == 0 or y_train.nunique() < 2:
        return {"precision": 0.0, "recall": 0.0, "brier": 0.0}

    # Train model
    model.fit(X_train, y_train)
    
    # Predict
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1] if len(model.classes_) > 1 else [0.0] * len(X_test)
    
    # Metrics
    try:
        precision = float(precision_score(y_test, y_pred, zero_division=0))
        recall = float(recall_score(y_test, y_pred, zero_division=0))
        brier = float(brier_score_loss(y_test, y_prob))
    except Exception:
        precision, recall, brier = 0.0, 0.0, 0.0
        
    return {
        "precision": precision,
        "recall": recall,
        "brier": brier
    }
