from datetime import datetime, timedelta, timezone

import duckdb

from dao_vang.labels.engine import DistributionLabelEngine


def create_test_db(rows):
    db = duckdb.connect(":memory:")
    db.execute(
        "CREATE TABLE test_data (feature_time TIMESTAMP, open DECIMAL, high DECIMAL, low DECIMAL, close DECIMAL, quality_status VARCHAR)"
    )
    for r in rows:
        db.execute("INSERT INTO test_data VALUES (?, ?, ?, ?, ?, ?)", r)
    return db


def generate_candles(start_time, num_candles, start_price, trend_func):
    """Helper to generate continuous candles"""
    rows = []
    current_time = start_time
    for i in range(num_candles):
        p = trend_func(i, start_price)
        rows.append((current_time, p, p, p, p, "valid"))
        current_time += timedelta(minutes=5)
    return rows


def test_label_positive_clean():
    """Target reached within 24h, MAE <= 4%"""
    start_time = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
    # Signal at P=100
    rows = [(start_time, 100.0, 100.0, 100.0, 100.0, "valid")]
    # Next 10 candles hover around 101 (MAE=1%)
    for i in range(10):
        t = start_time + timedelta(minutes=5 * (i + 1))
        rows.append((t, 101.0, 101.0, 101.0, 101.0, "valid"))
    # Candle 11 drops to 92 (Target = 92)
    t = start_time + timedelta(minutes=5 * 11)
    rows.append((t, 101.0, 101.0, 92.0, 92.0, "valid"))

    # Fill remaining 24h (288 total candles after signal)
    current_time = t
    while current_time < start_time + timedelta(minutes=1440):
        current_time += timedelta(minutes=5)
        rows.append((current_time, 92.0, 92.0, 92.0, 92.0, "valid"))

    db = create_test_db(rows)
    engine = DistributionLabelEngine()
    results = engine.compute_all(db, "test_data")

    assert len(results) == len(rows)
    res = results[0]
    assert res.label_value == 1
    assert res.target_reached is True
    assert res.max_adverse_excursion == 0.01
    assert res.exclusion_reason is None


def test_label_negative_target_missed():
    """Target not reached in 24h"""
    start_time = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
    # Signal at P=100
    rows = [(start_time, 100.0, 100.0, 100.0, 100.0, "valid")]

    # Hover around 95 (never reach 92) for 24h
    current_time = start_time
    for _ in range(288):
        current_time += timedelta(minutes=5)
        rows.append((current_time, 95.0, 95.0, 95.0, 95.0, "valid"))

    db = create_test_db(rows)
    engine = DistributionLabelEngine()
    results = engine.compute_all(db, "test_data")

    res = results[0]
    assert res.label_value == 0
    assert res.target_reached is False
    assert res.exclusion_reason is None


def test_label_negative_mae_breached():
    """MAE exceeded before target is reached"""
    start_time = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
    # Signal at P=100
    rows = [(start_time, 100.0, 100.0, 100.0, 100.0, "valid")]

    # Candle 1: Spike to 105 (MAE > 4%)
    t = start_time + timedelta(minutes=5)
    rows.append((t, 105.0, 105.0, 105.0, 105.0, "valid"))

    # Candle 2: Drop to 90 (Target reached, but MAE already breached)
    t += timedelta(minutes=5)
    rows.append((t, 90.0, 90.0, 90.0, 90.0, "valid"))

    # Fill remaining
    current_time = t
    while current_time < start_time + timedelta(minutes=1440):
        current_time += timedelta(minutes=5)
        rows.append((current_time, 90.0, 90.0, 90.0, 90.0, "valid"))

    db = create_test_db(rows)
    engine = DistributionLabelEngine()
    results = engine.compute_all(db, "test_data")

    res = results[0]
    assert res.label_value == 0
    assert res.target_reached is True  # Target was actually reached!
    assert res.max_adverse_excursion == 0.05
    assert res.exclusion_reason is None


def test_label_ambiguous_intrabar():
    """Target and MAE breached on the same candle, prior MAE <= 4%"""
    start_time = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = [(start_time, 100.0, 100.0, 100.0, 100.0, "valid")]

    # Candle 1: High=105, Low=90. Target and MAE both breached!
    t = start_time + timedelta(minutes=5)
    rows.append((t, 100.0, 105.0, 90.0, 100.0, "valid"))

    current_time = t
    while current_time < start_time + timedelta(minutes=1440):
        current_time += timedelta(minutes=5)
        rows.append((current_time, 100.0, 100.0, 100.0, 100.0, "valid"))

    db = create_test_db(rows)
    engine = DistributionLabelEngine()
    results = engine.compute_all(db, "test_data")

    res = results[0]
    assert res.label_value is None
    assert res.target_reached is True
    assert res.exclusion_reason == "ambiguous_intrabar"


def test_label_missing_future_data():
    """End of data before 24h"""
    start_time = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = [(start_time, 100.0, 100.0, 100.0, 100.0, "valid")]

    # Only 10 candles provided
    current_time = start_time
    for _ in range(10):
        current_time += timedelta(minutes=5)
        rows.append((current_time, 100.0, 100.0, 100.0, 100.0, "valid"))

    db = create_test_db(rows)
    engine = DistributionLabelEngine()
    results = engine.compute_all(db, "test_data")

    res = results[0]
    assert res.label_value is None
    assert res.exclusion_reason == "missing_future_data"


def test_label_gap_exceeds_threshold():
    """Gap > 15 minutes before 24h"""
    start_time = datetime(2020, 1, 1, 0, 0, tzinfo=timezone.utc)
    rows = [(start_time, 100.0, 100.0, 100.0, 100.0, "valid")]

    # Candle 1
    t = start_time + timedelta(minutes=5)
    rows.append((t, 100.0, 100.0, 100.0, 100.0, "valid"))

    # Candle 2 (Gap = 20 minutes!)
    t += timedelta(minutes=20)
    rows.append((t, 100.0, 100.0, 100.0, 100.0, "valid"))

    # Fill remaining to make sure it's not a missing_future_data error
    current_time = t
    while current_time < start_time + timedelta(minutes=1440):
        current_time += timedelta(minutes=5)
        rows.append((current_time, 100.0, 100.0, 100.0, 100.0, "valid"))

    db = create_test_db(rows)
    engine = DistributionLabelEngine()
    results = engine.compute_all(db, "test_data")

    res = results[0]
    assert res.label_value is None
    assert res.exclusion_reason == "gap_exceeds_threshold"
