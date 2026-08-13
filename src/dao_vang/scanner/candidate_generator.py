"""Versioned, high-recall candidate generation.

Candidate generation is a cheap watchlist filter.  It deliberately does not
produce a probability or an action alert; the frozen horizon model and policy
gate make that decision later.  Rules are represented as data so a replay can
report exactly which version and reason admitted each row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

import duckdb
import pandas as pd

from dao_vang.config.settings import ScoringConfig
from dao_vang.scoring.btc_context import BtcContext
from dao_vang.scoring.distribution_scorer import compute_distribution_score

CANDIDATE_POLICY_VERSION = "candidate_v1"


@dataclass(frozen=True)
class CandidatePolicy:
    """Auditable fast-filter policy.

    The defaults are intentionally permissive (5% move, 8% from high) because
    recall is the primary objective at this stage.  Raising these thresholds
    must be justified by an event-recall report, not only row reduction.
    """

    version: str = CANDIDATE_POLICY_VERSION
    min_pump_return: float = 0.05
    near_high_distance: float = -0.08
    weak_momentum_deceleration: float = -0.01
    derivatives_zscore: float = 2.0
    oi_unwind_return: float = -0.05
    min_heuristic_score: float = 35.0
    min_data_quality_score: float = 0.8
    max_feature_age_minutes: float | None = None


@dataclass(frozen=True)
class CandidateDecision:
    symbol: str
    feature_time: Any
    passed: bool
    reason_codes: tuple[str, ...]
    heuristic_score: float | None
    policy_version: str


class _NeutralBtcContext:
    regime = "NEUTRAL"
    score_adjustment = 0.0
    explanation = ""
    btc_ret_24h = 0.0
    btc_ret_4h = 0.0
    btc_ret_1h = 0.0


def _number(features: Mapping[str, Any], name: str, default: float = 0.0) -> float:
    value = features.get(name, default)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return default if pd.isna(result) else result


def _quality_passes(features: Mapping[str, Any], policy: CandidatePolicy) -> bool:
    status = str(features.get("quality_status", "valid")).lower().split(".")[-1]
    if status not in {"valid", "warning"}:
        return False
    quality = _number(
        features, "data_quality_score", 1.0 if status == "valid" else 0.75
    )
    if quality < policy.min_data_quality_score:
        return False
    if policy.max_feature_age_minutes is None:
        return True
    stamp = features.get("feature_time", features.get("timestamp"))
    if stamp is None:
        return False
    try:
        parsed = pd.Timestamp(stamp)
        if parsed.tzinfo is None:
            parsed = parsed.tz_localize("UTC")
        age = (
            pd.Timestamp(datetime.now(timezone.utc)) - parsed.tz_convert("UTC")
        ).total_seconds() / 60.0
    except (TypeError, ValueError, OverflowError):
        return False
    return 0.0 <= age <= policy.max_feature_age_minutes


def decide_candidate(
    features: Mapping[str, Any],
    config: ScoringConfig,
    *,
    policy: CandidatePolicy | None = None,
    btc_context: BtcContext | Any | None = None,
    pump_pct: float | None = None,
    min_pump_pct: float | None = None,
    min_score: float | None = None,
) -> CandidateDecision:
    """Apply the candidate rules to one latest snapshot."""

    resolved = policy or CandidatePolicy()
    if min_pump_pct is not None:
        resolved = CandidatePolicy(
            **{
                **resolved.__dict__,
                "min_pump_return": float(min_pump_pct),
            }
        )
    if min_score is not None:
        resolved = CandidatePolicy(
            **{**resolved.__dict__, "min_heuristic_score": float(min_score)}
        )

    symbol = str(features.get("symbol", ""))
    reasons: list[str] = []
    if not _quality_passes(features, resolved):
        reasons.append("quality_gate_failed")

    pump = _number(features, "price_ret_24h") if pump_pct is None else float(pump_pct)
    pump_pass = pump >= resolved.min_pump_return
    if pump_pass:
        reasons.append("pump_or_price_return")

    near_high = (
        _number(features, "distance_from_high_24h") >= resolved.near_high_distance
    )
    weak_momentum = (
        _number(features, "momentum_deceleration_4h")
        <= resolved.weak_momentum_deceleration
    )
    derivatives = (
        _number(features, "funding_zscore_30d") >= resolved.derivatives_zscore
        or _number(features, "oi_change_24h") <= resolved.oi_unwind_return
        or _number(features, "top_long_short_position_ratio") >= 1.5
    )
    if near_high:
        reasons.append("near_high")
    if weak_momentum:
        reasons.append("momentum_weakening")
    if derivatives:
        reasons.append("derivatives_abnormal")

    score_value: float | None = None
    try:
        score = compute_distribution_score(
            symbol=symbol,
            features=dict(features),
            btc=btc_context or _NeutralBtcContext(),
            config=config,
            pump_pct=pump,
        )
        score_value = float(score.total_score)
    except (TypeError, ValueError, KeyError):
        # Candidate generation must remain available when a non-critical
        # optional feature is absent.  The model quality gate handles required
        # features later.
        score_value = None
    score_pass = score_value is not None and score_value >= resolved.min_heuristic_score
    if score_pass:
        reasons.append("heuristic_score")

    passed = (
        "quality_gate_failed" not in reasons
        and pump_pass
        and (near_high or weak_momentum or derivatives or score_pass)
    )
    if not passed:
        reasons.append("candidate_rejected")
    return CandidateDecision(
        symbol=symbol,
        feature_time=features.get("feature_time", features.get("timestamp")),
        passed=passed,
        reason_codes=tuple(dict.fromkeys(reasons)),
        heuristic_score=score_value,
        policy_version=resolved.version,
    )


def _latest_rows(db: duckdb.DuckDBPyConnection, timeline_table: str) -> pd.DataFrame:
    """Read one latest row per symbol from the caller-owned connection."""

    # Table names are controlled by the CLI/config, not user-entered values.
    # Reject unsafe identifiers here rather than interpolating arbitrary SQL.
    if not timeline_table.replace("_", "").isalnum():
        raise ValueError("timeline_table must be a simple identifier")
    query = f"""
        WITH latest AS (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY symbol ORDER BY feature_time DESC
            ) AS rn
            FROM {timeline_table}
        )
        SELECT * FROM latest WHERE rn = 1
    """
    return db.execute(query).df()


def generate_candidate_decisions(
    db: duckdb.DuckDBPyConnection,
    timeline_table: str,
    config: ScoringConfig,
    *,
    policy: CandidatePolicy | None = None,
    min_pump_pct: float | None = None,
    min_score: float | None = None,
) -> list[CandidateDecision]:
    """Generate auditable decisions for the latest row of every symbol."""

    return [
        decide_candidate(
            row.to_dict(),
            config,
            policy=policy,
            min_pump_pct=min_pump_pct,
            min_score=min_score,
        )
        for _, row in _latest_rows(db, timeline_table).iterrows()
    ]


def generate_candidates(
    db: duckdb.DuckDBPyConnection,
    timeline_table: str,
    config: ScoringConfig,
    min_pump_pct: float = 0.05,
    min_score: float = 40.0,
) -> list[str]:
    """Return symbols admitted to the high-recall watchlist.

    ``min_pump_pct`` and ``min_score`` remain positional-compatible with the
    original helper.  For new code, pass a ``CandidatePolicy`` and persist its
    ``version`` alongside the candidate decisions.
    """

    decisions = generate_candidate_decisions(
        db,
        timeline_table,
        config,
        min_pump_pct=min_pump_pct,
        min_score=min_score,
    )
    return list(dict.fromkeys(d.symbol for d in decisions if d.passed and d.symbol))


def candidate_event_metrics(
    candidates: Iterable[str],
    events: Iterable[str] | pd.DataFrame,
    *,
    symbol_column: str = "symbol",
) -> dict[str, float | int]:
    """Compute candidate event recall and row reduction without fake labels.

    ``events`` may be an iterable of event symbols or a DataFrame containing a
    symbol column.  The report is descriptive and does not claim the internal
    80% target unless observed in the supplied data.
    """

    candidate_set = {str(value) for value in candidates}
    if isinstance(events, pd.DataFrame):
        if symbol_column not in events.columns:
            raise ValueError(f"events missing {symbol_column!r}")
        event_symbols = {
            str(value) for value in events[symbol_column].dropna().tolist()
        }
        total_rows = len(events)
    else:
        event_symbols = {str(value) for value in events}
        total_rows = len(event_symbols)
    caught = event_symbols & candidate_set
    recall = len(caught) / len(event_symbols) if event_symbols else 0.0
    reduction = 1.0 - len(candidate_set) / total_rows if total_rows else 0.0
    return {
        "candidate_count": len(candidate_set),
        "event_count": len(event_symbols),
        "caught_event_count": len(caught),
        "event_recall": float(recall),
        "reduction_ratio": float(max(0.0, reduction)),
    }


# Descriptive alias used by reports.
evaluate_candidate_recall = candidate_event_metrics
