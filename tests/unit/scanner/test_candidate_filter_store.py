from __future__ import annotations

from datetime import datetime, timedelta, timezone

import duckdb

from dao_vang.scanner.candidate_filter_store import (
    CandidateFilterStore,
    FilterAuditDecision,
    FilterMarketObservation,
)

UTC = timezone.utc


def _decision(
    version: str,
    observed_at: datetime,
    *,
    selected: bool,
    symbol: str = "TESTUSDT",
    rank: int | None = 1,
) -> FilterAuditDecision:
    return FilterAuditDecision(
        symbol=symbol,
        filter_version=version,
        selected=selected,
        stage="DISTRIBUTING" if selected else "REJECTED",
        observed_at=observed_at,
        reference_price=100.0,
        rank=rank,
        rank_score=80.0 if selected else 0.0,
    )


def test_save_cycle_is_idempotent_per_hour_and_keeps_episode() -> None:
    conn = duckdb.connect(":memory:")
    store = CandidateFilterStore()
    start = datetime(2026, 8, 1, 0, 5, tzinfo=UTC)
    store.save_cycle(
        conn,
        decisions=[_decision("v1", start, selected=True)],
        observations=[FilterMarketObservation("TESTUSDT", start, 101, 99, 100)],
        run_id="run-a",
        cycle=1,
    )
    store.save_cycle(
        conn,
        decisions=[_decision("v1", start + timedelta(minutes=20), selected=True)],
        observations=[
            FilterMarketObservation(
                "TESTUSDT", start + timedelta(minutes=5), 101, 98, 99
            )
        ],
        run_id="run-a",
        cycle=2,
    )
    assert (
        conn.execute("SELECT count(*) FROM candidate_filter_decisions").fetchone()[0]
        == 1
    )
    assert (
        conn.execute("SELECT count(*) FROM candidate_market_observations").fetchone()[0]
        == 2
    )
    assert (
        conn.execute("SELECT count(*) FROM candidate_filter_opportunities").fetchone()[
            0
        ]
        == 1
    )

    store.save_cycle(
        conn,
        decisions=[_decision("v1", start + timedelta(hours=1), selected=True)],
        observations=[],
        run_id="run-a",
        cycle=3,
    )
    episodes = conn.execute(
        "SELECT DISTINCT episode_id FROM candidate_filter_decisions"
    ).fetchall()
    assert len(episodes) == 1
    assert episodes[0][0]


def test_resolve_outcome_target_before_adverse_is_positive() -> None:
    conn = duckdb.connect(":memory:")
    store = CandidateFilterStore()
    start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    decisions = [
        _decision("v1", start, selected=True),
        _decision("v2", start, selected=True),
    ]
    observations = []
    for index in range(1, 289):
        stamp = start + timedelta(minutes=5 * index)
        low = 91.5 if index == 12 else 99.0
        observations.append(
            FilterMarketObservation("TESTUSDT", stamp, 101.0, low, 99.0)
        )
    store.save_cycle(
        conn,
        decisions=decisions,
        observations=observations,
        run_id="run-a",
        cycle=1,
    )
    resolved = store.resolve_due_outcomes(
        conn, now=start + timedelta(hours=24, minutes=1)
    )
    assert resolved == 1
    rows = conn.execute(
        "SELECT label_value, outcome_status FROM candidate_filter_outcomes"
    ).fetchall()
    assert rows == [(1, "resolved")]
    opportunity_ids = conn.execute(
        "SELECT DISTINCT opportunity_id FROM candidate_filter_decisions"
    ).fetchall()
    assert len(opportunity_ids) == 1


def test_resolve_outcome_excludes_data_gap() -> None:
    conn = duckdb.connect(":memory:")
    store = CandidateFilterStore()
    start = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
    store.save_cycle(
        conn,
        decisions=[_decision("v1", start, selected=False)],
        observations=[
            FilterMarketObservation(
                "TESTUSDT", start + timedelta(hours=24), 101, 99, 100
            )
        ],
        run_id="run-a",
        cycle=1,
    )
    store.resolve_due_outcomes(conn, now=start + timedelta(hours=25))
    row = conn.execute(
        "SELECT label_value, outcome_status, exclusion_reason "
        "FROM candidate_filter_outcomes"
    ).fetchone()
    assert row == (None, "excluded", "data_gap")


def test_metrics_remain_not_ready_without_enough_outcomes() -> None:
    conn = duckdb.connect(":memory:")
    store = CandidateFilterStore()
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    observations = [
        FilterMarketObservation(
            "TESTUSDT", start + timedelta(minutes=5 * index), 101, 91, 95
        )
        for index in range(1, 289)
    ]
    store.save_cycle(
        conn,
        decisions=[
            _decision("pump_filter_v1", start, selected=False),
            _decision("candidate_filter_v2", start, selected=True),
        ],
        observations=observations,
        run_id="run-a",
        cycle=1,
    )
    store.resolve_due_outcomes(conn, now=start + timedelta(hours=25))
    report = store.comparison_metrics(
        conn,
        champion_version="pump_filter_v1",
        challenger_version="candidate_filter_v2",
        min_resolved=200,
        min_positive_events=30,
    )
    assert report["promotion"]["ready"] is False
    assert report["promotion"]["passed"] is False
    assert "insufficient_resolved_outcomes" in report["promotion"]["reasons"]


def test_metrics_deduplicate_overlapping_positive_anchors_into_truth_event() -> None:
    conn = duckdb.connect(":memory:")
    store = CandidateFilterStore()
    start = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    for cycle, stamp in enumerate((start, start + timedelta(hours=1)), start=1):
        store.save_cycle(
            conn,
            decisions=[
                _decision("pump_filter_v1", stamp, selected=False),
                _decision("candidate_filter_v2", stamp, selected=True),
            ],
            observations=[],
            run_id="run-a",
            cycle=cycle,
        )

    opportunities = conn.execute(
        "SELECT opportunity_id, observed_at "
        "FROM candidate_filter_opportunities ORDER BY observed_at"
    ).fetchall()
    materialized_at = start + timedelta(days=2)
    conn.executemany(
        """
        INSERT INTO candidate_filter_outcomes (
            opportunity_id, label_value, target_time, lead_time_minutes,
            mae, mfe, outcome_status, exclusion_reason, materialized_at,
            outcome_engine_version
        ) VALUES (?, 1, ?, 120, 0.01, -0.10, 'resolved', NULL, ?, 'test')
        """,
        [
            [opportunity_id, observed_at + timedelta(hours=2), materialized_at]
            for opportunity_id, observed_at in opportunities
        ],
    )

    report = store.comparison_metrics(
        conn,
        champion_version="pump_filter_v1",
        challenger_version="candidate_filter_v2",
        min_resolved=2,
        min_positive_events=1,
        min_evaluation_days=0,
        truth_event_gap_minutes=240,
    )

    assert report["promotion"]["positive_anchors"] == 2
    assert report["promotion"]["positive_events"] == 1
    assert report["promotion"]["ready"] is True
    assert report["metrics"]["pump_filter_v1"]["event_recall"] == 0.0
    assert report["metrics"]["candidate_filter_v2"]["event_recall"] == 1.0
    recall_delta = report["paired_deltas"]["event_recall"]
    assert recall_delta["point"] == 1.0
    assert recall_delta["ci_lower"] == 1.0
    assert recall_delta["ci_upper"] == 1.0
