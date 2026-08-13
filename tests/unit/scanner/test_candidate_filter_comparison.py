from __future__ import annotations

from datetime import datetime, timezone

from dao_vang.scanner.candidate_filter_comparison import (
    assemble_candidate_filter_audit,
)
from dao_vang.scanner.candidate_filter_v2 import (
    CandidateV2Decision,
    MarketObservation,
)
from dao_vang.scanner.pump_filter import PumpCandidate

UTC = timezone.utc


def _ticker(symbol: str) -> dict[str, str]:
    return {"symbol": symbol, "quoteVolume": "2000000", "lastPrice": "100"}


def _observation(symbol: str) -> MarketObservation:
    return MarketObservation(
        symbol=symbol,
        observed_at=datetime(2026, 8, 13, 8, 0, tzinfo=UTC),
        high=101,
        low=99,
        close=100,
    )


def _v2(symbol: str, selected: bool, rank: int | None = None) -> CandidateV2Decision:
    return CandidateV2Decision(
        symbol=symbol,
        selected=selected,
        stage="DISTRIBUTING" if selected else "PUMPING",
        rank=rank,
        rank_score=0.8 if selected else 0.2,
        reference_price=70,
        peak_price=110,
        volume_24h_usd=2_000_000,
        reason_codes=("candidate_selected" if selected else "candidate_rejected",),
    )


def test_assembles_all_four_paired_strata_on_shared_price() -> None:
    symbols = ["BOTHUSDT", "V1USDT", "V2USDT", "NEITHERUSDT"]
    pump_candidates = [
        PumpCandidate("BOTHUSDT", 0.8, 2, 0.9, 110, 100, 2_000_000),
        PumpCandidate("V1USDT", 0.7, 2, 0.9, 110, 100, 2_000_000),
    ]
    audit = assemble_candidate_filter_audit(
        universe_tickers=[_ticker(symbol) for symbol in symbols],
        production_symbols=symbols,
        champion_score_symbols=["BOTHUSDT", "V1USDT"],
        pump_candidates=pump_candidates,
        challenger_decisions=[
            _v2("BOTHUSDT", True, 1),
            _v2("V1USDT", False),
            _v2("V2USDT", True, 2),
            _v2("NEITHERUSDT", False),
        ],
        challenger_observations=[_observation(symbol) for symbol in symbols],
        champion_version="pump_filter_v1",
        challenger_version="candidate_filter_v2",
        champion_fallback_all=False,
    )

    assert len(audit.decisions) == 8
    assert audit.current["overlap"] == 1
    assert audit.current["champion_only"] == 1
    assert audit.current["challenger_only"] == 1
    assert audit.current["neither"] == 1
    assert {item.reference_price for item in audit.decisions} == {100.0}


def test_champion_fallback_matches_actual_deep_scoring_lane() -> None:
    symbols = ["AAAUSDT", "BBBUSDT"]
    audit = assemble_candidate_filter_audit(
        universe_tickers=[_ticker(symbol) for symbol in symbols],
        production_symbols=symbols,
        champion_score_symbols=symbols,
        pump_candidates=[],
        challenger_decisions=[_v2(symbol, False) for symbol in symbols],
        challenger_observations=[_observation(symbol) for symbol in symbols],
        champion_version="pump_filter_v1",
        challenger_version="candidate_filter_v2",
        champion_fallback_all=True,
    )

    champion = [
        item for item in audit.decisions if item.filter_version == "pump_filter_v1"
    ]
    assert all(item.selected and item.stage == "FALLBACK" for item in champion)
    assert all(
        "fallback_all_no_champion_candidates" in item.reason_codes for item in champion
    )


def test_missing_observation_excludes_both_lanes_and_is_visible() -> None:
    audit = assemble_candidate_filter_audit(
        universe_tickers=[_ticker("AAAUSDT"), _ticker("BBBUSDT")],
        production_symbols=["AAAUSDT", "BBBUSDT"],
        champion_score_symbols=["AAAUSDT"],
        pump_candidates=[],
        challenger_decisions=[_v2("AAAUSDT", True, 1), _v2("BBBUSDT", False)],
        challenger_observations=[_observation("AAAUSDT")],
        champion_version="pump_filter_v1",
        challenger_version="candidate_filter_v2",
        champion_fallback_all=False,
    )

    assert len(audit.decisions) == 2
    assert audit.current["paired_count"] == 1
    assert audit.current["data_unavailable_count"] == 1
    assert audit.current["data_unavailable"] == ["BBBUSDT"]
