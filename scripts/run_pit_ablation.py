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
from sklearn.metrics import average_precision_score, precision_score, recall_score

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dao_vang.data.historical_adapter import DEFAULT_MASTER_DUCKDB
from dao_vang.experiments.ablation import FEATURE_GROUPS, run_ablation_matrix
from dao_vang.experiments.backtest_runner import BacktestRunConfig, FullBacktestRunner
from dao_vang.validation.splits import generate_walk_forward_splits

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)-8s] %(message)s")
logger = logging.getLogger(__name__)

ALL_FEATURES = [col for cols in FEATURE_GROUPS.values() for col in cols]

def create_evaluator(folds, fold_symbols_map):
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
                
            fold_symbols = fold_symbols_map[idx]
            fold_mask = work["symbol"].isin(fold_symbols)
            
            train_mask = fold_mask & (work["feature_time"] >= pd.Timestamp(f.train.start_time)) & (work["feature_time"] < pd.Timestamp(f.train.end_time))
            cal_mask = fold_mask & (work["feature_time"] >= pd.Timestamp(f.calibration.start_time)) & (work["feature_time"] < pd.Timestamp(f.calibration.end_time))
            test_mask = fold_mask & (work["feature_time"] >= pd.Timestamp(f.test.start_time)) & (work["feature_time"] < pd.Timestamp(f.test.end_time))
            
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
        
        prec = float(precision_score(y_true, y_pred, zero_division=0.0))  # type: ignore
        rec = float(recall_score(y_true, y_pred, zero_division=0.0))  # type: ignore
        
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
    
    # Generate walk forward splits bounds first
    dataset_start = pd.Timestamp("2025-12-01").tz_localize("UTC")
    dataset_end = pd.Timestamp("2026-08-15").tz_localize("UTC")

    logger.info(f"Generating Walk-Forward Folds from {dataset_start} to {dataset_end}...")
    folds = generate_walk_forward_splits(
        dataset_start=cast(datetime, dataset_start.to_pydatetime()),
        dataset_end=cast(datetime, dataset_end.to_pydatetime()),
        train_days=60,
        val_days=1,
        cal_days=15,
        test_days=15,
        step_days=15,
        embargo_hours=48
    )
    
    if not folds:
        logger.error("No folds generated.")
        return

    conn_master = duckdb.connect(str(DEFAULT_MASTER_DUCKDB), read_only=True)
    fold_symbols_map = {}
    all_symbols_set = set()

    for idx, f in enumerate(folds):
        ts_train_start = pd.Timestamp(f.train.start_time)
        if pd.isna(ts_train_start):
            continue
            
        lookback_start = ts_train_start - pd.DateOffset(months=6)  # type: ignore
        
        query = f"""
        WITH period_data AS (
            SELECT symbol,
                   FIRST_VALUE(open) OVER (PARTITION BY symbol ORDER BY close_time ASC) as start_price,
                   MAX(high) OVER (PARTITION BY symbol) as period_max_high,
                   SUM(quote_volume) OVER (PARTITION BY symbol) as total_vol
            FROM klines_5m
            WHERE close_time >= '{lookback_start}' AND close_time < '{ts_train_start}'
            AND symbol IN (SELECT DISTINCT symbol FROM funding_history)
        )
        SELECT symbol
        FROM period_data
        GROUP BY symbol, total_vol
        HAVING total_vol > 50000000
        ORDER BY MAX(period_max_high / NULLIF(start_price, 0)) DESC
        LIMIT 50
        """
        symbols = [r[0] for r in conn_master.execute(query).fetchall()]
        if len(symbols) != 50:
            logger.error(f"FATAL: Fold {idx+1} failed to find exactly 50 symbols (found {len(symbols)}). Universe selection failed.")
            sys.exit(1)
            
        fold_symbols_map[idx] = symbols
        all_symbols_set.update(symbols)
        logger.info(f"Fold {idx+1} PIT Universe: {len(symbols)} coins selected.")

    conn_master.close()
    
    all_symbols_list = list(all_symbols_set)
    logger.info(f"Total unique symbols across all folds: {len(all_symbols_list)}")

    chunk_size = 10
    chunks = [all_symbols_list[i:i + chunk_size] for i in range(0, len(all_symbols_list), chunk_size)]
    
    final_db_path = Path("artifacts/backtest_results_pit.duckdb")
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
            
        # The runner automatically handles memory limit and temp directory setup
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
    
    evaluator_func = create_evaluator(folds, fold_symbols_map)
    
    logger.info("Starting Point-In-Time Causal Ablation Matrix...")
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
