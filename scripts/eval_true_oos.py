import duckdb
import pandas as pd
import numpy as np
import joblib
from sklearn.metrics import precision_score, recall_score, brier_score_loss
import json
from pathlib import Path

def main():
    model_id = "frozen_20260907_064329_9bae597e"
    model_dir = Path("artifacts/frozen_models") / model_id
    
    with open(model_dir / "metadata.json") as f:
        meta = json.load(f)
        
    train_cutoff = meta["train_cutoff"]
    features = meta["feature_cols"]
    threshold = 0.20
    
    print(f"Evaluating {model_id} after {train_cutoff}")
    
    conn = duckdb.connect("artifacts/backtest_results.duckdb", read_only=True)
    df = conn.execute(f"""
        SELECT f.*, l.label_value AS is_distribution
        FROM bt_features f
        JOIN bt_labels l ON f.symbol = l.symbol AND f.feature_time = l.signal_time
        WHERE l.label_value IS NOT NULL AND f.feature_time > '{train_cutoff}'
    """).df()
    conn.close()
    
    df = df.dropna(subset=features + ["is_distribution"])
    if df.empty:
        print("No test data found.")
        return
        
    X = df[features]
    y_true = np.asarray(df["is_distribution"], dtype=int)
    
    model = joblib.load(model_dir / "model.joblib")
    calibrator = joblib.load(model_dir / "calibrator.joblib")
    probs = model.predict(X)
    cal_probs = calibrator.transform(probs)
    
    y_pred = (cal_probs >= threshold).astype(int)
    prec = float(precision_score(y_true, y_pred, zero_division=0.0))
    rec = float(recall_score(y_true, y_pred, zero_division=0.0))
    brier = brier_score_loss(y_true, cal_probs)
    
    print(f"OOS Rows: {len(df)}")
    print(f"Signals: {y_pred.sum()} | Actual Distributions: {y_true.sum()}")
    print(f"OOS Precision: {prec*100:.2f}%")
    print(f"OOS Recall: {rec*100:.2f}%")
    print(f"OOS Brier: {brier:.4f}")

if __name__ == "__main__":
    main()
