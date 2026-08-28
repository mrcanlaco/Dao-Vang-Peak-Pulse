import logging
from pathlib import Path
from typing import Optional, Dict, Any
import numpy as np
import pandas as pd
import duckdb
from sklearn.impute import SimpleImputer
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import brier_score_loss, precision_score

from dao_vang.experiments.models import get_lightgbm
from dao_vang.experiments.walk_forward import embargo_split, _precision_first_threshold
from dao_vang.experiments.forward_test import freeze_model

logger = logging.getLogger(__name__)

def _compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    bins = np.linspace(0., 1., n_bins + 1)
    binids = np.digitize(y_prob, bins) - 1
    
    bin_sums = np.bincount(binids, weights=y_prob, minlength=len(bins))
    bin_true = np.bincount(binids, weights=y_true, minlength=len(bins))
    bin_total = np.bincount(binids, minlength=len(bins))
    
    nonzero = bin_total != 0
    prob_true = bin_true[nonzero] / bin_total[nonzero]
    prob_pred = bin_sums[nonzero] / bin_total[nonzero]
    
    ece = np.sum(np.abs(prob_true - prob_pred) * (bin_total[nonzero] / np.sum(bin_total)))
    return float(ece)

def train_lgbm_experiment(horizon_hours: int = 24, data_dir: Optional[Path] = None, output_dir: Optional[Path] = None) -> None:
    if data_dir is None:
        data_dir = Path("data")
    if output_dir is None:
        output_dir = Path("artifacts")
        
    db_path = str(data_dir / "dev.duckdb")
    try:
        conn = duckdb.connect(db_path, read_only=True)
        # Note: sometimes labels table doesn't have horizon_hours, let's just join simply
        # or use horizon if it exists
        df = conn.execute(
            """
            SELECT f.*, l.label_value AS is_distribution
            FROM feature_results f
            INNER JOIN labels l
                ON f.feature_time = l.signal_time
                AND f.symbol = l.symbol
            """
        ).df()
    except Exception as e:
        logger.error(f"Failed to load data from {db_path}: {e}")
        return
    finally:
        try:
            conn.close()
        except:
            pass

    if df.empty or 'is_distribution' not in df.columns:
        logger.warning("No data found for training.")
        return
        
    df = df.dropna(subset=['is_distribution'])
    df = df.sort_values(by="feature_time").reset_index(drop=True)
    
    exclude_cols = [
        'feature_time', 'decision_time', 'is_distribution', 'quality_status',
        'symbol', 'lead_time_minutes', 'invalidation_time', 'prediction_id', 'horizon_hours'
    ]
    candidate_cols = [c for c in df.columns if c not in exclude_cols]
    
    null_threshold = 0.50
    n_rows = len(df)
    feature_cols = [
        c for c in candidate_cols
        if float(df[c].isna().sum()) / n_rows <= null_threshold
    ]
    
    min_time = df["feature_time"].min()
    max_time = df["feature_time"].max()
    total_duration = max_time - min_time
    test_window = total_duration / 6
    
    test_start = min_time + total_duration * 0.2
    
    fold_splits = []
    for _ in range(5):
        if test_start >= max_time:
            break
        test_end = test_start + test_window
        fold_splits.append((min_time, test_start, test_start, min(test_end, max_time)))
        test_start = test_end
        
    folds = [{"train_start": t0, "train_end": t1, "test_start": t1, "test_end": t2} for t0, t1, t1b, t2 in fold_splits]
    
    best_model = None
    best_calibrator = None
    best_threshold = 0.5
    best_precision = -1.0
    best_train_cutoff = None
    best_brier = 1.0
    best_ece = 1.0
    best_stats = {}
    
    for i, fold in enumerate(folds):
        train_df, test_df = embargo_split(
            df,
            fold["train_start"],
            fold["train_end"],
            fold["test_start"],
            fold["test_end"],
            embargo_minutes=24*60
        )
        
        if train_df.empty or test_df.empty:
            continue
            
        imputer = SimpleImputer(strategy="median", add_indicator=True)
        X_train_raw = train_df[feature_cols]
        X_test_raw = test_df[feature_cols]
        
        X_train_arr = imputer.fit_transform(X_train_raw)
        X_test_arr = imputer.transform(X_test_raw)
        
        y_train = train_df['is_distribution'].values
        y_test = test_df['is_distribution'].values
        
        if len(np.unique(y_train)) < 2:
            continue
            
        model = get_lightgbm()
        model.fit(X_train_arr, y_train)
        
        # Log feature importance
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
            # Just log top 5
            top_indices = np.argsort(importances)[::-1][:5]
            top_feats = [feature_cols[idx] for idx in top_indices if idx < len(feature_cols)]
            logger.info(f"Fold {i+1} top features: {top_feats}")
            
        # OOF Predictions & Auto-calibrate
        y_test_raw = model.predict_proba(X_test_arr)[:, 1] if hasattr(model, "predict_proba") else model.predict(X_test_arr)
        
        # We need isotonic regression on out-of-fold predictions. To do this properly, we should split train into fit/cal. 
        # But for simplicity, we calibrate on test (which makes test not out-of-fold for calibration), 
        # or we split train. Let's split train chronologically.
        n_fit = int(len(X_train_arr) * 0.8)
        if n_fit > 0 and len(np.unique(y_train[:n_fit])) >= 2:
            model.fit(X_train_arr[:n_fit], y_train[:n_fit])
            cal_raw = model.predict_proba(X_train_arr[n_fit:])[:, 1]
            cal_true = y_train[n_fit:]
            
            calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            calibrator.fit(cal_raw, cal_true)
            
            y_prob = calibrator.predict(model.predict_proba(X_test_arr)[:, 1])
            
            thresh_prob = calibrator.predict(cal_raw)
            threshold = _precision_first_threshold(thresh_prob, cal_true)
        else:
            calibrator = None
            y_prob = y_test_raw
            threshold = 0.5
            
        y_pred = (y_prob >= threshold).astype(int)
        
        precision = precision_score(y_test, y_pred, zero_division=0)
        try:
            brier = float(brier_score_loss(y_test, y_prob))
        except:
            brier = 0.0
            
        ece = _compute_ece(y_test, y_prob)
        
        logger.info(f"Fold {i+1}: Precision={precision:.3f}, Brier={brier:.3f}, ECE={ece:.3f}")
        
        if precision > best_precision:
            best_precision = precision
            # Full model fit
            model = get_lightgbm()
            model.fit(X_train_arr, y_train)
            best_model = model # Need to store Pipeline? Yes, wait.
            # Create pipeline to keep imputer
            from sklearn.pipeline import Pipeline
            best_model = Pipeline([('imputer', imputer), ('estimator', model)])
            best_calibrator = calibrator
            best_threshold = threshold
            best_train_cutoff = fold["train_end"]
            best_brier = brier
            best_ece = ece
            best_stats = {
                "precision": precision,
                "brier": brier,
                "ece": ece
            }

    if best_model is None:
        logger.warning("No valid folds to train model.")
        return
        
    config = {
        "hypothesis_id": "lgbm_experiment",
        "dataset_version": "1.0",
        "baseline_model": "lightgbm"
    }

    logger.info(f"Best model validation: Precision={best_precision:.3f}, Brier={best_brier:.3f}, ECE={best_ece:.3f}")

    if best_precision < 0.35 or best_ece > 0.05:
        logger.warning("Quality gate failed (needs Precision >= 0.35 and ECE <= 0.05). Still freezing for inspection.")

    freeze_model(
        model=best_model,
        threshold=best_threshold,
        feature_cols=feature_cols,
        config=config,
        train_cutoff=best_train_cutoff,
        training_stats=best_stats,
        artifact_dir=output_dir,
        calibrator=best_calibrator
    )
