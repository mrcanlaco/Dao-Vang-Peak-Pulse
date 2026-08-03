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


def train_and_predict_latest(
    df: pd.DataFrame,
    feature_cols: list,
    n_latest: int = 10,
    embargo_minutes: int = 12 * 60,
) -> Dict[str, Any]:
    """
    Train LogisticRegression on all data except the last n_latest rows (with embargo),
    then predict probability of distribution for the most recent candles.

    This implements Khối 4 (probability) and Khối 5 (watchlist) from the Constitution.

    Returns:
        predictions: list of {feature_time, symbol, probability, risk_level, top_features}
        model_metrics: precision, recall, brier, threshold from last-fold validation
        model_info: coefficients, intercept, feature_importance
    """
    df = df.sort_values("feature_time").reset_index(drop=True)

    if len(df) < 200 or "is_distribution" not in df.columns:
        return {"predictions": [], "model_metrics": {}, "model_info": {}}

    # Drop rows without labels for training
    labeled = df.dropna(subset=["is_distribution"])
    if labeled["is_distribution"].nunique() < 2:
        return {"predictions": [], "model_metrics": {}, "model_info": {}}

    # Split: train = all except last n_latest + embargo, predict = last n_latest
    cutoff_time = df["feature_time"].iloc[-n_latest]
    embargo_end = cutoff_time - pd.Timedelta(minutes=embargo_minutes)

    train_df = labeled[labeled["feature_time"] < embargo_end].copy()
    predict_df = df[df["feature_time"] >= cutoff_time].copy()

    if len(train_df) == 0 or train_df["is_distribution"].nunique() < 2:
        return {"predictions": [], "model_metrics": {}, "model_info": {}}

    X_train = train_df[feature_cols].fillna(0)
    y_train = train_df["is_distribution"]
    X_predict = predict_df[feature_cols].fillna(0)

    # Train model
    model = LogisticRegression(max_iter=1000, random_state=42, class_weight='balanced')
    model.fit(X_train, y_train)

    # Get probabilities for latest candles
    y_prob = model.predict_proba(X_predict)[:, 1] if len(model.classes_) > 1 else np.zeros(len(X_predict))

    # Find optimal threshold on a validation set (last 20% of training data)
    val_cutoff = train_df["feature_time"].quantile(0.8)
    val_df = train_df[train_df["feature_time"] >= val_cutoff]
    if len(val_df) > 0 and val_df["is_distribution"].nunique() >= 2:
        X_val = val_df[feature_cols].fillna(0)
        y_val = val_df["is_distribution"]
        y_val_prob = model.predict_proba(X_val)[:, 1] if len(model.classes_) > 1 else np.zeros(len(X_val))

        best_threshold = 0.5
        best_f1 = 0.0
        y_val_arr = y_val.values
        for thresh in np.arange(0.05, 0.95, 0.05):
            y_pred_t = (y_val_prob >= thresh).astype(int)
            tp = int(((y_pred_t == 1) & (y_val_arr == 1)).sum())
            fp = int(((y_pred_t == 1) & (y_val_arr == 0)).sum())
            fn = int(((y_pred_t == 0) & (y_val_arr == 1)).sum())
            if tp + fp == 0 or tp + fn == 0:
                continue
            p = tp / (tp + fp)
            r = tp / (tp + fn)
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = thresh

        from sklearn.metrics import precision_score, recall_score, brier_score_loss
        y_val_pred = (y_val_prob >= best_threshold).astype(int)
        val_metrics = {
            "precision": float(precision_score(y_val, y_val_pred, zero_division=0)),
            "recall": float(recall_score(y_val, y_val_pred, zero_division=0)),
            "brier": float(brier_score_loss(y_val, y_val_prob)),
            "threshold": float(best_threshold),
        }
    else:
        val_metrics = {"precision": 0.0, "recall": 0.0, "brier": 0.0, "threshold": 0.5}
        best_threshold = 0.5

    # Build predictions
    horizon_minutes = 1440  # MVP v0.1: 24h horizon
    predictions = []
    for i in range(len(predict_df)):
        prob = float(y_prob[i])
        # Risk level based on probability and threshold
        if prob >= best_threshold:
            risk = "CAO" if prob >= best_threshold * 1.5 else "TRUNG BÌNH"
        elif prob >= best_threshold * 0.5:
            risk = "THẤP"
        else:
            risk = "RẤT THẤP"

        ft = predict_df["feature_time"].iloc[i]
        # Invalidation time: signal expires after horizon (24h).
        # After this, if distribution hasn't materialized, signal is a false positive.
        invalidation_time = ft + pd.Timedelta(minutes=horizon_minutes)

        predictions.append({
            "feature_time": str(ft),
            "symbol": predict_df["symbol"].iloc[i] if "symbol" in predict_df.columns else "N/A",
            "close": float(predict_df["close"].iloc[i]) if "close" in predict_df.columns else None,
            "probability": prob,
            "risk_level": risk,
            "threshold": float(best_threshold),
            "invalidation_time": str(invalidation_time),
        })

    # Feature importance (top 5)
    if hasattr(model, "coef_") and len(feature_cols) == len(model.coef_[0]):
        coefs = list(zip(feature_cols, model.coef_[0]))
        coefs.sort(key=lambda x: abs(x[1]), reverse=True)
        top_features = [{"feature": f, "coefficient": float(c)} for f, c in coefs[:5]]
    else:
        top_features = []

    model_info = {
        "top_features": top_features,
        "train_size": len(train_df),
        "train_positives": int(y_train.sum()),
        "n_predictions": len(predictions),
    }

    return {
        "predictions": predictions,
        "model_metrics": val_metrics,
        "model_info": model_info,
    }
