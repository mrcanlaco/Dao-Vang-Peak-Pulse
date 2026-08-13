from __future__ import annotations

from datetime import datetime, timedelta, timezone

from dao_vang.scanner.scan_results_store import (
    PredictionRecord,
    ScanResultRecord,
    ScanResultStore,
)


def test_prediction_store_is_append_only_and_materialization_idempotent(tmp_path):
    store = ScanResultStore(str(tmp_path / "predictions.duckdb"))
    signal_time = datetime.now(timezone.utc) - timedelta(hours=7)
    record = PredictionRecord(
        prediction_id="prediction-1",
        symbol="BTCUSDT",
        signal_time=signal_time,
        horizon_hours=6,
        model_id="bundle-1",
        quality_status="valid",
        candidate_passed=True,
        state="early_watch",
        tier="WATCH",
        invalidation_time=signal_time + timedelta(hours=6),
    )
    assert store.save_prediction(record)
    assert store.save_prediction(record)
    assert len(store.pending_predictions()) == 1
    assert store.save_outcome(
        record.prediction_id,
        label_value=0,
        target_time=None,
        lead_time_minutes=None,
        mae=0.02,
        mfe=-0.03,
        outcome_status="materialized",
        exclusion_reason=None,
        outcome_engine_version="distribution_short_v1",
    )
    assert store.save_outcome(
        record.prediction_id,
        label_value=1,
        target_time=None,
        lead_time_minutes=None,
        mae=0.01,
        mfe=-0.02,
        outcome_status="materialized",
        exclusion_reason=None,
        outcome_engine_version="distribution_short_v1",
    )
    stats = store.materialization_stats()
    assert stats["predictions"] == 1
    assert stats["outcomes"] == 1
    assert stats["pending"] == 0


def test_materialized_positive_outcomes_receive_event_ids(tmp_path):
    store = ScanResultStore(str(tmp_path / "events.duckdb"))
    base = datetime.now(timezone.utc) - timedelta(hours=8)
    rows = [
        ("prediction-a", base),
        ("prediction-b", base + timedelta(minutes=30)),
        ("prediction-c", base + timedelta(hours=2)),
    ]
    for prediction_id, signal_time in rows:
        record = PredictionRecord(
            prediction_id=prediction_id,
            symbol="BTCUSDT",
            signal_time=signal_time,
            horizon_hours=6,
            model_id="bundle-1",
            quality_status="valid",
            candidate_passed=True,
            state="confirmed_distribution",
            tier="HIGH_CONFIDENCE",
            invalidation_time=signal_time + timedelta(hours=6),
        )
        assert store.save_prediction(record)
        assert store.save_outcome(
            prediction_id,
            label_value=1,
            target_time=signal_time + timedelta(minutes=30),
            lead_time_minutes=30.0,
            mae=0.01,
            mfe=-0.02,
            outcome_status="materialized",
            exclusion_reason=None,
            outcome_engine_version="distribution_short_v1",
        )

    assert store.assign_materialized_event_ids(gap_minutes=60) == 3
    with store._conn() as conn:  # noqa: SLF001 - verify persisted audit metadata
        event_ids = conn.execute(
            "SELECT event_id FROM prediction_outcomes ORDER BY prediction_id"
        ).fetchall()
    assert event_ids[0][0] == event_ids[1][0]
    assert event_ids[2][0] != event_ids[0][0]


def test_latest_predictions_per_symbol_exposes_latest_delivery(tmp_path):
    store = ScanResultStore(str(tmp_path / "latest.duckdb"))
    now = datetime.now(timezone.utc)
    older = PredictionRecord(
        prediction_id="prediction-old",
        symbol="ETHUSDT",
        signal_time=now - timedelta(minutes=10),
        created_at=now - timedelta(minutes=9),
        horizon_hours=6,
        model_id="bundle-1",
        quality_status="valid",
        candidate_passed=True,
        state="early_watch",
        tier="WATCH",
        calibrated_probability=0.61,
        invalidation_time=now + timedelta(hours=6),
    )
    latest = PredictionRecord(
        prediction_id="prediction-latest",
        symbol="ETHUSDT",
        signal_time=now - timedelta(minutes=5),
        created_at=now - timedelta(minutes=4),
        horizon_hours=6,
        model_id="bundle-1",
        quality_status="valid",
        candidate_passed=True,
        state="early_watch",
        tier="WATCH",
        calibrated_probability=0.72,
        invalidation_time=now + timedelta(hours=6),
    )
    assert store.save_prediction(older)
    assert store.save_prediction(latest)
    store.mark_prediction_telegram_sent(latest.prediction_id)

    rows = store.latest_predictions_per_symbol(limit=10, max_age_hours=24)

    assert len(rows) == 1
    assert rows[0]["prediction_id"] == latest.prediction_id
    assert rows[0]["telegram_sent"] is True


def test_latest_cycle_stats_uses_contiguous_tail_after_daemon_restart(tmp_path):
    store = ScanResultStore(str(tmp_path / "cycles.duckdb"))
    now = datetime.now(timezone.utc)

    store.save_batch([
        ScanResultRecord(now - timedelta(minutes=2), "OLD1", 10.0, "WAIT", cycle=1),
        ScanResultRecord(now - timedelta(minutes=2), "OLD2", 20.0, "SHORT_CANDIDATE", cycle=1),
        ScanResultRecord(now - timedelta(minutes=1), "OLD3", 30.0, "SHORT_CANDIDATE", cycle=2),
    ])
    # A restarted daemon starts counting at cycle=1 again.
    store.save_batch([
        ScanResultRecord(now, "NEW1", 40.0, "SHORT_CANDIDATE", cycle=1),
        ScanResultRecord(now, "NEW2", 15.0, "WAIT", cycle=1),
    ])

    stats = store.latest_cycle_stats()

    assert stats["cycle"] == 1
    assert stats["n_symbols"] == 2
    assert stats["n_alerts"] == 1
