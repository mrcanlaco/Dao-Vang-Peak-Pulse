"""Offline v3 replay and immutable evidence ledger; never submits orders.

Consumes point-in-time feature snapshots and 5-minute price/funding paths.
Replay the whole frozen candidate window, not just selected entries: timing is
stateful. Every run is separately identified; repeating a run is idempotent.
"""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from math import isfinite
from pathlib import Path

from dao_vang.labels.dual_outcomes_v3 import evaluate_dual
from dao_vang.labels.engine_v3 import Bar, Funding, aware, evaluate, positive
from dao_vang.labels.specs.distribution_short_v3 import SPEC, TIMING

TIMING_VERSION = TIMING.version
PARENT = "v3_parent_challenger"
SCOUT = "v3_funding_exhaustion_scout"


def canonical(value: object) -> str:
    def encode(item: object) -> str:
        if isinstance(item, datetime):
            aware(item)
            return item.astimezone(timezone.utc).isoformat()
        raise TypeError(f"unsupported JSON value: {type(item)}")

    return json.dumps(
        value, default=encode, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def digest(value: object) -> str:
    return sha256(canonical(value).encode()).hexdigest()


def time_value(value: str) -> datetime:
    timestamp = datetime.fromisoformat(value)
    aware(timestamp)
    return timestamp.astimezone(timezone.utc)


@dataclass
class Episode:
    start: datetime
    previous: datetime
    peak: float = float("-inf")
    consecutive: int = 0
    armed: bool = False
    confirmed: bool = False
    consumed: bool = False


class Timing:
    """Matches the locked research selector, including sticky confirmations.

    A confirmation pair is <=90 minutes apart and remains latched within the
    episode. Pump peak starts at arming (first score>=.39). Cooldown suppresses
    the first qualified event and consumes that episode, as in the old replay.
    These details are versioned rather than silently reinterpreted.
    """

    def __init__(self) -> None:
        self.episodes: dict[str, Episode] = {}
        self.last_entry: dict[str, datetime] = {}

    def decide(self, snapshot: dict) -> tuple[str, str | None]:
        symbol, when = snapshot["symbol"], snapshot["feature_time"]
        pump, score = snapshot["price_ret_24h"], snapshot["score"]
        if snapshot["is_stablecoin"]:
            return "stablecoin", None
        if pump < TIMING.min_return_24h:
            return "outside_universe", None
        episode = self.episodes.get(symbol)
        if episode is None or when - episode.previous > timedelta(
            hours=TIMING.episode_gap_hours
        ):
            episode = Episode(when, when)
            self.episodes[symbol] = episode
        above = score >= TIMING.score_threshold
        gap = when - episode.previous
        contiguous = gap <= timedelta(minutes=TIMING.max_confirmation_gap_minutes)
        is_first = (when == episode.start and episode.consecutive == 0)
        is_hourly = gap >= timedelta(minutes=45)
        if is_first or is_hourly:
            episode.consecutive = (
                episode.consecutive + 1 if above and contiguous and not is_first else int(above)
            )
            episode.confirmed |= episode.consecutive >= TIMING.confirmations
            episode.armed |= above
            episode.previous = when
        if episode.armed:
            episode.peak = max(episode.peak, pump)
        episode_id = f"{symbol}:{episode.start.isoformat()}"
        if episode.consumed:
            return "episode_already_consumed", episode_id
        if not episode.confirmed:
            return "confirmation_pending", episode_id
        if episode.peak < TIMING.min_armed_peak_return_24h:
            return "peak_below_30pct", episode_id
        if when - episode.start < timedelta(hours=TIMING.min_episode_age_hours):
            return "episode_too_young", episode_id
        if score < max(
            0.0,
            round(
                TIMING.score_threshold - TIMING.post_confirmation_score_tolerance, 12
            ),
        ):
            return "score_below_reference_threshold", episode_id
        episode.consumed = True
        last = self.last_entry.get(symbol)
        if last is not None and when - last < timedelta(hours=TIMING.cooldown_hours):
            return "symbol_cooldown", episode_id
        self.last_entry[symbol] = when
        return "selected", episode_id


def scout_gate(snapshot: dict) -> str:
    keys = ("funding_percentile_30d", "funding_persistence_7d", "funding_change_8h")
    if any(snapshot.get(key) is None for key in keys):
        return "funding_features_missing"
    return (
        "selected"
        if snapshot[keys[0]] >= TIMING.scout_percentile_min
        and snapshot[keys[1]] > TIMING.scout_persistence_min_exclusive
        and snapshot[keys[2]] > TIMING.scout_change_min_exclusive
        else "funding_gate_failed"
    )


def reversal_gate(snapshot: dict, threshold: float = -0.02) -> bool:
    """Check if price has confirmed a roll-over of at least abs(threshold) from 24h high."""
    dist = snapshot.get("distance_from_high_24h")
    return dist is not None and dist <= threshold


def champion_gate(snapshot: dict) -> str:
    """Optimal V3 Formula: Climax Pump >= 25% + Reversal Confirmation <= -2% + Funding Scout."""
    pump = snapshot.get("price_ret_24h", 0.0)
    if pump < 0.25:
        return "pump_below_25pct"
    if not reversal_gate(snapshot, -0.02):
        return "reversal_not_confirmed"
    scout_status = scout_gate(snapshot)
    if scout_status != "selected":
        return scout_status
    return "selected"


def normalize_input(payload: dict) -> dict:
    """Validate provenance before any persistent write; no forward feature use."""
    if payload.get("schema_version") != "distribution_v3_replay_v1":
        raise ValueError("unsupported replay schema")
    result = json.loads(canonical(payload))
    provenance = result["provenance"]
    for key in (
        "dataset_id",
        "model_id",
        "model_checksum",
        "feature_schema",
        "score_label_version",
        "data_source",
    ):
        if not isinstance(provenance.get(key), str) or not provenance[key].strip():
            raise ValueError(f"missing provenance: {key}")
    checksum = provenance["model_checksum"]
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ValueError("model_checksum must be SHA-256 hex")
    # This offline adapter cannot certify out-of-sample/sealed status.
    if provenance.get("evidence_kind") not in {"synthetic", "retrospective"}:
        raise ValueError("only synthetic/retrospective evidence is supported")
    previous_by_symbol: dict[str, datetime] = {}
    previous_time: datetime | None = None
    for row in result["snapshots"]:
        symbol = row["symbol"]
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError("symbol must be non-empty")
        when = time_value(row["feature_time"])
        available = time_value(row["features_available_at"])
        if available > when:
            raise ValueError("future feature snapshot is forbidden")
        if when.timestamp() % 300:
            raise ValueError("snapshot must align to a 5-minute close")
        if (
            symbol in previous_by_symbol
            and when <= previous_by_symbol[symbol]
            or previous_time is not None
            and when < previous_time
        ):
            raise ValueError("snapshots must be chronological and unique per symbol")
        previous_by_symbol[symbol] = previous_time = when
        positive(row["signal_price"])
        if not isfinite(row["score"]) or not 0 <= row["score"] <= 1:
            raise ValueError("score must be finite in [0, 1]")
        if not isfinite(row["price_ret_24h"]):
            raise ValueError("price return must be finite")
        if type(row["is_stablecoin"]) is not bool:
            raise ValueError("is_stablecoin must be explicitly boolean")
        for key in (
            "funding_percentile_30d",
            "funding_persistence_7d",
            "funding_change_8h",
        ):
            if row.get(key) is not None and not isfinite(row[key]):
                raise ValueError(f"invalid {key}")
        percentile = row.get("funding_percentile_30d")
        if percentile is not None and not 0 <= percentile <= 1:
            raise ValueError("funding percentile must be in [0, 1]")
        row["feature_time"], row["features_available_at"] = when, available
    return result


def replay(payload: dict) -> dict:
    data = normalize_input(payload)
    timing = Timing()
    events, decisions, evaluations = [], [], []
    for snapshot in data["snapshots"]:
        snapshot = dict(snapshot)
        # Price/funding paths are outcomes, never inputs to the timing selector.
        path = snapshot.pop("path", None)
        event = {"snapshot": snapshot, "provenance": data["provenance"]}
        event_id = digest(event)
        events.append({"event_id": event_id, **event})
        reason, episode_id = timing.decide(snapshot)
        for lane in (PARENT, SCOUT):
            lane_reason = (
                scout_gate(snapshot)
                if lane == SCOUT and reason == "selected"
                else reason
            )
            decisions.append(
                {
                    "event_id": event_id,
                    "lane": lane,
                    "episode_id": episode_id,
                    "selected": lane_reason == "selected",
                    "reason": lane_reason,
                }
            )
        if reason != "selected":
            continue
        path = path or {}
        bars = [
            Bar(
                close_time=time_value(bar["close_time"]),
                **{key: bar[key] for key in ("open", "high", "low", "close")},
            )
            for bar in path.get("bars", [])
        ]
        funding = [
            Funding(time_value(item["timestamp"]), item["rate"], item["mark_price"])
            for item in path.get("funding", [])
        ]
        through = path.get("funding_coverage_through")
        for diagnostic in (False, True):
            if diagnostic:
                # Preserve the historical Entry-1 diagnostic as a separate
                # mode; it is never represented as compact policy evidence.
                outcome = evaluate(
                    signal_time=snapshot["feature_time"],
                    signal_price=snapshot["signal_price"],
                    bars=bars,
                    funding=funding,
                    funding_coverage_through=time_value(through) if through else None,
                    entry1_only=True,
                )
            else:
                outcome = evaluate_dual(
                    signal_time=snapshot["feature_time"],
                    signal_price=snapshot["signal_price"],
                    bars=bars,
                    funding=funding,
                    funding_coverage_through=time_value(through) if through else None,
                )
            evaluations.append({"event_id": event_id, **outcome.to_dict()})
    summary = {}
    primary = {
        row["event_id"]: row for row in evaluations if row["mode"] == "compact_policy"
    }
    for lane in (PARENT, SCOUT):
        lane_decisions = [row for row in decisions if row["lane"] == lane]
        selected = [
            primary[row["event_id"]] for row in lane_decisions if row["selected"]
        ]
        eligible = [row for row in selected if row["eligible"]]
        price_resolved = sum(row["status"] != "incomplete" for row in selected)
        summary[lane] = {
            "candidates": len(lane_decisions),
            "selected": len(selected),
            "resolved_with_costs_and_funding": len(eligible),
            "price_path_resolved": price_resolved,
            "price_path_coverage": price_resolved / len(selected) if selected else None,
            "fully_costed_coverage": len(eligible) / len(selected)
            if selected
            else None,
            "status_counts": dict(Counter(row["status"] for row in selected)),
            "excluded": len(selected) - len(eligible),
            "exclusion_reasons": dict(
                Counter(
                    row["exclusion_reason"] for row in selected if not row["eligible"]
                )
            ),
            "decision_reasons": dict(Counter(row["reason"] for row in lane_decisions)),
            "target_rate": (
                sum(row["label"] for row in eligible) / len(eligible)
                if eligible
                else None
            ),
            "mean_net_return_planned": (
                sum(row["net_return_planned"] for row in eligible) / len(eligible)
                if eligible
                else None
            ),
        }
    run_id = digest({"input": data, "contract": asdict(SPEC), "timing": asdict(TIMING)})
    return {
        "run_id": run_id,
        "input_checksum": digest(data),
        "contract": asdict(SPEC),
        "contract_checksum": SPEC.checksum,
        "timing_version": TIMING_VERSION,
        "timing": asdict(TIMING),
        "provenance": data["provenance"],
        "live_eligible": False,
        "promotion_eligible": False,
        "score_interpretation": "reference_threshold_only_not_v3_calibrated_probability",
        "events": events,
        "decisions": decisions,
        "evaluations": evaluations,
        "summary": summary,
    }


class EvidenceLedger:
    """Transactional, append-only run snapshots, including every fill revision.

    Corrected/extended market data create a new run, not an overwritten result.
    Consumers must select ONE run: never pool reruns as independent evidence.
    """

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with sqlite3.connect(path) as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS v3_runs (
                    run_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v3_events (
                    event_id TEXT PRIMARY KEY, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS v3_decisions (
                    run_id TEXT NOT NULL, event_id TEXT NOT NULL,
                    lane TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, event_id, lane)
                );
                CREATE TABLE IF NOT EXISTS v3_outcomes (
                    run_id TEXT NOT NULL, event_id TEXT NOT NULL,
                    mode TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, event_id, mode)
                );
                CREATE TABLE IF NOT EXISTS v3_fills (
                    run_id TEXT NOT NULL, event_id TEXT NOT NULL,
                    mode TEXT NOT NULL, leg INTEGER NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, event_id, mode, leg)
                );
                CREATE TABLE IF NOT EXISTS v3_funding (
                    run_id TEXT NOT NULL, event_id TEXT NOT NULL,
                    mode TEXT NOT NULL, timestamp TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(run_id, event_id, mode, timestamp)
                );
            """)

    def save(self, result: dict) -> bool:
        """Return True on insertion, False on identical replay; conflict raises."""
        run_id, payload = result["run_id"], canonical(result)
        with sqlite3.connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            old = connection.execute(
                "SELECT payload FROM v3_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if old:
                if old[0] != payload:
                    raise ValueError("immutable run conflict")
                return False
            connection.execute("INSERT INTO v3_runs VALUES (?, ?)", (run_id, payload))
            for event in result["events"]:
                event_id, body = event["event_id"], canonical(event)
                old = connection.execute(
                    "SELECT payload FROM v3_events WHERE event_id=?", (event_id,)
                ).fetchone()
                if old and old[0] != body:
                    raise ValueError("immutable event conflict")
                connection.execute(
                    "INSERT OR IGNORE INTO v3_events VALUES (?, ?)", (event_id, body)
                )
            for row in result["decisions"]:
                connection.execute(
                    "INSERT INTO v3_decisions VALUES (?, ?, ?, ?)",
                    (run_id, row["event_id"], row["lane"], canonical(row)),
                )
            for row in result["evaluations"]:
                key = (run_id, row["event_id"], row["mode"])
                connection.execute(
                    "INSERT INTO v3_outcomes VALUES (?, ?, ?, ?)",
                    (*key, canonical(row)),
                )
                for fill in row["fills"]:
                    connection.execute(
                        "INSERT INTO v3_fills VALUES (?, ?, ?, ?, ?)",
                        (*key, fill["leg"], canonical(fill)),
                    )
                for payment in row["funding_payments"]:
                    connection.execute(
                        "INSERT INTO v3_funding VALUES (?, ?, ?, ?, ?)",
                        (*key, canonical(payment["timestamp"]), canonical(payment)),
                    )
        return True
