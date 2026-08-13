import duckdb
from datetime import timedelta
from pathlib import Path
from dao_vang.domain.time import system_now
from dao_vang.validation.metrics import compute_event_metrics, compute_expected_calibration_error

def generate_weekly_review_report(db_path: str, out_dir: Path):
    db = duckdb.connect(db_path, read_only=True)
    now = system_now()
    week_ago = now - timedelta(days=7)
    
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"weekly_review_{now.strftime('%Y%m%d')}.md"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# Weekly Review Report ({week_ago.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')})\n\n")
        
        # 1. Performance (Precision/Recall)
        try:
            # Use the append-only prediction contract and materialized V1
            # outcomes.  Do not synthesize event IDs from row numbers: rows
            # without an event identity remain unresolved for event recall.
            perf_df = db.execute(f"""
                SELECT
                    p.symbol,
                    p.signal_time,
                    COALESCE(p.calibrated_probability, p.model_probability) AS model_probability,
                    p.threshold,
                    o.label_value,
                    o.target_time,
                    COALESCE(o.event_id, p.event_id) AS event_id,
                    p.prediction_id
                FROM predictions p
                INNER JOIN prediction_outcomes o ON o.prediction_id = p.prediction_id
                WHERE p.signal_time >= '{week_ago.isoformat()}'
                  AND o.label_value IS NOT NULL
            """).df()
            
            if not perf_df.empty:
                perf_df['pred_value'] = (perf_df['model_probability'] >= perf_df['threshold']).astype(int)
                perf_df['label_value'] = perf_df['label_value'].astype(int)
                
                # Mock lead_time
                perf_df['lead_time_minutes'] = (perf_df['target_time'] - perf_df['signal_time']).dt.total_seconds() / 60.0
                
                metrics = compute_event_metrics(perf_df)
                
                # ECE
                ece = compute_expected_calibration_error(perf_df['label_value'].values, perf_df['model_probability'].values)
                
                f.write("## 1. Event Performance (Resolved Outcomes)\n")
                for k, v in metrics.items():
                    f.write(f"- **{k}**: {v}\n")
                f.write(f"- **Expected Calibration Error (ECE)**: {ece}\n\n")
            else:
                f.write("## 1. Event Performance\nNo resolved outcomes in the last 7 days.\n\n")
        except Exception as e:
            f.write(f"## 1. Event Performance\nError: {e}\n\n")

        # 2. Coin Concentration
        try:
            conc_df = db.execute(f"""
                SELECT 
                    symbol,
                    COUNT(*) as alert_count
                FROM alert_history
                WHERE signal_time >= '{week_ago.isoformat()}'
                GROUP BY symbol
                ORDER BY alert_count DESC
                LIMIT 10
            """).df()
            f.write("## 2. Coin Concentration (Top 10)\n")
            f.write(conc_df.to_markdown(index=False) + "\n\n")
        except Exception as e:
            f.write(f"## 2. Coin Concentration\nError: {e}\n\n")
            
    return report_file

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create a materialized shadow weekly review")
    parser.add_argument("--db", default="data/dev.duckdb")
    parser.add_argument("--out-dir", default="reports/monitoring")
    args = parser.parse_args()
    path = generate_weekly_review_report(args.db, Path(args.out_dir))
    print(f"Weekly review written to {path}")
