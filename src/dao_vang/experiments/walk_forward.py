from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_score, recall_score


def _precision_first_threshold(
    y_prob: np.ndarray,
    y_true: np.ndarray,
    min_recall: float = 0.50,
    thresh_grid: Optional[np.ndarray] = None,
) -> float:
    """Pick the threshold maximizing precision subject to recall >= min_recall.

    Falls back to the highest-precision threshold overall if none satisfy the
    recall floor (precision is always reported honestly by the caller).
    """
    if thresh_grid is None:
        thresh_grid = np.arange(0.05, 0.95, 0.01)
    n_pos = int((y_true == 1).sum())
    best_threshold = 0.5
    best_precision = -1.0
    best_precision_at_floor = -1.0
    best_threshold_at_floor = None
    for thresh in thresh_grid:
        y_pred_t = (y_prob >= thresh).astype(int)
        tp = int(((y_pred_t == 1) & (y_true == 1)).sum())
        fp = int(((y_pred_t == 1) & (y_true == 0)).sum())
        if tp + fp == 0:
            continue
        p = tp / (tp + fp)
        r = tp / n_pos if n_pos > 0 else 0.0
        if p > best_precision:
            best_precision = p
            best_threshold = thresh
        if r >= min_recall and p > best_precision_at_floor:
            best_precision_at_floor = p
            best_threshold_at_floor = thresh
    if best_threshold_at_floor is not None:
        best_threshold = best_threshold_at_floor
    return float(best_threshold)


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
    min_recall: float = 0.50,
    X_calibration: Optional[pd.DataFrame] = None,
    y_calibration: Optional[pd.Series] = None,
) -> Dict[str, float]:
    """
    Trains a Logistic Regression model and evaluates precision, recall, and brier score.
    Uses precision-first threshold tuning on a chronological calibration
    subset of training data; the test set is reserved for evaluation.
    Falls back to a neutral threshold when no calibration rows are available.

    Note: ``class_weight`` is left at None (default). The previous
    ``class_weight='balanced'`` setting artificially boosted recall at the
    direct expense of precision, which is the opposite of the precision-first
    objective.
    """
    model = LogisticRegression(max_iter=1000, random_state=42)

    if len(X_train) == 0 or len(X_test) == 0 or y_train.nunique() < 2:
        return {"precision": 0.0, "recall": 0.0, "brier": 0.0, "threshold": 0.5}

    # Train on a fit subset and reserve a chronological calibration subset for
    # threshold policy selection.  Never inspect y_test when selecting a
    # threshold; the test fold is evaluation-only.
    if X_calibration is None or y_calibration is None:
        n_fit = max(1, int(len(X_train) * 0.8))
        X_fit, y_fit = X_train.iloc[:n_fit], y_train.iloc[:n_fit]
        X_calibration = X_train.iloc[n_fit:]
        y_calibration = y_train.iloc[n_fit:]
    else:
        X_fit, y_fit = X_train, y_train
    if y_fit.nunique() < 2:
        X_fit, y_fit = X_train, y_train
    model.fit(X_fit, y_fit)

    # Get probabilities
    y_prob = model.predict_proba(X_test)[:, 1] if len(model.classes_) > 1 else np.zeros(len(X_test))

    # Brier score (independent of threshold)
    try:
        brier = float(brier_score_loss(y_test, y_prob))
    except Exception:
        brier = 0.0

    # Precision-first threshold tuning with a recall floor on calibration only.
    if (
        X_calibration is not None
        and y_calibration is not None
        and len(X_calibration) > 0
        and y_calibration.nunique() >= 1
    ):
        cal_prob = (
            model.predict_proba(X_calibration)[:, 1]
            if len(model.classes_) > 1
            else np.zeros(len(X_calibration))
        )
        best_threshold = _precision_first_threshold(
            cal_prob,
            y_calibration.values if hasattr(y_calibration, "values") else y_calibration,
            min_recall=min_recall,
        )
    else:
        best_threshold = 0.5

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


def train_evaluate_lightgbm(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    min_recall: float = 0.50,
    num_boost_round: int = 400,
) -> Dict[str, float]:
    """Train a LightGBM model with isotonic calibration and precision-first
    threshold tuning.

    Splits the training data into a fit set (first 80%) and a calibration set
    (last 20%) — both chronological. LightGBM is fit on the fit set, then an
    isotonic regression maps its raw scores to calibrated probabilities on the
    calibration set. The calibrated probabilities are then used to pick a
    precision-first threshold (max precision s.t. recall >= min_recall) on the
    calibration set; the test fold is evaluation-only.

    This addresses two weaknesses of the LogReg baseline:
      1. Non-linear feature interactions (LightGBM captures them natively).
      2. Poor probability calibration (isotonic regression sharpens the scores,
         which makes the precision/recall tradeoff much steeper — essential for
         reaching high precision at a controlled recall).
    """
    import lightgbm as lgb

    if len(X_train) == 0 or len(X_test) == 0 or y_train.nunique() < 2:
        return {"precision": 0.0, "recall": 0.0, "brier": 0.0, "threshold": 0.5}

    y_train_arr = np.asarray(y_train, dtype=np.float64)
    # Chronological split: fit on first 80%, calibrate on last 20%.
    n_train = len(X_train)
    n_fit = int(n_train * 0.8)
    X_fit = X_train.iloc[:n_fit]
    y_fit = y_train_arr[:n_fit]
    X_cal = X_train.iloc[n_fit:]
    y_cal = y_train_arr[n_fit:]

    # If the fit or cal split has only one class, fall back to fitting on all
    # training data and skip calibration.
    calibrate = (
        len(np.unique(y_fit)) >= 2
        and len(np.unique(y_cal)) >= 2
        and len(X_cal) >= 50
    )

    pos_ratio = float(y_fit.mean()) if len(y_fit) > 0 else 0.1
    # scale_pos_weight < 1 biases toward precision (we want fewer, more confident
    # positives). For a precision-first objective we deliberately do NOT balance.
    scale_pos_weight = 1.0

    train_set = lgb.Dataset(X_fit, label=y_fit)
    params = {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.03,
        "num_leaves": 63,
        "min_data_in_leaf": 100,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.9,
        "bagging_freq": 5,
        "scale_pos_weight": scale_pos_weight,
        "pos_ratio": pos_ratio,
        "verbose": -1,
        "seed": 42,
        "deterministic": True,
        "force_col_wise": True,
    }
    valid_sets = [lgb.Dataset(X_cal, label=y_cal)] if calibrate else []
    callbacks = [lgb.early_stopping(50, verbose=False)] if calibrate else []
    model = lgb.train(
        params,
        train_set,
        num_boost_round=num_boost_round,
        valid_sets=valid_sets,
        callbacks=callbacks,
    )

    # Raw scores on test set
    y_score_raw = model.predict(X_test)
    if calibrate:
        cal_raw = model.predict(X_cal)
        # Isotonic regression: map raw scores -> calibrated probabilities.
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
        iso.fit(cal_raw, y_cal)
        y_prob = iso.predict(y_score_raw)
    else:
        y_prob = y_score_raw

    # Brier on calibrated probabilities
    try:
        brier = float(brier_score_loss(y_test, y_prob))
    except Exception:
        brier = 0.0

    # Select the decision threshold from the chronological calibration fold,
    # never from the held-out test fold.
    if calibrate:
        threshold_prob = iso.predict(cal_raw)
        threshold_true = y_cal
    elif len(X_cal) > 0 and len(np.unique(y_cal)) >= 1:
        threshold_prob = model.predict(X_cal)
        threshold_true = y_cal
    else:
        threshold_prob = np.asarray([], dtype=float)
        threshold_true = np.asarray([], dtype=float)
    best_threshold = (
        _precision_first_threshold(
            threshold_prob, threshold_true, min_recall=min_recall
        )
        if len(threshold_prob)
        else 0.5
    )
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

    imputer = SimpleImputer(strategy="median", add_indicator=True)
    X_train = imputer.fit_transform(train_df[feature_cols])
    y_train = train_df["is_distribution"]
    X_predict = imputer.transform(predict_df[feature_cols])

    # Train model (no class_weight='balanced' — precision-first objective)
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X_train, y_train)

    # Get probabilities for latest candles
    y_prob = model.predict_proba(X_predict)[:, 1] if len(model.classes_) > 1 else np.zeros(len(X_predict))

    # Find optimal threshold on a validation set (last 20% of training data).
    # Precision-first: among thresholds with recall >= 0.50, pick the highest
    # precision. Falls back to highest-precision threshold overall.
    val_cutoff = train_df["feature_time"].quantile(0.8)
    val_df = train_df[train_df["feature_time"] >= val_cutoff]
    if len(val_df) > 0 and val_df["is_distribution"].nunique() >= 2:
        X_val = imputer.transform(val_df[feature_cols])
        y_val = val_df["is_distribution"]
        y_val_prob = model.predict_proba(X_val)[:, 1] if len(model.classes_) > 1 else np.zeros(len(X_val))

        min_recall = 0.50
        y_val_arr = y_val.values
        best_threshold = _precision_first_threshold(
            y_val_prob, y_val_arr, min_recall=min_recall
        )

        from sklearn.metrics import brier_score_loss, precision_score, recall_score
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
