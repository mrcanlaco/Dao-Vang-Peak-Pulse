from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import numpy as np
from sklearn.linear_model import LogisticRegression

from dao_vang.experiments.forward_test import freeze_model
from dao_vang.experiments.self_learning import run_self_learning
from dao_vang.scanner.scan_results_store import ScanResultStore


def _make_training_db(path: Path, n_rows: int = 250) -> None:
    store = ScanResultStore(str(path))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    features: list[tuple[str, datetime, str, float, float]] = []
    labels: list[int] = []
    for index in range(n_rows):
        signal_time = start + timedelta(minutes=5 * index)
        label = int(index % 5 == 0)
        labels.append(label)
        features.append(
            (
                "BTCUSDT",
                signal_time.replace(tzinfo=None),
                "valid",
                2.0 if label else -2.0,
                float((index % 11) / 10.0),
            )
        )

    with duckdb.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE feature_results (
                symbol VARCHAR,
                feature_time TIMESTAMP,
                quality_status VARCHAR,
                feature_a DOUBLE,
                feature_b DOUBLE
            )
            """
        )
        conn.executemany(
            "INSERT INTO feature_results VALUES (?, ?, ?, ?, ?)", features
        )

    prediction_rows = []
    outcome_rows = []
    for index, label in enumerate(labels):
        signal_time = start + timedelta(minutes=5 * index)
        prediction_id = f"p-{index}"
        prediction_rows.append(
            (
                prediction_id,
                "BTCUSDT",
                signal_time,
                signal_time,
                24,
                "historical-bundle",
                "valid",
                bool(label),
                "early_watch",
                "WATCH",
                False,
                signal_time - timedelta(minutes=1),
            )
        )
        outcome_rows.append(
            (
                prediction_id,
                label,
                signal_time + timedelta(hours=24),
                30.0 if label else None,
                0.01,
                0.02,
                "materialized",
                None,
                signal_time + timedelta(hours=24, minutes=1),
                "distribution_short_v1",
            )
        )

    # Batch insert keeps this fixture fast while using the production schema.
    with store._conn() as conn:  # noqa: SLF001 - fixture setup
        conn.executemany(
            """
            INSERT INTO predictions (
                prediction_id, symbol, signal_time, created_at, horizon_hours,
                model_id, quality_status, candidate_passed, state, tier,
                shadow_mode, invalidation_time
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            prediction_rows,
        )
        conn.executemany(
            """
            INSERT INTO prediction_outcomes (
                prediction_id, label_value, target_time, lead_time_minutes,
                mae, mfe, outcome_status, exclusion_reason, materialized_at,
                outcome_engine_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            outcome_rows,
        )


def _make_champion(artifact_dir: Path) -> str:
    rng = np.random.default_rng(7)
    X = rng.normal(size=(250, 2))
    y = (X[:, 0] > 0).astype(int)
    model = LogisticRegression(max_iter=1000, random_state=7).fit(X, y)
    info = freeze_model(
        model=model,
        threshold=0.99,
        feature_cols=["feature_a", "feature_b"],
        config={"hypothesis_id": "test-champion"},
        train_cutoff=datetime(2025, 12, 31, tzinfo=timezone.utc),
        artifact_dir=artifact_dir,
    )
    return info.model_id


def _make_historical_only_db(path: Path, n_rows: int = 250) -> None:
    """Create labeled history without any live prediction audit rows."""

    store = ScanResultStore(str(path))
    start = datetime(2026, 1, 1)
    features = []
    labels = []
    for index in range(n_rows):
        signal_time = start + timedelta(minutes=5 * index)
        label = int(index % 5 == 0)
        features.append(
            (
                "BTCUSDT",
                signal_time,
                "valid",
                2.0 if label else -2.0,
                float((index % 11) / 10.0),
            )
        )
        labels.append(("BTCUSDT", signal_time, 24, label))

    with duckdb.connect(str(path)) as conn:
        conn.execute(
            """
            CREATE TABLE feature_results (
                symbol VARCHAR,
                feature_time TIMESTAMP,
                quality_status VARCHAR,
                feature_a DOUBLE,
                feature_b DOUBLE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE labels (
                symbol VARCHAR,
                signal_time TIMESTAMP,
                horizon_hours INTEGER,
                label_value INTEGER
            )
            """
        )
        conn.executemany("INSERT INTO feature_results VALUES (?, ?, ?, ?, ?)", features)
        conn.executemany("INSERT INTO labels VALUES (?, ?, ?, ?)", labels)


def test_self_learning_creates_challenger_and_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "self-learning.duckdb"
    artifact_dir = tmp_path / "artifacts"
    _make_training_db(db_path)
    champion_id = _make_champion(artifact_dir)

    kwargs = dict(
        db_path=db_path,
        artifact_dir=artifact_dir,
        champion_model_id=champion_id,
        state_path=artifact_dir / "self_learning" / "state.json",
        report_dir=artifact_dir / "self_learning" / "runs",
        min_training_outcomes=200,
        min_new_outcomes=1,
        min_positive_events=20,
        min_precision_improvement=0.0,
        max_recall_regression=1.0,
        max_brier_regression=1.0,
    )
    result = run_self_learning(**kwargs)

    assert result["status"] == "challenger_ready"
    assert result["challenger_model_id"]
    assert result["promotion"]["promoted"] is False
    assert Path(result["report_path"]).exists()
    assert result["challenger_model_id"] != champion_id

    repeated = run_self_learning(**kwargs)
    assert repeated["status"] == "skipped"


def test_self_learning_waits_for_minimum_outcomes(tmp_path: Path) -> None:
    db_path = tmp_path / "small.duckdb"
    artifact_dir = tmp_path / "artifacts"
    _make_training_db(db_path, n_rows=40)
    champion_id = _make_champion(artifact_dir)

    result = run_self_learning(
        db_path=db_path,
        artifact_dir=artifact_dir,
        champion_model_id=champion_id,
        state_path=artifact_dir / "state.json",
        report_dir=artifact_dir / "runs",
        min_training_outcomes=200,
        min_new_outcomes=1,
        min_positive_events=2,
    )

    assert result["status"] == "not_ready"
    assert result["reason"] == "insufficient_materialized_outcomes"


def test_self_learning_bootstraps_from_historical_labels(tmp_path: Path) -> None:
    db_path = tmp_path / "historical-only.duckdb"
    artifact_dir = tmp_path / "artifacts"
    _make_historical_only_db(db_path)
    champion_id = _make_champion(artifact_dir)

    result = run_self_learning(
        db_path=db_path,
        artifact_dir=artifact_dir,
        champion_model_id=champion_id,
        state_path=artifact_dir / "state.json",
        report_dir=artifact_dir / "runs",
        min_training_outcomes=200,
        min_new_outcomes=1,
        min_positive_events=20,
        min_precision_improvement=0.0,
        max_recall_regression=1.0,
        max_brier_regression=1.0,
    )

    assert result["status"] == "challenger_ready"
    assert result["readiness"]["historical_outcomes"] == 250
    assert result["readiness"]["live_outcomes"] == 0
    assert result["dataset"]["recent_sample_weight"] == 2.0
