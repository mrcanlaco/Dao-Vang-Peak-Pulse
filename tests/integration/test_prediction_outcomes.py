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

def test_materialize_excludes_invalid_and_leaves_missing_pending(tmp_path):
    db = DuckDBQueryLayer(":memory:")
    start = datetime(2024, 1, 1)
    rows = []
    for i in range(73):
        ts = start + timedelta(minutes=5 * i)
        rows.append(
            {
                "symbol": "BTCUSDT",
                "feature_time": ts,
                "close": 100.0,
                "high": 100.0,
                "low": 100.0,
                "quality_status": "invalid" if i == 0 else "valid",
            }
        )
    # Missing data for ETHUSDT (only up to 2 hours)
    for i in range(24):
        ts = start + timedelta(minutes=5 * i)
        rows.append(
            {
                "symbol": "ETHUSDT",
                "feature_time": ts,
                "close": 100.0,
                "high": 100.0,
                "low": 100.0,
                "quality_status": "valid",
            }
        )
    db.conn.register("timeline_df", pd.DataFrame(rows))
    db.conn.execute("CREATE TABLE raw_timeline AS SELECT * FROM timeline_df")

    store = ScanResultStore(str(tmp_path / "predictions.duckdb"))
    
    rec_invalid = PredictionRecord(
        prediction_id="pred-invalid",
        symbol="BTCUSDT",
        signal_time=start,
        horizon_hours=6,
        model_id="bundle-1",
        quality_status="invalid",
        candidate_passed=True,
        state="early_watch",
        tier="WATCH",
        invalidation_time=start + timedelta(hours=6),
    )
    store.save_prediction(rec_invalid)

    rec_missing = PredictionRecord(
        prediction_id="pred-missing",
        symbol="ETHUSDT",
        signal_time=start,
        horizon_hours=6,
        model_id="bundle-1",
        quality_status="valid",
        candidate_passed=True,
        state="early_watch",
        tier="WATCH",
        invalidation_time=start + timedelta(hours=6),
    )
    store.save_prediction(rec_missing)

    resolved = materialize_prediction_outcomes(
        store, db, timeline_table="raw_timeline", horizons=(6,)
    )
    
    # Only the invalid one should be materialized as excluded. The missing one is pending.
    assert resolved == 1
    
    with store._conn() as conn:
        row_invalid = conn.execute(
            "SELECT label_value, outcome_status, exclusion_reason "
            "FROM prediction_outcomes WHERE prediction_id = 'pred-invalid'"
        ).fetchone()
        row_missing = conn.execute(
            "SELECT label_value FROM prediction_outcomes WHERE prediction_id = 'pred-missing'"
        ).fetchone()

    assert row_invalid[0] is None
    assert row_invalid[1] == "excluded"
    assert "invalid" in row_invalid[2]
    
    assert row_missing is None


def test_historical_backlog_and_missing_future_do_not_repeat_metrics_queries():
    from types import SimpleNamespace
    from unittest.mock import Mock

    db = DuckDBQueryLayer(":memory:")
    db.conn.execute("""
        CREATE TABLE raw_timeline AS
        SELECT 'BTCUSDT' AS symbol, t AS feature_time, 100.0 AS close,
            101.0 AS high, 99.0 AS low, 'valid' AS quality_status
        FROM generate_series(TIMESTAMP '2024-01-01', TIMESTAMP '2024-01-01 06:00:00', INTERVAL '5 minutes') AS series(t)
    """)
    base = {"symbol": "BTCUSDT", "horizon_hours": 6, "signal_price": 100.0,
            "label_version": "distribution_short_v1"}
    pending = [{**base, "prediction_id": f"old-{i}", "signal_time": datetime(2023, 1, 1)+timedelta(minutes=5*i)}
               for i in range(1000)]
    pending += [{**base, "prediction_id": "ready", "signal_time": datetime(2024, 1, 1)},
                {**base, "prediction_id": "waiting", "signal_time": datetime(2024, 1, 1, 1)}]
    store = Mock()
    store.pending_predictions.return_value = pending
    store.save_outcome.return_value = True
    metrics = []

    class CountingConnection:
        def execute(self, sql, *args):
            if "signal_klines AS" in sql:
                metrics.append(sql)
            return db.conn.execute(sql, *args)

    assert materialize_prediction_outcomes(store, SimpleNamespace(conn=CountingConnection()), horizons=(6,)) == 1
    assert len(metrics) == 1
    assert store.save_outcome.call_args.args[0] == "ready"
    store.assign_materialized_event_ids.assert_called_once()
    # No pending record was marked as a loss/exclusion simply for being absent.
    assert store.save_outcome.call_count == 1


def test_absent_signal_backlog_does_not_run_label_engine(monkeypatch):
    from unittest.mock import Mock

    db = DuckDBQueryLayer(":memory:")
    db.conn.execute("CREATE TABLE raw_timeline(symbol VARCHAR, feature_time TIMESTAMP)")
    store = Mock()
    store.pending_predictions.return_value = [{"symbol": "BTCUSDT", "signal_time": datetime(2023, 1, 1)}]
    compute = Mock(side_effect=AssertionError("no matching source"))
    monkeypatch.setattr("dao_vang.scanner.outcomes.DistributionLabelEngineV1.compute_all_horizons_to_table", compute)
    assert materialize_prediction_outcomes(store, db) == 0
    compute.assert_not_called()
    store.save_outcome.assert_not_called()
