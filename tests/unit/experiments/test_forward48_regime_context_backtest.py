from __future__ import annotations

import math

import pandas as pd
import pytest

from scripts.forward48_regime_context_backtest import (
    Config,
    apply_variant,
    assert_unique_keys,
    choose_variant,
    fit_thresholds,
    summarize,
    variants,
)


def _events() -> pd.DataFrame:
    rows = []
    for fold in (1, 2, 3):
        for index in range(10):
            target = index < 6
            rows.append({
                "signal_id": f"{fold}-{index}", "signal_time": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(days=fold, hours=index),
                "fold": fold, "status": "target" if target else "stop",
                "net_return_planned": 0.10 if target else -0.08,
                "btc_regime": "SIDEWAY_DISTRIBUTION" if index < 8 else "TRENDING_BULL",
                "btc_volatility_24h": 0.01 + index / 1000,
                "price_volatility_24h": 0.02 + index / 1000,
                "btc_ret_24h": -0.01 + index / 1000,
                "breadth_positive_24h": index / 10,
                "btc_dominance_proxy_24h": index / 100,
                "price_ret_24h": 0.30,
                "quote_volume_24h": 100_000_000,
                "funding_percentile_30d": index / 10,
                "funding_persistence_7d": 0.001,
                "funding_change_8h": 0.001 if index % 2 else -0.001,
                "oi_change_24h": index / 10,
                "funding_rate_raw": index / 10000,
                "retail_top_spread": index / 100,
            })
    return pd.DataFrame(rows)


def test_summary_uses_identical_baseline_denominators() -> None:
    frame = _events()
    result = summarize(frame.iloc[:15], frame)
    assert result["signals"] == 15
    assert result["signal_coverage_vs_baseline"] == pytest.approx(0.5)
    assert 0 <= result["wilson95_lower"] <= result["target_rate"]
    assert result["sequential_compounded_mdd"] >= 0


def test_thresholds_are_fit_from_passed_development_only() -> None:
    dev = _events()
    thresholds = fit_thresholds(dev)
    assert thresholds["breadth_q50"] == pytest.approx(dev.breadth_positive_24h.quantile(0.5))
    assert thresholds["funding_raw_q80"] == pytest.approx(dev.funding_rate_raw.quantile(0.8))


def test_variant_missing_context_fails_closed() -> None:
    frame = _events()
    frame.loc[0, "btc_regime"] = None
    variant = next(item for item in variants() if item.variant_id == "block_trending_bull")
    selected = apply_variant(frame, variant, fit_thresholds(frame))
    assert frame.loc[0, "signal_id"] not in set(selected.signal_id)


def test_duplicate_keys_rejected() -> None:
    frame = pd.DataFrame({"symbol": ["X", "X"], "time": [1, 1]})
    with pytest.raises(RuntimeError, match="duplicate"):
        assert_unique_keys(frame, ["symbol", "time"], "fixture")


def test_choose_variant_applies_coverage_floors_and_finite_penalty() -> None:
    dev = _events()
    winner, leaderboard, _ = choose_variant(
        dev, Config(min_dev_coverage=0.35, min_dev_signals=10, min_signals_per_dev_fold=2)
    )
    assert winner.variant_id in set(leaderboard.variant_id)
    eligible = leaderboard[leaderboard.eligible]
    assert not eligible.empty
    assert eligible.multiple_testing_ev_penalty.map(math.isfinite).all()
