"""Tests for distribution scorer — 8 signals composite 0-100."""

from __future__ import annotations

from typing import Any

import pytest

from dao_vang.config.settings import ScoringConfig
from dao_vang.scoring.btc_context import BtcContext
from dao_vang.scoring.distribution_scorer import (
    compute_distribution_score,
    score_fake_breakout,
    score_funding_spike,
    score_momentum_exhaustion,
    score_price_volume_divergence,
    score_taker_sell_pressure,
)


@pytest.fixture
def config() -> ScoringConfig:
    return ScoringConfig()


@pytest.fixture
def neutral_btc() -> BtcContext:
    return BtcContext(
        btc_ret_24h=0.0,
        btc_ret_4h=0.0,
        btc_ret_1h=0.0,
        regime="NEUTRAL",
        score_adjustment=50.0,
        explanation="BTC flat — neutral.",
    )


@pytest.fixture
def fomo_btc() -> BtcContext:
    return BtcContext(
        btc_ret_24h=0.08,
        btc_ret_4h=0.03,
        btc_ret_1h=0.01,
        regime="FOMO",
        score_adjustment=10.0,
        explanation="BTC +8% — FOMO risk.",
    )


@pytest.fixture
def weak_btc() -> BtcContext:
    return BtcContext(
        btc_ret_24h=-0.05,
        btc_ret_4h=-0.02,
        btc_ret_1h=-0.01,
        regime="WEAK",
        score_adjustment=90.0,
        explanation="BTC -5% — market weak.",
    )


def _make_features(**overrides: Any) -> dict[str, Any]:
    """Default features with overrides."""
    defaults: dict[str, Any] = {
        "price_ret_24h": 0.5,
        "price_ret_4h": 0.15,
        "price_ret_1h": 0.03,
        "price_ret_5m": 0.005,
        "volume_percentile_24h": 0.2,
        "funding_zscore_30d": 2.5,
        "funding_rate_raw": 0.0008,
        "momentum_deceleration_4h": -0.05,
        "distance_from_high_24h": -0.02,
        "taker_buy_ratio": 0.4,
        "taker_buy_ratio_change_1h": -0.05,
        "oi_change_24h": -0.10,
        "fake_breakout_1h": 0.8,
    }
    defaults.update(overrides)
    return defaults


class TestPriceVolumeDivergence:
    def test_high_divergence(self) -> None:
        """Price +50% with low volume → high score."""
        comp = score_price_volume_divergence(0.5, 0.1)
        assert comp.score > 70
        assert "divergence" in comp.explanation.lower()

    def test_no_divergence(self) -> None:
        """Price +50% with high volume → low score."""
        comp = score_price_volume_divergence(0.5, 0.9)
        assert comp.score < 30

    def test_price_down(self) -> None:
        """Price down → score 0."""
        comp = score_price_volume_divergence(-0.1, 0.1)
        assert comp.score == 0


class TestFundingSpike:
    def test_high_spike(self) -> None:
        """Z-score 3+ → high score."""
        comp = score_funding_spike(3.5, 0.001)
        assert comp.score >= 90

    def test_normal_funding(self) -> None:
        """Z-score 0 → score 0."""
        comp = score_funding_spike(0.0, 0.0001)
        assert comp.score == 0

    def test_moderate_spike(self) -> None:
        """Z-score 2 → score ~60."""
        comp = score_funding_spike(2.0, 0.0005)
        assert 50 <= comp.score <= 70


class TestMomentumExhaustion:
    def test_strong_exhaustion(self) -> None:
        """Large negative deceleration → high score."""
        comp = score_momentum_exhaustion(-0.10, 0.15)
        assert comp.score >= 90
        assert "exhaust" in comp.explanation.lower()

    def test_acceleration(self) -> None:
        """Positive deceleration → low score."""
        comp = score_momentum_exhaustion(0.02, 0.15)
        assert comp.score <= 15

    def test_no_pump(self) -> None:
        """Price not up → score 0."""
        comp = score_momentum_exhaustion(-0.05, -0.02)
        assert comp.score == 0


class TestTakerSellPressure:
    def test_strong_sell(self) -> None:
        """Buy ratio 0.35 → high score."""
        comp = score_taker_sell_pressure(0.35, -0.05)
        assert comp.score >= 80

    def test_buy_dominant(self) -> None:
        """Buy ratio 0.6 → low score."""
        comp = score_taker_sell_pressure(0.6, 0.02)
        assert comp.score <= 15


class TestFakeBreakout:
    def test_strong_fake_breakout(self) -> None:
        """Feature value 1.0 → score 100."""
        comp = score_fake_breakout(1.0)
        assert comp.score == 100.0
        assert comp.weight == 0.05
        assert "bull trap" in comp.explanation.lower()

    def test_no_breakout(self) -> None:
        """Feature value 0.0 → score 0."""
        comp = score_fake_breakout(0.0)
        assert comp.score == 0.0

    def test_moderate_fake_breakout(self) -> None:
        """Feature value 0.5 → score 50."""
        comp = score_fake_breakout(0.5)
        assert 45 <= comp.score <= 55

    def test_weak_fake_breakout(self) -> None:
        """Feature value 0.2 → low score, weak signal."""
        comp = score_fake_breakout(0.2)
        assert comp.score <= 25
        assert "weak" in comp.explanation.lower()


class TestCompositeScore:
    def test_high_risk_coin(self, config: ScoringConfig, weak_btc: BtcContext) -> None:
        """Coin with all bearish signals + weak BTC → high score."""
        features = _make_features()
        score = compute_distribution_score(
            "TESTUSDT", features, weak_btc, config, pump_pct=1.8, pump_days=3
        )
        assert score.total_score >= 70
        assert score.recommendation == "SHORT_CANDIDATE"
        assert len(score.components) == 8
        assert score.pump_pct == 1.8

    def test_low_risk_coin(self, config: ScoringConfig, fomo_btc: BtcContext) -> None:
        """Coin with bullish signals + FOMO BTC → low score."""
        features = _make_features(
            price_ret_24h=-0.05,
            volume_percentile_24h=0.9,
            funding_zscore_30d=0.0,
            momentum_deceleration_4h=0.02,
            distance_from_high_24h=-0.25,
            taker_buy_ratio=0.65,
            taker_buy_ratio_change_1h=0.03,
            oi_change_24h=0.05,
            fake_breakout_1h=0.0,
        )
        score = compute_distribution_score("TESTUSDT", features, fomo_btc, config)
        assert score.total_score < 50
        assert score.recommendation == "WAIT"

    def test_score_in_range(
        self, config: ScoringConfig, neutral_btc: BtcContext
    ) -> None:
        """Score should always be 0-100."""
        features = _make_features()
        score = compute_distribution_score("TESTUSDT", features, neutral_btc, config)
        assert 0 <= score.total_score <= 100

    def test_top_signals(self, config: ScoringConfig, weak_btc: BtcContext) -> None:
        """top_signals should return 3 highest weighted scores."""
        features = _make_features()
        score = compute_distribution_score("TESTUSDT", features, weak_btc, config)
        top = score.top_signals
        assert len(top) == 3
        assert top[0].weighted_score >= top[1].weighted_score
        assert top[1].weighted_score >= top[2].weighted_score

    def test_watch_recommendation(
        self, config: ScoringConfig, neutral_btc: BtcContext
    ) -> None:
        """Score in 50-70 range → WATCH."""
        features = _make_features(
            volume_percentile_24h=0.5,
            funding_zscore_30d=1.0,
            momentum_deceleration_4h=-0.02,
            taker_buy_ratio=0.48,
            oi_change_24h=-0.03,
        )
        score = compute_distribution_score("TESTUSDT", features, neutral_btc, config)
        assert score.recommendation in ("WATCH", "SHORT_CANDIDATE", "WAIT")
