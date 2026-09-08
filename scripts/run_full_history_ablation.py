import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import cast

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.isotonic import IsotonicRegression
from sklearn.metrics import (
    average_precision_score,
    precision_score,
    recall_score,
)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dao_vang.data.historical_adapter import DEFAULT_MASTER_DUCKDB
from dao_vang.experiments.ablation import FEATURE_GROUPS, run_ablation_matrix
from dao_vang.experiments.backtest_runner import BacktestRunConfig, FullBacktestRunner
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

def create_evaluator(folds, required_symbols_count: int):
    def evaluator(frame: pd.DataFrame, variant_name: str):
        active_features = [col for col in ALL_FEATURES if col in frame.columns and bool(frame[col].notna().any())]
        
        frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
        work = frame.dropna(subset=active_features + ["is_distribution"]).copy()
        
        if work.empty:
            return {"precision": 0.0, "recall": 0.0, "signals": 0, "base_rate": 0.0, "pr_auc": 0.0, "folds_evaluated": 0, "precision_std": 0.0}
            
        fold_precisions = []
        all_y_true = []
        all_y_pred = []
        all_y_prob = []
        folds_evaluated = 0
        
        for idx, f in enumerate(folds):
            if f.calibration is None:
                continue
                
            train_mask = (work["feature_time"] >= pd.Timestamp(f.train.start_time)) & (work["feature_time"] < pd.Timestamp(f.train.end_time))
            cal_mask = (work["feature_time"] >= pd.Timestamp(f.calibration.start_time)) & (work["feature_time"] < pd.Timestamp(f.calibration.end_time))
            test_mask = (work["feature_time"] >= pd.Timestamp(f.test.start_time)) & (work["feature_time"] < pd.Timestamp(f.test.end_time))
            
            # HARD GATE: Check if all symbols are present in every subset
            train_syms = work.loc[train_mask, "symbol"].nunique()
            cal_syms = work.loc[cal_mask, "symbol"].nunique()
            test_syms = work.loc[test_mask, "symbol"].nunique()
            
            if train_syms < required_symbols_count or cal_syms < required_symbols_count or test_syms < required_symbols_count:
                logger.warning(f"Variant {variant_name} skipping fold {idx+1}: Missing symbol coverage (Train: {train_syms}, Cal: {cal_syms}, Test: {test_syms} vs Req: {required_symbols_count})")
                continue
            
            X_fit, y_fit = work.loc[train_mask, active_features], work.loc[train_mask, "is_distribution"]
            X_cal, y_cal = work.loc[cal_mask, active_features], work.loc[cal_mask, "is_distribution"]
            X_test, y_test = work.loc[test_mask, active_features], work.loc[test_mask, "is_distribution"]
            
            if y_fit.sum() < 5 or y_cal.sum() < 2 or y_test.sum() < 1:
                continue
                
            dtrain = lgb.Dataset(X_fit, label=y_fit)
            params = {
                "objective": "binary",
                "metric": "binary_logloss",
                "learning_rate": 0.05,
                "num_leaves": 31,
                "min_data_in_leaf": 20,
                "scale_pos_weight": 2.0,
                "verbose": -1,
                "seed": 42,
                "force_col_wise": True,
            }
            bst = lgb.train(params, dtrain, num_boost_round=150)
            
            cal_preds = bst.predict(X_cal)
            iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            iso.fit(cal_preds, y_cal)
            
            threshold = 0.20
            
            test_preds = bst.predict(X_test)
            test_cal_preds = iso.predict(test_preds)
            y_pred = (test_cal_preds >= threshold).astype(int)
            
            all_y_true.extend(y_test.values)
            all_y_prob.extend(test_cal_preds)
            all_y_pred.extend(y_pred)
            
            if y_pred.sum() > 0:
                fold_precisions.append(precision_score(y_test.values, y_pred, zero_division=cast(str, 0.0)))
            else:
                fold_precisions.append(0.0)
                
            folds_evaluated += 1
            
        if not all_y_true:
            return {"precision": 0.0, "recall": 0.0, "signals": 0, "base_rate": 0.0, "pr_auc": 0.0, "folds_evaluated": 0, "precision_std": 0.0}
            
        y_true = np.array(all_y_true)
        y_pred = np.array(all_y_pred)
        y_prob = np.array(all_y_prob)
        
        prec = float(precision_score(y_true, y_pred, zero_division=cast(str, 0.0)))
        rec = float(recall_score(y_true, y_pred, zero_division=cast(str, 0.0)))
        
        try:
            pr_auc = float(average_precision_score(y_true, y_prob))
        except ValueError:
            pr_auc = 0.0
            
        base_rate = float(y_true.mean())
        std_prec = float(np.std(fold_precisions)) if fold_precisions else 0.0
        
        return {
            "precision": prec,
            "recall": rec,
            "pr_auc": pr_auc,
            "base_rate": base_rate,
            "precision_std": std_prec,
            "signals": int(y_pred.sum()),
            "folds_evaluated": folds_evaluated
        }
    return evaluator

def main():
    os.makedirs("data/tmp", exist_ok=True)

    logger.info("Ranking Universe: 2025-06-01 to 2025-12-01")
    conn_master = duckdb.connect(str(DEFAULT_MASTER_DUCKDB), read_only=True)
    
    # Strictly rank coins BEFORE the walk-forward evaluation begins (Lookahead protection)
    top_pump_query = """
    WITH period_data AS (
        SELECT symbol,
               FIRST_VALUE(open) OVER (PARTITION BY symbol ORDER BY close_time ASC) as start_price,
               MAX(high) OVER (PARTITION BY symbol) as period_max_high,
               SUM(quote_volume) OVER (PARTITION BY symbol) as total_vol
        FROM klines_5m
        WHERE close_time >= '2025-06-01' AND close_time < '2025-12-01'
        AND symbol IN (SELECT DISTINCT symbol FROM funding_history)
    )
    SELECT symbol, 
           MAX(period_max_high / NULLIF(start_price, 0)) as pump_factor
    FROM period_data
    GROUP BY symbol, total_vol
    HAVING total_vol > 50000000
    ORDER BY pump_factor DESC
    LIMIT 50
    """
    top_df = conn_master.execute(top_pump_query).df()
    conn_master.close()
    
    top_symbols = top_df["symbol"].tolist()
    
    # HARD GATE: Verify exactly 50 symbols
    if len(top_symbols) != 50:
        logger.error(f"FATAL: Failed to identify 50 valid pump coins. Only found {len(top_symbols)}.")
        sys.exit(1)
        
    logger.info(f"Identified {len(top_symbols)} Pump Coins. Highest pump factor: {top_df['pump_factor'].max():.2f}x")
    
    chunk_size = 10
    chunks = [top_symbols[i:i + chunk_size] for i in range(0, len(top_symbols), chunk_size)]
    
    final_db_path = Path("artifacts/backtest_results_all.duckdb")
    if final_db_path.exists():
        final_db_path.unlink()
        
    final_conn = duckdb.connect(str(final_db_path))
    
    for idx, chunk in enumerate(chunks, 1):
        logger.info(f"Processing Chunk {idx}/{len(chunks)} ({len(chunk)} coins)...")
        config = BacktestRunConfig(
            start_date="2025-12-01",
            end_date="2026-08-15",
            horizon_hours=24,
            symbols=chunk,
            output_db_path="artifacts/backtest_results_chunk.duckdb"
        )
        
        chunk_db = Path(config.output_db_path)
        if chunk_db.exists():
            chunk_db.unlink()
            
        runner = FullBacktestRunner(config)
        runner.run()
        
        final_conn.execute(f"ATTACH '{str(chunk_db)}' AS chunk_db (READ_ONLY)")
        
        if idx == 1:
            final_conn.execute("CREATE TABLE bt_combined_all AS SELECT f.*, l.label_value AS is_distribution FROM chunk_db.bt_features f JOIN chunk_db.bt_labels l ON f.symbol = l.symbol AND f.feature_time = l.signal_time WHERE l.label_value IS NOT NULL")
        else:
            final_conn.execute("INSERT INTO bt_combined_all SELECT f.*, l.label_value AS is_distribution FROM chunk_db.bt_features f JOIN chunk_db.bt_labels l ON f.symbol = l.symbol AND f.feature_time = l.signal_time WHERE l.label_value IS NOT NULL")
            
        final_conn.execute("DETACH chunk_db")
        chunk_db.unlink()
        
    logger.info("Detecting completely NULL columns to safely construct view...")
    null_cols = []
    for c in ALL_FEATURES:
        try:
            row_res = final_conn.execute(f"SELECT COUNT(*) FROM bt_combined_all WHERE {c} IS NOT NULL").fetchone()
            cnt = row_res[0] if row_res else 0
            if cnt == 0:
                null_cols.append(c)
        except Exception:
            null_cols.append(c)
            
    active_features = [c for c in ALL_FEATURES if c not in null_cols]
    
    valid_conds = " AND ".join([f"{c} IS NOT NULL" for c in active_features])
    final_conn.execute(f"CREATE OR REPLACE VIEW bt_combined AS SELECT * FROM bt_combined_all WHERE {valid_conds}")
    
    # HARD GATE: Verify 30 symbols survived the null filtering
    final_syms_row = final_conn.execute("SELECT COUNT(DISTINCT symbol) FROM bt_combined").fetchone()
    final_syms = final_syms_row[0] if final_syms_row else 0
    if final_syms < 50:
        logger.error(f"FATAL: Only {final_syms}/50 symbols survived the complete-case filtering. Cannot proceed.")
        sys.exit(1)
        
    row_res = final_conn.execute("SELECT COUNT(*), MIN(feature_time), MAX(feature_time) FROM bt_combined").fetchone()
    if not row_res or row_res[0] == 0:
        logger.error("No data in bt_combined")
        final_conn.close()
        return
        
    count, min_time, max_time = row_res
    logger.info(f"bt_combined rows: {count}, time range: {min_time} to {max_time}")
    
    logger.info(f"Generating Walk-Forward Folds from {min_time} to {max_time}...")
    folds = generate_walk_forward_splits(
        dataset_start=cast(datetime, pd.Timestamp(min_time).to_pydatetime()),
        dataset_end=cast(datetime, pd.Timestamp(max_time).to_pydatetime()),
        train_days=60,
        val_days=1,
        cal_days=15,
        test_days=15,
        step_days=15,
        embargo_hours=48
    )
    logger.info(f"Generated {len(folds)} folds")
    
    if len(folds) == 0:
        logger.error("No folds generated. Check date range and fold sizes.")
        final_conn.close()
        return
        
    evaluator_func = create_evaluator(folds, required_symbols_count=50)
    
    logger.info("Starting Causal Ablation Matrix on Top 50 Pump Coins...")
    results = run_ablation_matrix(final_conn, "bt_combined", evaluator_func)
    final_conn.close()
    
    df_res = pd.DataFrame.from_dict(results, orient='index')
    if not df_res.empty:
        df_res = df_res.sort_values("precision", ascending=False)
        print("\n" + "="*110)
        print(f"{'VARIANT':<20} | {'PRECISION':<10} | {'RECALL':<8} | {'PR-AUC':<8} | {'BASE RATE':<10} | {'STD(P)':<8} | {'FOLDS':<6} | {'SIGNALS'}")
        print("="*110)
        for var, r in df_res.iterrows():
            print(f"{var:<20} | {r['precision']*100:>8.2f}% | {r['recall']*100:>7.2f}% | {r['pr_auc']:.4f}   | {r['base_rate']*100:>8.2f}% | {r['precision_std']*100:>6.2f}% | {r['folds_evaluated']:>5.0f} | {r['signals']}")
        print("="*110)

if __name__ == "__main__":
    main()
