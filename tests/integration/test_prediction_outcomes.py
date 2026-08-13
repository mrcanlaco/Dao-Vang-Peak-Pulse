from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.scanner.outcomes import materialize_prediction_outcomes
from dao_vang.scanner.scan_results_store import PredictionRecord, ScanResultStore


def test_materialize_prediction_outcome_uses_v1_label_and_preserves_exclusion(tmp_path):
    db = DuckDBQueryLayer(":memory:")
    start = datetime(2024, 1, 1)
    rows = []
    for i in range(73):  # signal + a complete six-hour 5m horizon
        ts = start + timedelta(minutes=5 * i)
        close = 100.0 if i == 0 else 90.0 if i == 12 else 100.0
        rows.append(
            {
                "symbol": "BTCUSDT",
                "feature_time": ts,
                "close": close,
                "high": close * 1.01,
                "low": close * 0.99 if i != 12 else 90.0,
                "quality_status": "valid",
            }
        )
    db.conn.register("timeline_df", pd.DataFrame(rows))
    db.conn.execute("CREATE TABLE raw_timeline AS SELECT * FROM timeline_df")

    store = ScanResultStore(str(tmp_path / "predictions.duckdb"))
    record = PredictionRecord(
        prediction_id="prediction-v1",
        symbol="BTCUSDT",
        signal_time=start,
        horizon_hours=6,
        model_id="bundle-1",
        quality_status="valid",
        candidate_passed=True,
        state="early_watch",
        tier="WATCH",
        invalidation_time=datetime(2024, 1, 1, 7),
    )
    store.save_prediction(record)
    resolved = materialize_prediction_outcomes(
        store, db, timeline_table="raw_timeline", horizons=(6,)
    )
    assert resolved == 1
    with store._conn() as conn:
        row = conn.execute(
            "SELECT label_value, outcome_status, outcome_engine_version "
            "FROM prediction_outcomes WHERE prediction_id = ?",
            [record.prediction_id],
        ).fetchone()
    assert row == (1, "materialized", "distribution_short_v1")
