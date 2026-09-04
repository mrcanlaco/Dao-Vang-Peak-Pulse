from __future__ import annotations

from dao_vang.scanner.telegram_selection import select_top_alerts


def _alert(symbol: str, probability: float, **extra: object) -> dict[str, object]:
    return {
        "symbol": symbol,
        "model_probability": probability,
        "quality_status": "valid",
        "data_quality_score": 1.0,
        "total_score": 50.0,
        **extra,
    }


def test_selection_deduplicates_ranks_and_caps_daily_budget() -> None:
    result = select_top_alerts(
        [
            _alert("ethusdt", 0.23),
            _alert("BTCUSDT", 0.25),
            _alert("ETHUSDT", 0.24),
            _alert("SOLUSDT", 0.22),
            _alert("BADUSDT", 0.99, quality_status="invalid"),
        ],
        sent_24h=8,
        daily_limit=10,
        max_per_cycle=5,
        target_min=5,
        coin_sent_counts={"BTCUSDT": 1},
        coin_daily_limit=1,
    )

    assert [item["symbol"] for item in result.selected] == ["ETHUSDT", "SOLUSDT"]
    assert result.projected_24h == 10
    assert result.target_unmet is False
    assert result.candidate_count == 5
    assert result.eligible_count == 2


def test_selection_fails_closed_for_missing_probability_and_reports_shortfall() -> None:
    result = select_top_alerts(
        [
            _alert("BTCUSDT", 0.19),
            {"symbol": "ETHUSDT", "quality_status": "valid"},
            _alert("SOLUSDT", 0.21, quality_status="warning"),
        ],
        sent_24h=0,
        daily_limit=10,
        max_per_cycle=2,
        target_min=5,
    )

    assert [item["symbol"] for item in result.selected] == ["BTCUSDT"]
    assert result.target_unmet is True
    assert result.eligible_count == 1
