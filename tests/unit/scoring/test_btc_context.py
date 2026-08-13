"""Tests for BTC context classifier — FOMO/NEUTRAL/WEAK regimes."""

from __future__ import annotations

import pytest

from dao_vang.config.settings import ScoringConfig
from dao_vang.scoring.btc_context import classify_btc


@pytest.fixture
def config() -> ScoringConfig:
    return ScoringConfig()


class TestBtcContextFomo:
    def test_strong_pump_is_fomo(self, config: ScoringConfig) -> None:
        """BTC +5% 24h should be FOMO."""
        ctx = classify_btc(0.05, 0.02, 0.005, config)
        assert ctx.regime == "FOMO"
        assert ctx.score_adjustment <= 20
        assert "FOMO" in ctx.explanation

    def test_extreme_pump_low_score(self, config: ScoringConfig) -> None:
        """BTC +15% should give very low short score."""
        ctx = classify_btc(0.15, 0.08, 0.02, config)
        assert ctx.regime == "FOMO"
        assert ctx.score_adjustment <= 5


class TestBtcContextWeak:
    def test_dump_is_weak(self, config: ScoringConfig) -> None:
        """BTC -2% should be WEAK."""
        ctx = classify_btc(-0.02, -0.01, -0.005, config)
        assert ctx.regime == "WEAK"
        assert ctx.score_adjustment >= 70
        assert "WEAK" in ctx.explanation

    def test_extreme_dump_high_score(self, config: ScoringConfig) -> None:
        """BTC -10% should give very high short score."""
        ctx = classify_btc(-0.10, -0.05, -0.02, config)
        assert ctx.regime == "WEAK"
        assert ctx.score_adjustment >= 90


class TestBtcContextNeutral:
    def test_flat_is_neutral(self, config: ScoringConfig) -> None:
        """BTC 0% should be NEUTRAL."""
        ctx = classify_btc(0.0, 0.0, 0.0, config)
        assert ctx.regime == "NEUTRAL"
        assert 40 <= ctx.score_adjustment <= 60

    def test_small_pump_is_neutral(self, config: ScoringConfig) -> None:
        """BTC +2% should be NEUTRAL (below FOMO threshold)."""
        ctx = classify_btc(0.02, 0.01, 0.005, config)
        assert ctx.regime == "NEUTRAL"

    def test_small_dip_is_neutral(self, config: ScoringConfig) -> None:
        """BTC -1% should be NEUTRAL (above WEAK threshold)."""
        ctx = classify_btc(-0.01, -0.005, -0.002, config)
        assert ctx.regime == "NEUTRAL"


class TestBtcContextScoreRange:
    def test_score_in_0_100(self, config: ScoringConfig) -> None:
        """Score adjustment should always be 0-100."""
        for ret_24h in [-0.20, -0.10, -0.05, -0.02, 0.0, 0.02, 0.05, 0.10, 0.20]:
            ctx = classify_btc(ret_24h, ret_24h / 6, ret_24h / 24, config)
            assert 0 <= ctx.score_adjustment <= 100
