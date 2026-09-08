import logging
import sys
from datetime import datetime
from typing import cast
import numpy as np
import pandas as pd
import duckdb
from pathlib import Path
from sklearn.isotonic import IsotonicRegression
import lightgbm as lgb
from sklearn.metrics import precision_score, recall_score, brier_score_loss

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dao_vang.experiments.backtest_runner import FullBacktestRunner, BacktestRunConfig
from dao_vang.experiments.ablation import run_ablation_matrix, FEATURE_GROUPS
from dao_vang.validation.splits import generate_walk_forward_splits

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(message)s")
logger = logging.getLogger(__name__)

ALL_FEATURES = [col for cols in FEATURE_GROUPS.values() for col in cols]

def compute_ece(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    n = len(y_true)
    if n == 0:
        return 0.0
    for i in range(n_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]
        in_bin = (y_prob >= bin_lower) & (y_prob < bin_upper if i < n_bins - 1 else y_prob <= bin_upper)
        prop_in_bin = np.mean(in_bin)
        if prop_in_bin > 0:
            accuracy_in_bin = np.mean(y_true[in_bin])
            avg_confidence_in_bin = np.mean(y_prob[in_bin])
            ece += np.abs(avg_confidence_in_bin - accuracy_in_bin) * prop_in_bin
    return float(ece)

def create_evaluator(folds):
    def evaluator(frame: pd.DataFrame, variant_name: str):
        logger.info(f"Evaluating variant: {variant_name}")
        
        active_features = [col for col in ALL_FEATURES if col in frame.columns and bool(frame[col].notna().any())]
        logger.info(f"  Active features: {len(active_features)} / {len(ALL_FEATURES)}")
        
        frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
        work = frame.dropna(subset=active_features + ["is_distribution"]).copy()
        
        if work.empty:
            return {"precision": 0.0, "recall": 0.0, "signals": 0}
            
        all_y_true = []
        all_y_pred = []
        all_y_prob = []
        
        for f in folds:
            train_mask = (work["feature_time"] >= pd.Timestamp(f.train.start_time)) & (work["feature_time"] < pd.Timestamp(f.train.end_time))
            cal_mask = (work["feature_time"] >= pd.Timestamp(f.calibration.start_time)) & (work["feature_time"] < pd.Timestamp(f.calibration.end_time))
            test_mask = (work["feature_time"] >= pd.Timestamp(f.test.start_time)) & (work["feature_time"] < pd.Timestamp(f.test.end_time))
            
            X_fit, y_fit = work.loc[train_mask, active_features], work.loc[train_mask, "is_distribution"]
            X_cal, y_cal = work.loc[cal_mask, active_features], work.loc[cal_mask, "is_distribution"]
            X_test, y_test = work.loc[test_mask, active_features], work.loc[test_mask, "is_distribution"]
            
            if y_fit.sum() < 10 or y_cal.sum() < 5 or y_test.sum() < 1:
                continue
                
            dtrain = lgb.Dataset(X_fit, label=y_fit)
            params = {
                "objective": "binary",
                "metric": "binary_logloss",
                "learning_rate": 0.05,
                "num_leaves": 63,
                "min_data_in_leaf": 30,
                "scale_pos_weight": 3.0,
                "verbose": -1,
                "seed": 42,
                "force_col_wise": True,
            }
            bst = lgb.train(params, dtrain, num_boost_round=300)
            
            cal_preds = bst.predict(X_cal)
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(cal_preds, y_cal)
            
            # Threshold (Fixed confidence - 20% calibrated probability, ~8x base rate)
            threshold = 0.20
            
            test_preds = bst.predict(X_test)
            test_cal_preds = iso.predict(test_preds)
            y_pred = (test_cal_preds >= threshold).astype(int)
            
            all_y_true.extend(y_test.values)
            all_y_prob.extend(test_cal_preds)
            all_y_pred.extend(y_pred)
            
        if not all_y_true:
            return {"precision": 0.0, "recall": 0.0, "signals": 0}
            
        y_true = np.array(all_y_true)
        y_pred = np.array(all_y_pred)
        y_prob = np.array(all_y_prob)
        
        prec = float(precision_score(y_true, y_pred, zero_division=cast(str, 0.0)))
        rec = float(recall_score(y_true, y_pred, zero_division=cast(str, 0.0)))
        brier = float(brier_score_loss(y_true, y_prob))
        ece = compute_ece(y_true, y_prob)
        
        return {
            "precision": prec,
            "recall": rec,
            "brier": brier,
            "ece": ece,
            "signals": int(y_pred.sum())
        }
    return evaluator

def main():
    logger.info("Initializing Backtest Data Environment...")
    config = BacktestRunConfig(
        start_date="2025-12-01",
        end_date="2026-08-15",
        horizon_hours=24,
        symbols=[
            "SPCXUSDT", "UNIUSDT", "CFXUSDT", "LINEAUSDT", "ARUSDT", 
            "2ZUSDT", "WIFUSDT", "NMRUSDT", "COMPUSDT", "ZKUSDT", 
            "ACEUSDT", "ARKMUSDT", "FFUSDT", "PLUMEUSDT", "LPTUSDT"
        ]
    )
    
    # We rely on the memory limit and temp directory now inside backtest_runner.py
    runner = FullBacktestRunner(config)
    runner.run()
    
    conn = duckdb.connect(str(config.output_db_path), read_only=False)
    
    logger.info("Creating unified view for ablation...")
    conn.execute("""
        CREATE OR REPLACE VIEW bt_combined AS
        SELECT f.*, l.label_value AS is_distribution
        FROM bt_features f
        JOIN bt_labels l ON f.symbol = l.symbol AND f.feature_time = l.signal_time
        WHERE l.label_value IS NOT NULL
    """)
    
    row = conn.execute("SELECT COUNT(*), MIN(feature_time), MAX(feature_time) FROM bt_combined").fetchone()
    if not row or row[0] == 0:
        logger.error("No data in bt_combined")
        return
        
    count, min_time, max_time = row
    logger.info(f"bt_combined rows: {count}, time range: {min_time} to {max_time}")
    
    logger.info(f"Generating Walk-Forward Folds from {min_time} to {max_time}...")
    folds = generate_walk_forward_splits(
        dataset_start=cast(datetime, pd.Timestamp(min_time).to_pydatetime()),
        dataset_end=cast(datetime, pd.Timestamp(max_time).to_pydatetime()),
        train_days=60,
        cal_days=15,
        test_days=15,
        step_days=15,
        embargo_hours=48
    )
    logger.info(f"Generated {len(folds)} folds")
    
    if len(folds) == 0:
        logger.error("No folds generated. Check date range and fold sizes.")
        return
        
    evaluator_func = create_evaluator(folds)
    
    logger.info("Starting Causal Ablation Matrix...")
    results = run_ablation_matrix(conn, "bt_combined", evaluator_func)
    
    logger.info("Ablation Results:")
    df_res = pd.DataFrame.from_dict(results, orient='index')
    if not df_res.empty:
        df_res = df_res.sort_values("precision", ascending=False)
        print("\n" + "="*80)
        print(f"{'VARIANT':<20} | {'PRECISION':<10} | {'RECALL':<8} | {'SIGNALS':<8}")
        print("="*80)
        for var, row in df_res.iterrows():
            print(f"{var:<20} | {row['precision']*100:>8.2f}% | {row['recall']*100:>7.2f}% | {row['signals']:>8.0f}")
        print("="*80)

if __name__ == "__main__":
    main()
