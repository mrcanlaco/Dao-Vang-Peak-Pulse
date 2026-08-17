"""Pure assembly helpers for paired candidate-filter shadow comparisons.

The production daemon decides which symbols v1 actually sends to deep
scoring.  This module mirrors that decision onto the same closed 5-minute
market anchor used by v2, producing two audit rows per eligible opportunity.
It has no network, database, Telegram, or filesystem side effects.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from dao_vang.scanner.candidate_filter_store import (
    FilterAuditDecision,
    FilterMarketObservation,
)
from dao_vang.scanner.candidate_filter_v2 import (
    CandidateV2Decision,
    MarketObservation,
)
from dao_vang.scanner.pump_filter import PumpCandidate


@dataclass(frozen=True)
class CandidateFilterCycleAudit:
    decisions: tuple[FilterAuditDecision, ...]
    observations: tuple[FilterMarketObservation, ...]
    current: dict[str, Any]


def _decision_summary(item: FilterAuditDecision) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "rank": item.rank,
        "rank_score": item.rank_score,
        "stage": item.stage,
        "reason_codes": list(item.reason_codes),
    }


def assemble_candidate_filter_audit(
    *,
    universe_tickers: Sequence[Mapping[str, Any]],
    production_symbols: Iterable[str],
    champion_score_symbols: Iterable[str],
    pump_candidates: Iterable[PumpCandidate],
    challenger_decisions: Iterable[CandidateV2Decision],
    challenger_observations: Iterable[MarketObservation],
    champion_version: str,
    challenger_version: str,
    champion_fallback_all: bool,
) -> CandidateFilterCycleAudit:
    """Pair actual v1 and shadow-v2 decisions on one market observation.

    A symbol without a closed 5-minute observation is excluded from both arms
    instead of inventing a price.  It remains visible in ``data_unavailable``
    so a data outage cannot silently improve either filter's metrics.
    """

    production_values = [str(symbol).strip().upper() for symbol in production_symbols]
    pump_values = list(pump_candidates)
    universe_symbols = [
        str(ticker.get("symbol", "")).strip().upper()
        for ticker in universe_tickers
        if str(ticker.get("symbol", "")).strip()
    ]
    ticker_by_symbol = {
        str(ticker.get("symbol", "")).strip().upper(): ticker
        for ticker in universe_tickers
    }
    production_set = set(production_values)
    champion_selected_set = {
        str(symbol).strip().upper() for symbol in champion_score_symbols
    }
    pumps = {candidate.symbol.upper(): candidate for candidate in pump_values}
    pump_ranks = {
        candidate.symbol.upper(): rank
        for rank, candidate in enumerate(pump_values, start=1)
    }
    production_ranks = {
        symbol.upper(): rank for rank, symbol in enumerate(production_values, start=1)
    }
    v2_by_symbol = {
        decision.symbol.upper(): decision for decision in challenger_decisions
    }
    observation_by_symbol = {
        observation.symbol.upper(): observation
        for observation in challenger_observations
    }

    audit_decisions: list[FilterAuditDecision] = []
    market_observations: list[FilterMarketObservation] = []
    champion_rows: list[FilterAuditDecision] = []
    challenger_rows: list[FilterAuditDecision] = []
    unavailable_symbols: list[str] = []

    for symbol in universe_symbols:
        observation = observation_by_symbol.get(symbol)
        if observation is None or observation.close <= 0:
            unavailable_symbols.append(symbol)
            continue

        market_observations.append(
            FilterMarketObservation(
                symbol=symbol,
                observed_at=observation.observed_at,
                high=float(observation.high),
                low=float(observation.low),
                close=float(observation.close),
            )
        )

        volume_24h = float(
            ticker_by_symbol.get(symbol, {}).get("quoteVolume", 0) or 0
        )
        pump = pumps.get(symbol)
        v2 = v2_by_symbol.get(symbol)

        # Build V1 Pump Decision
        if pump is not None:
            v1_stage = "PUMP_CANDIDATE"
            v1_reasons = (
                "daily_pump_threshold_met",
                "daily_volume_threshold_met",
                "candidate_selected",
            )
            v1_rank = pump_ranks.get(symbol)
            v1_rank_score = float(pump.pump_pct)
            peak_price = float(pump.peak_price)
            drawdown = (
                max(0.0, 1.0 - float(observation.close) / peak_price)
                if peak_price > 0
                else None
            )
            evidence = ("daily_price_pump", "daily_quote_volume")
            pump_score = float(pump.pump_pct)
            v1_volume = float(pump.quote_volume)
            v1_selected = True
        elif champion_fallback_all and champion_version != "candidate_filter_v2" and symbol in production_set:
            v1_stage = "FALLBACK"
            v1_reasons = (
                "pump_filter_returned_no_candidates",
                "fallback_all_no_champion_candidates",
                "candidate_selected",
            )
            v1_rank = production_ranks.get(symbol)
            v1_rank_score = None
            peak_price = None
            drawdown = None
            evidence = ()
            pump_score = None
            v1_volume = volume_24h
            v1_selected = symbol in champion_selected_set
        else:
            v1_stage = "REJECTED"
            v1_reasons = (
                (
                    "pump_filter_rejected"
                    if symbol in production_set
                    else "initial_universe_gate_rejected"
                ),
                "candidate_rejected",
            )
            v1_rank = None
            v1_rank_score = None
            peak_price = None
            drawdown = None
            evidence = ()
            pump_score = None
            v1_volume = volume_24h
            v1_selected = False

        v1_decision = FilterAuditDecision(
            symbol=symbol,
            filter_version="pump_filter_v1",
            selected=v1_selected,
            stage=v1_stage,
            observed_at=observation.observed_at,
            reference_price=float(observation.close),
            rank=v1_rank if v1_selected else None,
            rank_score=v1_rank_score,
            pump_score=pump_score,
            peak_price=peak_price,
            drawdown_from_peak=drawdown,
            volume_24h_usd=v1_volume,
            evidence_groups=evidence,
            reason_codes=v1_reasons,
        )

        # Build V2 Quant Decision
        if v2 is None:
            v2_decision = FilterAuditDecision(
                symbol=symbol,
                filter_version="candidate_filter_v2",
                selected=False,
                stage="DATA_UNAVAILABLE",
                observed_at=observation.observed_at,
                reference_price=float(observation.close),
                volume_24h_usd=volume_24h,
                reason_codes=("challenger_decision_missing", "candidate_rejected"),
            )
        else:
            v2_decision = FilterAuditDecision(
                symbol=symbol,
                filter_version="candidate_filter_v2",
                selected=bool(v2.selected),
                stage=str(v2.stage),
                observed_at=observation.observed_at,
                reference_price=float(observation.close),
                rank=v2.rank,
                rank_score=float(v2.rank_score),
                pump_score=float(v2.pump_score),
                transition_score=float(v2.transition_score),
                peak_price=v2.peak_price,
                peak_time=v2.peak_time,
                peak_age_hours=v2.peak_age_hours,
                drawdown_from_peak=v2.drawdown_from_peak,
                volume_24h_usd=float(v2.volume_24h_usd),
                evidence_groups=tuple(v2.evidence_groups),
                reason_codes=tuple(v2.reason_codes),
            )

        # Map to Champion & Challenger according to configured versions
        if champion_version == "candidate_filter_v2":
            champion = v2_decision
            # If champion is v2, assign challenger
            if challenger_version == "pump_filter_v1":
                challenger = v1_decision
            else:
                challenger = FilterAuditDecision(
                    symbol=symbol,
                    filter_version=challenger_version,
                    selected=v1_decision.selected,
                    stage=v1_decision.stage,
                    observed_at=v1_decision.observed_at,
                    reference_price=v1_decision.reference_price,
                    rank=v1_decision.rank,
                    rank_score=v1_decision.rank_score,
                    pump_score=v1_decision.pump_score,
                    peak_price=v1_decision.peak_price,
                    drawdown_from_peak=v1_decision.drawdown_from_peak,
                    volume_24h_usd=v1_decision.volume_24h_usd,
                    evidence_groups=v1_decision.evidence_groups,
                    reason_codes=v1_decision.reason_codes,
                )
        else:
            champion = FilterAuditDecision(
                symbol=symbol,
                filter_version=champion_version,
                selected=v1_decision.selected,
                stage=v1_decision.stage,
                observed_at=v1_decision.observed_at,
                reference_price=v1_decision.reference_price,
                rank=v1_decision.rank,
                rank_score=v1_decision.rank_score,
                pump_score=v1_decision.pump_score,
                peak_price=v1_decision.peak_price,
                drawdown_from_peak=v1_decision.drawdown_from_peak,
                volume_24h_usd=v1_decision.volume_24h_usd,
                evidence_groups=v1_decision.evidence_groups,
                reason_codes=v1_decision.reason_codes,
            )
            challenger = FilterAuditDecision(
                symbol=symbol,
                filter_version=challenger_version,
                selected=v2_decision.selected,
                stage=v2_decision.stage,
                observed_at=v2_decision.observed_at,
                reference_price=v2_decision.reference_price,
                rank=v2_decision.rank,
                rank_score=v2_decision.rank_score,
                pump_score=v2_decision.pump_score,
                transition_score=v2_decision.transition_score,
                peak_price=v2_decision.peak_price,
                peak_time=v2_decision.peak_time,
                peak_age_hours=v2_decision.peak_age_hours,
                drawdown_from_peak=v2_decision.drawdown_from_peak,
                volume_24h_usd=v2_decision.volume_24h_usd,
                evidence_groups=v2_decision.evidence_groups,
                reason_codes=v2_decision.reason_codes,
            )

        champion_rows.append(champion)
        audit_decisions.append(champion)
        challenger_rows.append(challenger)
        audit_decisions.append(challenger)

    champion_selected_symbols = {item.symbol for item in champion_rows if item.selected}
    challenger_selected_symbols = {
        item.symbol for item in challenger_rows if item.selected
    }
    overlap = champion_selected_symbols & challenger_selected_symbols
    champion_only = champion_selected_symbols - challenger_selected_symbols
    challenger_only = challenger_selected_symbols - champion_selected_symbols
    paired_symbols = {item.symbol for item in champion_rows}
    neither = paired_symbols - champion_selected_symbols - challenger_selected_symbols

    champion_selected_rows = sorted(
        (item for item in champion_rows if item.selected),
        key=lambda item: (item.rank is None, item.rank or 10**9, item.symbol),
    )
    challenger_selected_rows = sorted(
        (item for item in challenger_rows if item.selected),
        key=lambda item: (item.rank is None, item.rank or 10**9, item.symbol),
    )
    challenger_only_rows = [
        item for item in challenger_selected_rows if item.symbol in challenger_only
    ]

    return CandidateFilterCycleAudit(
        decisions=tuple(audit_decisions),
        observations=tuple(market_observations),
        current={
            "universe_count": len(universe_symbols),
            "paired_count": len(paired_symbols),
            "data_unavailable_count": len(unavailable_symbols),
            "data_unavailable": unavailable_symbols,
            "champion_selected": len(champion_selected_symbols),
            "challenger_selected": len(challenger_selected_symbols),
            "overlap": len(overlap),
            "champion_only": len(champion_only),
            "challenger_only": len(challenger_only),
            "neither": len(neither),
            "selected": {
                "champion": [
                    _decision_summary(item) for item in champion_selected_rows
                ],
                "challenger": [
                    _decision_summary(item) for item in challenger_selected_rows
                ],
                "challenger_only": [
                    _decision_summary(item) for item in challenger_only_rows
                ],
            },
        },
    )


__all__ = ["CandidateFilterCycleAudit", "assemble_candidate_filter_audit"]
