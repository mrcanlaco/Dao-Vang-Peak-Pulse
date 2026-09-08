import duckdb
import pandas as pd
import numpy as np
import lightgbm as lgb
from sklearn.isotonic import IsotonicRegression
from pathlib import Path
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dao_vang.experiments.forward_test import freeze_model
from dao_vang.experiments.ablation import FEATURE_GROUPS

def main():
    logger.info("1. Connecting to DB and preparing features...")
    conn = duckdb.connect("artifacts/backtest_results.duckdb", read_only=True)
    
    active_features = []
    for group, cols in FEATURE_GROUPS.items():
        if group != "funding":
            active_features.extend(cols)
            
    logger.info(f"Selected {len(active_features)} features (Funding group removed).")
    
    df = conn.execute("""
        SELECT f.*, l.label_value AS is_distribution
        FROM bt_features f
        JOIN bt_labels l ON f.symbol = l.symbol AND f.feature_time = l.signal_time
        WHERE l.label_value IS NOT NULL
    """).df()
    conn.close()
    
    logger.info(f"Loaded {len(df)} labeled samples.")
    
    null_cols = [c for c in active_features if c not in df.columns or df[c].isna().all()]
    if null_cols:
        logger.warning(f"Dropping {len(null_cols)} completely NULL features: {null_cols}")
        active_features = [c for c in active_features if c not in null_cols]
        
    df["feature_time"] = pd.to_datetime(df["feature_time"], utc=True)
    df = df.dropna(subset=active_features + ["is_distribution"]).sort_values("feature_time").reset_index(drop=True)
    logger.info(f"Usable samples after NaN drop: {len(df)}")
    
    # Split Data chronologically
    train_idx = int(len(df) * 0.65)
    val_idx = int(len(df) * 0.75)
    cal_idx = int(len(df) * 0.85)
    
    train_df = df.iloc[:train_idx].copy()
    val_df = df.iloc[train_idx:val_idx].copy()
    cal_df = df.iloc[val_idx:cal_idx].copy()
    test_df = df.iloc[cal_idx:].copy()
    
    train_max_time = train_df["feature_time"].max()
    val_df = val_df[val_df["feature_time"] >= train_max_time + pd.Timedelta(hours=48)]
    if not val_df.empty:
        val_max_time = val_df["feature_time"].max()
        cal_df = cal_df[cal_df["feature_time"] >= val_max_time + pd.Timedelta(hours=24)]
        cal_max_time = cal_df["feature_time"].max()
        test_df = test_df[test_df["feature_time"] >= cal_max_time + pd.Timedelta(hours=24)]
    
    X_train, y_train = train_df[active_features], train_df["is_distribution"]
    X_val, y_val = val_df[active_features], val_df["is_distribution"]
    X_cal, y_cal = cal_df[active_features], cal_df["is_distribution"]
    
    logger.info(f"Train size: {len(X_train)} | Val size: {len(X_val)} | Cal size: {len(X_cal)} | Test size: {len(test_df)}")
    
    if len(X_val) == 0 or len(X_cal) == 0 or len(test_df) == 0:
        logger.error("Insufficient data after embargo purges.")
        return

    logger.info("2. Training LightGBM with Early Stopping...")
    dtrain = lgb.Dataset(X_train, label=y_train)
    dval = lgb.Dataset(X_val, label=y_val, reference=dtrain)
    
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
    
    bst = lgb.train(
        params,
        dtrain,
        num_boost_round=1000,
        valid_sets=[dtrain, dval],
        callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=True)]
    )
    
    logger.info("3. Fitting Isotonic Calibrator...")
    cal_preds = bst.predict(X_cal)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(cal_preds, y_cal)
    
    logger.info("4. Freezing Model (Evaluation will be strictly Out-Of-Sample)...")
    train_cutoff = cal_df["feature_time"].max().to_pydatetime()
    
    info = freeze_model(
        model=bst,
        threshold=0.20,
        feature_cols=active_features,
        config={"hypothesis_id": "lean_champion_no_funding", "note": "Removed funding group based on causal ablation"},
        train_cutoff=train_cutoff,
        training_stats={"train_size": len(X_train), "train_positives": int(y_train.sum())},
        calibrator=iso,
        artifact_dir=Path("artifacts")
    )
    
    logger.info(f"✅ MODEL FROZEN SUCCESSFULLY: {info.model_id}")

if __name__ == "__main__":
    main()
