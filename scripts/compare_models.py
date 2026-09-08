import json
import duckdb
import pandas as pd
from pathlib import Path

# Add src to path to use internal functions
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dao_vang.experiments.forward_test import evaluate_frozen, load_frozen_model
from dao_vang.scoring.frozen_inference import load_verified_bundle, FrozenInferenceError

def compare_all_models():
    models_dir = Path("artifacts/frozen_models")
    
    # 1. Find all models and the maximum cutoff
    valid_models = []
    cutoffs = []
    
    for meta_file in models_dir.glob("frozen_*/metadata.json"):
        with open(meta_file) as f:
            meta = json.load(f)
        cutoff = pd.Timestamp(meta["train_cutoff"])
        model_id = meta.get("model_id", meta_file.parent.name)
        
        valid_models.append(model_id)
        cutoffs.append(cutoff)
        
    common_start = max(cutoffs)
    print(f"Common evaluation start time (max cutoff): {common_start}")
    
    # 2. Extract Data from Dev DB
    print("Loading data from dev.duckdb...")
    conn = duckdb.connect("data/dev.duckdb", read_only=True)
    df = conn.execute(
        """
        SELECT f.*, l.label_value AS is_distribution, l.horizon_hours, l.label_version
        FROM feature_results f
        INNER JOIN labels l
            ON f.feature_time = l.signal_time AND f.symbol = l.symbol
        WHERE f.feature_time >= ?
        """,
        [str(common_start)]
    ).df()
    conn.close()
    
    if df.empty:
        print("No data available after common_start.")
        return
        
    print(f"Dataset loaded: {len(df)} rows.")
    
    # 3. Evaluate each model
    results = []
    for model_id in valid_models:
        try:
            info = load_frozen_model(model_id, Path("artifacts"))
            
            # Filter the common dataset to match this model's specific label contract
            horizon = info.label_spec.get("horizon_hours", 24)
            version = info.label_spec.get("version", "distribution_short_v1")
            
            model_df = df[(df["horizon_hours"] == horizon) & (df["label_version"] == version)].copy()
            
            # Force the train_cutoff of info to our common_start so evaluate_frozen uses exactly the shared interval
            info.train_cutoff = str(common_start)
            
            res = evaluate_frozen(model_id, model_df)
            
            if res["status"] == "ok":
                results.append({
                    "model_id": model_id,
                    "precision": res["metrics"]["precision"],
                    "recall": res["metrics"]["recall"],
                    "usable_rows": res["n_evaluated_usable_rows"],
                    "positives": res["n_positive_labels"],
                    "predicted": res["n_predicted_positive"]
                })
            else:
                print(f"Model {model_id} failed evaluation: {res.get('message', res['status'])}")
        except Exception as e:
            print(f"Model {model_id} encountered an error: {e}")

    # 4. Rank Models
    if not results:
        print("No models successfully evaluated.")
        return
        
    df_res = pd.DataFrame(results)
    # Require at least some minimal activity to be ranked
    df_res = df_res[df_res["predicted"] > 0]
    df_res = df_res.sort_values("precision", ascending=False)
    
    print("\n" + "="*80)
    print(f"{'MODEL ID':<35} | {'PRECISION':<10} | {'RECALL':<8} | {'PREDICTED':<10}")
    print("="*80)
    for _, row in df_res.iterrows():
        print(f"{row['model_id']:<35} | {row['precision']*100:>8.2f}% | {row['recall']*100:>7.2f}% | {row['predicted']:>10.0f}")
        
if __name__ == "__main__":
    compare_all_models()
