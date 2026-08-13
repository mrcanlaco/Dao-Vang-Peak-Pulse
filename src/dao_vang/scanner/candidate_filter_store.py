"""Audit store and outcome metrics for candidate-filter champion/challenger runs.

The live scanner owns DuckDB's writer connection on Windows.  This module
therefore accepts a caller-owned connection for every write and never opens a
second writer.  Decisions are sampled into fixed time buckets while lightweight
market observations are retained every cycle.  That makes rejected symbols
observable and prevents candidate-filter recall from being measured only on
coins a filter already selected.
"""

from __future__ import annotations

import hashlib
import json
import random
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import duckdb

_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_filter_opportunities (
    opportunity_id           VARCHAR PRIMARY KEY,
    run_id                   VARCHAR NOT NULL,
    cycle                    INTEGER NOT NULL,
    observed_at              TIMESTAMPTZ NOT NULL,
    decision_bucket          TIMESTAMPTZ NOT NULL,
    symbol                   VARCHAR NOT NULL,
    reference_price          DOUBLE NOT NULL,
    horizon_hours            INTEGER NOT NULL,
    target_drawdown          DOUBLE NOT NULL,
    max_adverse_excursion    DOUBLE NOT NULL,
    due_at                   TIMESTAMPTZ NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_filter_opportunities_due
    ON candidate_filter_opportunities(due_at, symbol);

CREATE TABLE IF NOT EXISTS candidate_filter_decisions (
    decision_id              VARCHAR PRIMARY KEY,
    opportunity_id           VARCHAR NOT NULL,
    run_id                   VARCHAR NOT NULL,
    cycle                    INTEGER NOT NULL,
    observed_at              TIMESTAMPTZ NOT NULL,
    decision_bucket          TIMESTAMPTZ NOT NULL,
    symbol                   VARCHAR NOT NULL,
    filter_version           VARCHAR NOT NULL,
    selected                 BOOLEAN NOT NULL,
    stage                    VARCHAR NOT NULL,
    rank                     INTEGER,
    rank_score               DOUBLE,
    pump_score               DOUBLE,
    transition_score         DOUBLE,
    reference_price          DOUBLE NOT NULL,
    peak_price               DOUBLE,
    peak_time                TIMESTAMPTZ,
    peak_age_hours           DOUBLE,
    drawdown_from_peak       DOUBLE,
    volume_24h_usd           DOUBLE,
    evidence_groups_json     VARCHAR,
    reason_codes_json        VARCHAR,
    episode_id               VARCHAR,
    horizon_hours            INTEGER NOT NULL,
    target_drawdown          DOUBLE NOT NULL,
    max_adverse_excursion    DOUBLE NOT NULL,
    due_at                   TIMESTAMPTZ NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (opportunity_id, filter_version),
    FOREIGN KEY (opportunity_id)
        REFERENCES candidate_filter_opportunities(opportunity_id)
);
CREATE INDEX IF NOT EXISTS idx_filter_decisions_symbol_time
    ON candidate_filter_decisions(symbol, observed_at DESC);

CREATE TABLE IF NOT EXISTS candidate_market_observations (
    symbol       VARCHAR NOT NULL,
    observed_at  TIMESTAMPTZ NOT NULL,
    high         DOUBLE NOT NULL,
    low          DOUBLE NOT NULL,
    close        DOUBLE NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_candidate_market_time
    ON candidate_market_observations(observed_at, symbol);

CREATE TABLE IF NOT EXISTS candidate_filter_outcomes (
    opportunity_id          VARCHAR PRIMARY KEY,
    label_value             INTEGER,
    target_time             TIMESTAMPTZ,
    lead_time_minutes       DOUBLE,
    mae                     DOUBLE,
    mfe                     DOUBLE,
    outcome_status          VARCHAR NOT NULL,
    exclusion_reason        VARCHAR,
    materialized_at         TIMESTAMPTZ NOT NULL,
    outcome_engine_version  VARCHAR NOT NULL,
    FOREIGN KEY (opportunity_id)
        REFERENCES candidate_filter_opportunities(opportunity_id)
);
CREATE INDEX IF NOT EXISTS idx_candidate_filter_outcome_status
    ON candidate_filter_outcomes(outcome_status, materialized_at);
"""


@dataclass(frozen=True)
class FilterAuditDecision:
    symbol: str
    filter_version: str
    selected: bool
    stage: str
    observed_at: datetime
    reference_price: float
    rank: int | None = None
    rank_score: float | None = None
    pump_score: float | None = None
    transition_score: float | None = None
    peak_price: float | None = None
    peak_time: datetime | None = None
    peak_age_hours: float | None = None
    drawdown_from_peak: float | None = None
    volume_24h_usd: float | None = None
    evidence_groups: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FilterMarketObservation:
    symbol: str
    observed_at: datetime
    high: float
    low: float
    close: float


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _bucket(value: datetime, minutes: int) -> datetime:
    stamp = _as_utc(value)
    width = max(1, int(minutes))
    total_minutes = int(stamp.timestamp() // 60)
    bucket_minutes = total_minutes - (total_minutes % width)
    return datetime.fromtimestamp(bucket_minutes * 60, tz=timezone.utc)


def _stable_id(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = max(0.0, min(1.0, quantile)) * (len(ordered) - 1)
    lower = int(position)
    upper = min(len(ordered) - 1, lower + 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _paired_event_recall_delta_ci(
    event_ids: set[str],
    champion_caught: set[str],
    challenger_caught: set[str],
    *,
    samples: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    ordered = sorted(event_ids)
    if not ordered:
        return {"point": None, "ci_lower": None, "ci_upper": None, "n": 0}
    point = (
        len(challenger_caught & event_ids) - len(champion_caught & event_ids)
    ) / len(ordered)
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(max(1, samples)):
        draw = [ordered[rng.randrange(len(ordered))] for _ in ordered]
        champion = sum(event_id in champion_caught for event_id in draw) / len(draw)
        challenger = sum(event_id in challenger_caught for event_id in draw) / len(draw)
        deltas.append(challenger - champion)
    return {
        "point": point,
        "ci_lower": _percentile(deltas, 0.025),
        "ci_upper": _percentile(deltas, 0.975),
        "n": len(ordered),
    }


def _paired_block_precision_delta_ci(
    daily_counts: dict[str, dict[str, tuple[int, int]]],
    champion_version: str,
    challenger_version: str,
    *,
    samples: int = 10_000,
    seed: int = 42,
) -> dict[str, Any]:
    days = sorted(daily_counts)
    if not days:
        return {
            "point": None,
            "ci_lower": None,
            "ci_upper": None,
            "n_blocks": 0,
        }

    def precision(version: str, selected_days: list[str]) -> float | None:
        positive = sum(
            daily_counts[day].get(version, (0, 0))[0] for day in selected_days
        )
        total = sum(daily_counts[day].get(version, (0, 0))[1] for day in selected_days)
        return positive / total if total else None

    champion_point = precision(champion_version, days)
    challenger_point = precision(challenger_version, days)
    point = (
        challenger_point - champion_point
        if champion_point is not None and challenger_point is not None
        else None
    )
    rng = random.Random(seed)
    deltas: list[float] = []
    for _ in range(max(1, samples)):
        draw = [days[rng.randrange(len(days))] for _ in days]
        champion = precision(champion_version, draw)
        challenger = precision(challenger_version, draw)
        if champion is not None and challenger is not None:
            deltas.append(challenger - champion)
    return {
        "point": point,
        "ci_lower": _percentile(deltas, 0.025),
        "ci_upper": _percentile(deltas, 0.975),
        "n_blocks": len(days),
    }


class CandidateFilterStore:
    """Persist filter decisions, market observations, and resolved outcomes."""

    outcome_engine_version = "candidate_filter_outcome_v1"

    @staticmethod
    def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
        conn.execute(_SCHEMA)

    def save_cycle(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        decisions: Iterable[FilterAuditDecision],
        observations: Iterable[FilterMarketObservation],
        run_id: str,
        cycle: int,
        horizon_hours: int = 24,
        target_drawdown: float = 0.08,
        max_adverse_excursion: float = 0.04,
        decision_interval_minutes: int = 60,
    ) -> dict[str, int]:
        self.ensure_schema(conn)

        observation_rows = []
        for item in observations:
            if item.close <= 0 or item.high <= 0 or item.low <= 0:
                continue
            observation_rows.append(
                [
                    item.symbol,
                    _as_utc(item.observed_at),
                    float(item.high),
                    float(item.low),
                    float(item.close),
                ]
            )
        if observation_rows:
            conn.executemany(
                """
                INSERT INTO candidate_market_observations (
                    symbol, observed_at, high, low, close
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (symbol, observed_at) DO NOTHING
                """,
                observation_rows,
            )

        opportunity_rows: dict[str, list[Any]] = {}
        opportunity_prices: dict[str, float] = {}
        decision_rows = []
        inserted_keys: set[tuple[str, str, datetime]] = set()
        for item in decisions:
            if item.reference_price <= 0:
                continue
            observed_at = _as_utc(item.observed_at)
            bucket = _bucket(observed_at, decision_interval_minutes)
            key = (item.filter_version, item.symbol, bucket)
            if key in inserted_keys:
                continue
            inserted_keys.add(key)

            previous = conn.execute(
                """
                SELECT selected, episode_id, decision_bucket
                FROM candidate_filter_decisions
                WHERE filter_version = ? AND symbol = ? AND decision_bucket < ?
                ORDER BY decision_bucket DESC
                LIMIT 1
                """,
                [item.filter_version, item.symbol, bucket],
            ).fetchone()
            episode_id: str | None = None
            if item.selected:
                previous_is_contiguous = bool(
                    previous
                    and previous[2]
                    and bucket - _as_utc(previous[2])
                    <= timedelta(minutes=decision_interval_minutes * 2)
                )
                if (
                    previous
                    and bool(previous[0])
                    and previous[1]
                    and previous_is_contiguous
                ):
                    episode_id = str(previous[1])
                else:
                    episode_id = _stable_id(
                        "episode", item.filter_version, item.symbol, bucket.isoformat()
                    )

            opportunity_id = _stable_id(
                "opportunity",
                item.symbol,
                bucket.isoformat(),
                int(horizon_hours),
                float(target_drawdown),
                float(max_adverse_excursion),
            )
            due_at = observed_at + timedelta(hours=int(horizon_hours))
            current_price = float(item.reference_price)
            previous_price = opportunity_prices.get(opportunity_id)
            if (
                previous_price is not None
                and abs(previous_price - current_price) > 1e-12
            ):
                raise ValueError(
                    "paired filter decisions must share one reference price"
                )
            opportunity_prices[opportunity_id] = current_price
            opportunity_rows.setdefault(
                opportunity_id,
                [
                    opportunity_id,
                    run_id,
                    int(cycle),
                    observed_at,
                    bucket,
                    item.symbol,
                    current_price,
                    int(horizon_hours),
                    float(target_drawdown),
                    float(max_adverse_excursion),
                    due_at,
                ],
            )
            decision_id = _stable_id("decision", opportunity_id, item.filter_version)
            decision_rows.append(
                [
                    decision_id,
                    opportunity_id,
                    run_id,
                    int(cycle),
                    observed_at,
                    bucket,
                    item.symbol,
                    item.filter_version,
                    bool(item.selected),
                    item.stage,
                    item.rank,
                    item.rank_score,
                    item.pump_score,
                    item.transition_score,
                    float(item.reference_price),
                    item.peak_price,
                    _as_utc(item.peak_time) if item.peak_time else None,
                    item.peak_age_hours,
                    item.drawdown_from_peak,
                    item.volume_24h_usd,
                    json.dumps(list(item.evidence_groups), ensure_ascii=False),
                    json.dumps(list(item.reason_codes), ensure_ascii=False),
                    episode_id,
                    int(horizon_hours),
                    float(target_drawdown),
                    float(max_adverse_excursion),
                    due_at,
                ]
            )

        if opportunity_rows:
            conn.executemany(
                """
                INSERT INTO candidate_filter_opportunities (
                    opportunity_id, run_id, cycle, observed_at,
                    decision_bucket, symbol, reference_price, horizon_hours,
                    target_drawdown, max_adverse_excursion, due_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (opportunity_id) DO NOTHING
                """,
                list(opportunity_rows.values()),
            )
        if decision_rows:
            conn.executemany(
                """
                INSERT INTO candidate_filter_decisions (
                    decision_id, opportunity_id, run_id, cycle, observed_at,
                    decision_bucket, symbol, filter_version, selected, stage,
                    rank, rank_score, pump_score, transition_score,
                    reference_price, peak_price, peak_time, peak_age_hours,
                    drawdown_from_peak, volume_24h_usd, evidence_groups_json,
                    reason_codes_json, episode_id, horizon_hours,
                    target_drawdown, max_adverse_excursion, due_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (decision_id) DO NOTHING
                """,
                decision_rows,
            )
        return {
            "observations_seen": len(observation_rows),
            "opportunities_seen": len(opportunity_rows),
            "decisions_seen": len(decision_rows),
        }

    def resolve_due_outcomes(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        now: datetime,
        gap_tolerance_minutes: int = 15,
        limit: int = 5000,
    ) -> int:
        """Resolve due hourly decisions from the shared five-minute tape."""

        self.ensure_schema(conn)
        pending = conn.execute(
            """
            SELECT p.opportunity_id, p.symbol, p.observed_at, p.due_at,
                   p.reference_price, p.target_drawdown,
                   p.max_adverse_excursion
            FROM candidate_filter_opportunities p
            LEFT JOIN candidate_filter_outcomes o
              ON o.opportunity_id = p.opportunity_id
            WHERE o.opportunity_id IS NULL AND p.due_at <= ?
            ORDER BY p.due_at, p.symbol
            LIMIT ?
            """,
            [_as_utc(now), max(1, int(limit))],
        ).fetchall()
        if not pending:
            return 0

        materialized_at = _as_utc(now)
        output_rows: list[list[Any]] = []
        for (
            opportunity_id,
            symbol,
            observed_at,
            due_at,
            reference_price,
            target_drawdown,
            max_adverse,
        ) in pending:
            future = conn.execute(
                """
                SELECT observed_at, high, low
                FROM candidate_market_observations
                WHERE symbol = ? AND observed_at > ? AND observed_at <= ?
                ORDER BY observed_at
                """,
                [symbol, observed_at, due_at],
            ).fetchall()

            exclusion: str | None = None
            label_value: int | None = None
            target_time: datetime | None = None
            lead_time: float | None = None
            mae: float | None = None
            mfe: float | None = None
            if not future:
                exclusion = "missing_future_data"
            else:
                stamps = [_as_utc(row[0]) for row in future]
                observed_utc = _as_utc(observed_at)
                due_utc = _as_utc(due_at)
                gaps = [
                    (stamps[0] - observed_utc).total_seconds() / 60.0,
                    *[
                        (right - left).total_seconds() / 60.0
                        for left, right in zip(stamps, stamps[1:])
                    ],
                ]
                final_lag = (due_utc - stamps[-1]).total_seconds() / 60.0
                if max([final_lag, *gaps]) > float(gap_tolerance_minutes):
                    exclusion = "data_gap"
                else:
                    price = float(reference_price)
                    target_level = price * (1.0 - float(target_drawdown))
                    adverse_level = price * (1.0 + float(max_adverse))
                    first_target = next(
                        (
                            stamps[i]
                            for i, row in enumerate(future)
                            if float(row[2]) <= target_level
                        ),
                        None,
                    )
                    first_adverse = next(
                        (
                            stamps[i]
                            for i, row in enumerate(future)
                            if float(row[1]) >= adverse_level
                        ),
                        None,
                    )
                    mae = max(float(row[1]) / price - 1.0 for row in future)
                    mfe = min(float(row[2]) / price - 1.0 for row in future)
                    if first_target is not None and first_target == first_adverse:
                        exclusion = "ambiguous_intrabar"
                    elif first_target is not None and (
                        first_adverse is None or first_target < first_adverse
                    ):
                        label_value = 1
                        target_time = first_target
                        lead_time = (first_target - observed_utc).total_seconds() / 60.0
                    else:
                        label_value = 0

            output_rows.append(
                [
                    opportunity_id,
                    label_value,
                    target_time,
                    lead_time,
                    mae,
                    mfe,
                    "excluded" if exclusion else "resolved",
                    exclusion,
                    materialized_at,
                    self.outcome_engine_version,
                ]
            )

        conn.executemany(
            """
            INSERT INTO candidate_filter_outcomes (
                opportunity_id, label_value, target_time, lead_time_minutes,
                mae, mfe, outcome_status, exclusion_reason, materialized_at,
                outcome_engine_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (opportunity_id) DO NOTHING
            """,
            output_rows,
        )
        return len(output_rows)

    def comparison_metrics(
        self,
        conn: duckdb.DuckDBPyConnection,
        *,
        champion_version: str,
        challenger_version: str,
        days: int = 30,
        min_resolved: int = 200,
        min_positive_events: int = 50,
        min_evaluation_days: int = 14,
        truth_event_gap_minutes: int = 240,
        min_challenger_event_recall: float = 0.80,
        precision10_relative_gain: float = 0.10,
        max_recall_regression: float = 0.05,
    ) -> dict[str, Any]:
        """Compute filter metrics with episode-level precision and event recall."""

        self.ensure_schema(conn)
        cutoff = _as_utc(datetime.now(timezone.utc) - timedelta(days=max(1, days)))
        rows = conn.execute(
            """
            SELECT d.filter_version, d.symbol, d.observed_at, d.selected,
                   d.rank, d.episode_id, o.label_value, o.target_time,
                   o.lead_time_minutes, o.mae, o.outcome_status
            FROM candidate_filter_decisions d
            LEFT JOIN candidate_filter_outcomes o
              ON o.opportunity_id = d.opportunity_id
            WHERE d.observed_at >= ?
              AND d.filter_version IN (?, ?)
            ORDER BY d.symbol, d.observed_at, d.filter_version
            """,
            [cutoff, champion_version, challenger_version],
        ).fetchall()
        columns = (
            "filter_version",
            "symbol",
            "observed_at",
            "selected",
            "rank",
            "episode_id",
            "label_value",
            "target_time",
            "lead_time_minutes",
            "mae",
            "outcome_status",
        )
        items = [dict(zip(columns, row)) for row in rows]

        versions = (champion_version, challenger_version)
        metrics: dict[str, dict[str, Any]] = {}
        # The outcome is identical for both versions at a symbol/time anchor.
        baseline: dict[tuple[str, datetime], dict[str, Any]] = {}
        for item in items:
            key = (str(item["symbol"]), _as_utc(item["observed_at"]))
            baseline.setdefault(key, item)
        positive_anchors = {
            key for key, item in baseline.items() if item.get("label_value") == 1
        }
        # Collapse overlapping hourly positive anchors into model-independent
        # truth events. The event key uses only market truth (symbol and first
        # target time), never a filter/model version.
        event_by_anchor: dict[tuple[str, datetime], str] = {}
        event_target: dict[str, datetime] = {}
        last_target_by_symbol: dict[str, datetime] = {}
        current_event_by_symbol: dict[str, str] = {}
        positive_baseline = sorted(
            (
                (key, item)
                for key, item in baseline.items()
                if item.get("label_value") == 1 and item.get("target_time") is not None
            ),
            key=lambda pair: (
                pair[0][0],
                _as_utc(pair[1]["target_time"]),
                pair[0][1],
            ),
        )
        event_gap = timedelta(minutes=max(1, int(truth_event_gap_minutes)))
        for anchor_key, item in positive_baseline:
            symbol = anchor_key[0]
            target = _as_utc(item["target_time"])
            previous_target = last_target_by_symbol.get(symbol)
            event_id = current_event_by_symbol.get(symbol)
            if (
                event_id is None
                or previous_target is None
                or target - previous_target >= event_gap
            ):
                event_id = _stable_id("truth-event", symbol, target.isoformat())
                current_event_by_symbol[symbol] = event_id
                event_target[event_id] = target
            else:
                event_target[event_id] = min(event_target[event_id], target)
            event_by_anchor[anchor_key] = event_id
            last_target_by_symbol[symbol] = target
        positive_events = set(event_target)
        caught_events_by_version: dict[str, set[str]] = {}
        daily_top10_counts: dict[str, dict[str, tuple[int, int]]] = {}

        resolved_baseline = [
            item
            for item in baseline.values()
            if item.get("outcome_status") == "resolved"
            and item.get("label_value") in (0, 1)
        ]
        resolved_times = [_as_utc(item["observed_at"]) for item in resolved_baseline]
        evaluation_days = (
            (max(resolved_times) - min(resolved_times)).total_seconds() / 86400.0
            if len(resolved_times) >= 2
            else 0.0
        )

        for version in versions:
            version_rows = [row for row in items if row["filter_version"] == version]
            resolved = [
                row
                for row in version_rows
                if row.get("outcome_status") == "resolved"
                and row.get("label_value") in (0, 1)
            ]
            selected = [row for row in resolved if bool(row.get("selected"))]
            selected_positive = [row for row in selected if row["label_value"] == 1]
            selected_top10 = [
                row
                for row in selected
                if row.get("rank") is not None and int(row["rank"]) <= 10
            ]
            caught_anchors = {
                (str(row["symbol"]), _as_utc(row["observed_at"]))
                for row in selected_positive
            }
            caught_events = {
                event_by_anchor[key] for key in caught_anchors if key in event_by_anchor
            }
            caught_events_by_version[version] = caught_events
            for row in selected_top10:
                day = _as_utc(row["observed_at"]).date().isoformat()
                by_version = daily_top10_counts.setdefault(day, {})
                positive, total = by_version.get(version, (0, 0))
                by_version[version] = (
                    positive + int(row["label_value"] == 1),
                    total + 1,
                )

            episode_first: dict[str, dict[str, Any]] = {}
            for row in selected:
                episode_id = row.get("episode_id")
                if not episode_id:
                    continue
                current = episode_first.get(str(episode_id))
                if current is None or _as_utc(row["observed_at"]) < _as_utc(
                    current["observed_at"]
                ):
                    episode_first[str(episode_id)] = row
            episode_rows = list(episode_first.values())
            episode_positive = [row for row in episode_rows if row["label_value"] == 1]
            earliest_selected_by_event: dict[str, datetime] = {}
            for row in selected_positive:
                anchor_key = (
                    str(row["symbol"]),
                    _as_utc(row["observed_at"]),
                )
                event_id = event_by_anchor.get(anchor_key)
                if event_id is None:
                    continue
                observed_at = anchor_key[1]
                current = earliest_selected_by_event.get(event_id)
                if current is None or observed_at < current:
                    earliest_selected_by_event[event_id] = observed_at
            lead_times = [
                max(
                    0.0,
                    (event_target[event_id] - observed_at).total_seconds() / 60.0,
                )
                for event_id, observed_at in earliest_selected_by_event.items()
            ]
            calendar_days = max(
                1.0,
                (
                    max(
                        (_as_utc(row["observed_at"]) for row in version_rows),
                        default=cutoff,
                    )
                    - min(
                        (_as_utc(row["observed_at"]) for row in version_rows),
                        default=cutoff,
                    )
                ).total_seconds()
                / 86400.0,
            )
            metrics[version] = {
                "anchors": len(version_rows),
                "resolved": len(resolved),
                "excluded": sum(
                    1 for row in version_rows if row.get("outcome_status") == "excluded"
                ),
                "selected_resolved": len(selected),
                "positive_anchors": len(positive_anchors),
                "positive_events": len(positive_events),
                "anchor_precision": (
                    len(selected_positive) / len(selected) if selected else None
                ),
                "anchor_recall": (
                    len(caught_anchors & positive_anchors) / len(positive_anchors)
                    if positive_anchors
                    else None
                ),
                "event_recall": (
                    len(caught_events & positive_events) / len(positive_events)
                    if positive_events
                    else None
                ),
                "precision_at_10": (
                    sum(1 for row in selected_top10 if row["label_value"] == 1)
                    / len(selected_top10)
                    if selected_top10
                    else None
                ),
                "episodes_resolved": len(episode_rows),
                "episode_precision": (
                    len(episode_positive) / len(episode_rows) if episode_rows else None
                ),
                "median_lead_time_minutes": (
                    statistics.median(lead_times) if lead_times else None
                ),
                "false_candidates_per_day": (
                    sum(1 for row in episode_rows if row["label_value"] == 0)
                    / calendar_days
                ),
            }

        champion = metrics[champion_version]
        challenger = metrics[challenger_version]
        recall_delta_ci = _paired_event_recall_delta_ci(
            positive_events,
            caught_events_by_version.get(champion_version, set()),
            caught_events_by_version.get(challenger_version, set()),
        )
        precision_delta_ci = _paired_block_precision_delta_ci(
            daily_top10_counts,
            champion_version,
            challenger_version,
        )
        positive_count = len(positive_events)
        enough_data = (
            champion["resolved"] >= min_resolved
            and challenger["resolved"] >= min_resolved
            and positive_count >= min_positive_events
            and evaluation_days >= min_evaluation_days
        )
        reasons: list[str] = []
        passed = False
        if not enough_data:
            if (
                champion["resolved"] < min_resolved
                or challenger["resolved"] < min_resolved
            ):
                reasons.append("insufficient_resolved_outcomes")
            if positive_count < min_positive_events:
                reasons.append("insufficient_positive_events")
            if evaluation_days < min_evaluation_days:
                reasons.append("evaluation_window_too_short")
        else:
            champion_p10 = champion["precision_at_10"]
            challenger_p10 = challenger["precision_at_10"]
            champion_recall = champion["event_recall"]
            challenger_recall = challenger["event_recall"]
            precision_gate = (
                champion_p10 is not None
                and challenger_p10 is not None
                and challenger_p10 >= champion_p10 * (1.0 + precision10_relative_gain)
            )
            precision_ci_gate = (
                precision_delta_ci["ci_lower"] is not None
                and precision_delta_ci["ci_lower"] > 0.0
            )
            recall_gate = (
                champion_recall is not None
                and challenger_recall is not None
                and challenger_recall >= champion_recall - max_recall_regression
            )
            recall_ci_gate = (
                recall_delta_ci["ci_lower"] is not None
                and recall_delta_ci["ci_lower"] >= -max_recall_regression
            )
            false_alert_gate = (
                challenger["false_candidates_per_day"]
                <= champion["false_candidates_per_day"]
            )
            absolute_recall_gate = (
                challenger_recall is not None
                and challenger_recall >= min_challenger_event_recall
            )
            if not precision_gate:
                reasons.append("precision_at_10_gate_failed")
            if not precision_ci_gate:
                reasons.append("precision_ci_gate_failed")
            if not recall_gate:
                reasons.append("recall_guardrail_failed")
            if not recall_ci_gate:
                reasons.append("recall_ci_guardrail_failed")
            if not false_alert_gate:
                reasons.append("false_candidate_guardrail_failed")
            if not absolute_recall_gate:
                reasons.append("minimum_event_recall_failed")
            passed = (
                precision_gate
                and precision_ci_gate
                and recall_gate
                and recall_ci_gate
                and false_alert_gate
                and absolute_recall_gate
            )

        return {
            "window_days": max(1, int(days)),
            "evaluation_days": evaluation_days,
            "truth_event_gap_minutes": max(1, int(truth_event_gap_minutes)),
            "champion_version": champion_version,
            "challenger_version": challenger_version,
            "metrics": metrics,
            "paired_deltas": {
                "precision_at_10": precision_delta_ci,
                "event_recall": recall_delta_ci,
                "confidence_level": 0.95,
                "bootstrap_samples": 10_000,
            },
            "promotion": {
                "ready": enough_data,
                "passed": passed,
                "requires_human_approval": True,
                "positive_anchors": len(positive_anchors),
                "positive_events": positive_count,
                "min_resolved": min_resolved,
                "min_positive_events": min_positive_events,
                "min_evaluation_days": min_evaluation_days,
                "min_challenger_event_recall": min_challenger_event_recall,
                "reasons": reasons,
            },
        }


__all__ = [
    "CandidateFilterStore",
    "FilterAuditDecision",
    "FilterMarketObservation",
]
