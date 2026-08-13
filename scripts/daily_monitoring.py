import duckdb
from datetime import timedelta
import json
from pathlib import Path
from dao_vang.monitoring.report import collect_operational_metrics
from dao_vang.domain.time import system_now

def generate_daily_monitoring_report(db_path: str, out_dir: Path):
    db = duckdb.connect(db_path, read_only=True)
    now = system_now()
    day_ago = now - timedelta(days=1)
    
    out_dir.mkdir(parents=True, exist_ok=True)
    report_file = out_dir / f"monitoring_{now.strftime('%Y%m%d')}.md"
    
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(f"# Daily Monitoring Report ({now.strftime('%Y-%m-%d')})\n\n")
        
        # 1. Heartbeat & Latency (from scan_results)
        try:
            latency_df = db.execute(f"""
                SELECT 
                    COUNT(DISTINCT cycle) as cycles_run,
                    COUNT(DISTINCT symbol) as unique_symbols,
                    MIN(scan_time) as first_scan,
                    MAX(scan_time) as last_scan
                FROM scan_results
                WHERE scan_time >= '{day_ago.isoformat()}'
            """).df()
            f.write("## 1. Scanner Heartbeat\n")
            f.write(latency_df.to_markdown(index=False) + "\n\n")
        except Exception as e:
            f.write(f"## 1. Scanner Heartbeat\nError: {e}\n\n")

        # 2. Missing/Stale Rate
        try:
            quality_df = db.execute(f"""
                SELECT 
                    quality_status,
                    COUNT(*) as count
                FROM raw_timeline
                WHERE feature_time >= '{day_ago.isoformat()}'
                GROUP BY quality_status
            """).df()
            f.write("## 2. Data Quality (Last 24h)\n")
            f.write(quality_df.to_markdown(index=False) + "\n\n")
        except Exception as e:
            f.write(f"## 2. Data Quality\nError: {e}\n\n")
            
        # 3. Predictions Distribution
        try:
            pred_df = db.execute(f"""
                SELECT 
                    recommendation,
                    COUNT(*) as count,
                    ROUND(AVG(model_probability), 4) as avg_prob
                FROM scan_results
                WHERE scan_time >= '{day_ago.isoformat()}'
                GROUP BY recommendation
            """).df()
            f.write("## 3. Predictions Distribution\n")
            f.write(pred_df.to_markdown(index=False) + "\n\n")
        except Exception as e:
            f.write(f"## 3. Predictions Distribution\nError: {e}\n\n")
            
        # 4. Materialization Backlog
        try:
            backlog_df = db.execute(f"""
                SELECT 
                    COUNT(*) as pending_outcomes
                FROM alert_history
                WHERE hit IS NULL AND invalidation_time <= '{now.isoformat()}'
            """).df()
            f.write("## 4. Outcome Materialization Backlog\n")
            f.write(backlog_df.to_markdown(index=False) + "\n\n")
        except Exception as e:
            f.write(f"## 4. Outcome Materialization Backlog\nError: {e}\n\n")

        # Sprint 6/7 operational contract.  This is deliberately additive to
        # the legacy dashboard sections; when the prediction tables do not
        # exist the report says ``partial`` instead of inventing a KPI.
        db_root = Path(db_path).resolve().parent
        metrics = collect_operational_metrics(
            db_path,
            heartbeat_path=db_root / "scanner_heartbeat.json",
            kill_switch_path=db_root / "scanner_kill_switch.json",
            mode="shadow",
        )
        f.write("## 5. Shadow/Canary Operations\n")
        f.write(f"- Evidence status: **{metrics['evidence_status']}**\n")
        f.write(f"- Health: **{metrics['health']['status']}**\n")
        f.write(f"- Predictions: {metrics['predictions']}\n")
        f.write(f"- Materialized outcomes: {metrics['outcomes']}\n")
        f.write(f"- Materialized positive events: {metrics['materialized_events']}\n")
        f.write(f"- Pending outcomes: {metrics['pending_outcomes']}\n")
        f.write(f"- Health reasons: {', '.join(metrics['health']['reasons']) or 'none'}\n\n")
        json_file = out_dir / f"monitoring_{now.strftime('%Y%m%d')}.json"
        json_file.write_text(json.dumps(metrics, indent=2, default=str) + "\n", encoding="utf-8")
            
    return report_file

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create a shadow operations report")
    parser.add_argument("--db", default="data/dev.duckdb")
    parser.add_argument("--out-dir", default="reports/monitoring")
    args = parser.parse_args()
    path = generate_daily_monitoring_report(args.db, Path(args.out_dir))
    print(f"Daily monitoring written to {path}")
