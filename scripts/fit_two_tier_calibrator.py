import numpy as np
import pandas as pd
import duckdb
import joblib
from pathlib import Path
from sklearn.isotonic import IsotonicRegression

def compute_ece(y_true, y_prob, n_bins=10):
    bins = np.linspace(0., 1., n_bins + 1)
    binids = np.digitize(y_prob, bins) - 1
    
    bin_sums = np.bincount(binids, weights=y_prob, minlength=len(bins))
    bin_true = np.bincount(binids, weights=y_true, minlength=len(bins))
    bin_total = np.bincount(binids, minlength=len(bins))
    
    nonzero = bin_total != 0
    prob_true = bin_true[nonzero] / bin_total[nonzero]
    prob_pred = bin_sums[nonzero] / bin_total[nonzero]
    
    ece = np.sum(np.abs(prob_true - prob_pred) * (bin_total[nonzero] / np.sum(bin_total)))
    return ece

def main():
    # Use standard dev duckdb path
    db_path = "data/dev.duckdb"
    
    if Path(db_path).exists():
        con = duckdb.connect(db_path)
        query = """
        SELECT 
            p.heuristic_score as total_score, 
            po.label_value as binary_outcome 
        FROM predictions p 
        JOIN prediction_outcomes po ON p.prediction_id = po.prediction_id
        WHERE po.label_value IS NOT NULL
          AND p.heuristic_score IS NOT NULL
        """
        df = con.execute(query).df()
    else:
        df = pd.DataFrame()
    
    if len(df) == 0:
        print("No training data found in DuckDB. Generating synthetic data to fit the model.")
        np.random.seed(42)
        X = np.random.uniform(10, 90, 1000)
        prob = 1.0 / (1.0 + np.exp(-0.075 * (X - 48.0)))
        y = np.random.binomial(1, prob)
    else:
        X = df['total_score'].values
        y = df['binary_outcome'].values
    
    # Calculate old probabilities (static sigmoid)
    old_probs = 1.0 / (1.0 + np.exp(-0.075 * (X - 48.0)))
    old_ece = compute_ece(y, old_probs)
    print(f"Before Calibration ECE: {old_ece:.4f}")
    
    # Fit Isotonic Regression
    calibrator = IsotonicRegression(y_min=0.01, y_max=0.99, out_of_bounds="clip")
    calibrator.fit(X, y)
    
    new_probs = calibrator.transform(X)
    new_ece = compute_ece(y, new_probs)
    print(f"After Calibration ECE: {new_ece:.4f}")
    
    # Save the calibrator
    out_dir = Path("data/artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "two_tier_calibrator.joblib"
    joblib.dump(calibrator, out_path)
    print(f"Calibrator saved to {out_path}")

if __name__ == "__main__":
    main()
