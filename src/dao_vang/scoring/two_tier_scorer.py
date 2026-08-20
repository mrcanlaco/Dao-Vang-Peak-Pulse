"""Two-Tier Pump Climax & Realtime Order Flow Scorer (2-Tier Climax Engine).

Architecture for Pump & Dump Shitcoins / Memecoins:
- Tier 1: HTF Pump Climax Filter (1h / 4h / 24h) - Pre-condition (ARMED vs NORMAL).
  Does NOT wait for 1h/4h candle close. Measures pump amplitude, distance to peak,
  fake breakout / liquidity sweep, and price-volume exhaustion.
- Tier 2: LTF Real-time Order Flow Trigger (5m / 15m) - Execution Trigger (FIRED vs STANDBY).
  Detects the very first signs of dump: OI unwinding (longs closing), taker sell burst,
  extreme funding rate spike, and momentum deceleration.
- Synergy: When Tier 1 is ARMED and Tier 2 is FIRED, triggers instant zero-lag short candidate.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from dao_vang.config.settings import ScoringConfig
from dao_vang.logging import get_logger
from dao_vang.scoring.btc_context import BtcContext
from dao_vang.scoring.distribution_scorer import (
    ScoreComponent,
    _clamp_score,
    score_btc_context,
    score_distance_from_high,
    score_fake_breakout,
    score_funding_spike,
    score_momentum_exhaustion,
    score_oi_divergence,
    score_price_volume_divergence,
    score_taker_sell_pressure,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class TwoTierDistributionScore:
    """Two-Tier composite distribution score for a coin."""

    symbol: str
    total_score: float  # 0-100
    calibrated_probability: float  # 0.0 - 1.0
    htf_climax_score: float  # 0-100 (Tier 1: HTF Context)
    htf_state: str  # "ARMED" | "NORMAL"
    ltf_trigger_score: float  # 0-100 (Tier 2: LTF Realtime Trigger)
    ltf_state: str  # "FIRED" | "WATCH" | "STANDBY"
    tier1_components: list[ScoreComponent] = field(default_factory=list)
    tier2_components: list[ScoreComponent] = field(default_factory=list)
    components: list[ScoreComponent] = field(default_factory=list)
    btc_regime: str = "NEUTRAL"
    btc_explanation: str = ""
    recommendation: str = "WATCH"  # "WAIT" | "WATCH" | "SHORT_CANDIDATE"
    pump_pct: float = 0.0
    pump_days: int = 0
    explanation_summary: str = ""

    @property
    def top_signals(self) -> list[ScoreComponent]:
        """Top 3 contributing signals by weighted_score."""
        return sorted(self.components, key=lambda c: c.weighted_score, reverse=True)[:3]

    def to_dict(self) -> dict[str, Any]:
        """Serialize to JSON-friendly dictionary."""
        return {
            "symbol": self.symbol,
            "total_score": round(self.total_score, 1),
            "calibrated_probability": round(self.calibrated_probability, 4),
            "htf_climax_score": round(self.htf_climax_score, 1),
            "htf_state": self.htf_state,
            "ltf_trigger_score": round(self.ltf_trigger_score, 1),
            "ltf_state": self.ltf_state,
            "recommendation": self.recommendation,
            "btc_regime": self.btc_regime,
            "pump_pct": self.pump_pct,
            "explanation_summary": self.explanation_summary,
            "components": [
                {
                    "name": c.name,
                    "raw_value": c.raw_value,
                    "score": round(c.score, 1),
                    "weight": c.weight,
                    "weighted_score": round(c.weighted_score, 2),
                    "explanation": c.explanation,
                }
                for c in self.components
            ],
        }


def score_pump_magnitude_htf(
    price_ret_24h: float,
    pump_pct: float = 0.0,
    weight: float = 0.35,
) -> ScoreComponent:
    """Score the macro pump amplitude. Greater pump = higher climax risk."""
    effective_pump = max(price_ret_24h, pump_pct)
    if effective_pump <= 0.10:
        score = 0.0
        explanation = f"Pump amplitude +{effective_pump:.1%} 24h — normal baseline."
    elif effective_pump <= 0.30:
        score = 30.0 + (effective_pump - 0.10) / 0.20 * 30.0  # 30 - 60
        explanation = f"Moderate pump +{effective_pump:.1%} 24h — warming up."
    elif effective_pump <= 0.80:
        score = 60.0 + (effective_pump - 0.30) / 0.50 * 30.0  # 60 - 90
        explanation = f"Heavy pump +{effective_pump:.1%} 24h — HTF climax zone reached."
    else:
        score = 95.0 + min(5.0, (effective_pump - 0.80) * 5.0)  # 95 - 100
        explanation = f"Extreme parabolic pump +{effective_pump:.1%} 24h — blow-off danger."

    score = _clamp_score(score)
    return ScoreComponent(
        name="htf_pump_magnitude",
        raw_value=effective_pump,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        explanation=explanation,
    )


def compute_two_tier_distribution_score(
    symbol: str,
    features: dict[str, Any],
    btc: BtcContext,
    config: ScoringConfig,
    pump_pct: float = 0.0,
    pump_days: int = 0,
) -> TwoTierDistributionScore:
    """Compute Two-Tier distribution score (HTF Climax Context + LTF Order Flow Trigger)."""

    # --- TIER 1: HTF PUMP CLIMAX CONTEXT (1h / 4h / 24h) ---
    t1_components: list[ScoreComponent] = []

    price_ret_24h = float(features.get("price_ret_24h") or 0.0)
    vol_percentile = float(features.get("volume_percentile_24h") or 0.5)
    dist_high = float(features.get("distance_from_high_24h") or 0.0)
    fake_breakout = float(features.get("fake_breakout_1h") or 0.0)

    t1_components.append(score_pump_magnitude_htf(price_ret_24h, pump_pct=pump_pct, weight=0.35))
    t1_components.append(score_distance_from_high(dist_high, weight=0.25))
    t1_components.append(score_price_volume_divergence(price_ret_24h, vol_percentile, weight=0.25))
    t1_components.append(score_fake_breakout(fake_breakout, weight=0.15))

    t1_raw_weight = sum(c.weight for c in t1_components)
    htf_climax_score = _clamp_score(sum(c.weighted_score for c in t1_components) / (t1_raw_weight or 1.0))
    htf_state = "ARMED" if htf_climax_score >= 50.0 else "NORMAL"

    # --- TIER 2: LTF REAL-TIME ORDER FLOW TRIGGER (5m / 15m) ---
    t2_components: list[ScoreComponent] = []

    funding_z = float(features.get("funding_zscore_30d") or 0.0)
    funding_raw = float(features.get("funding_rate_raw") or 0.0)
    mom_decel = float(features.get("momentum_deceleration_4h") or 0.0)
    price_ret_4h = float(features.get("price_ret_4h") or 0.0)
    taker_buy = float(features.get("taker_buy_ratio") or 0.5)
    taker_change = float(features.get("taker_buy_ratio_change_1h") or 0.0)
    oi_change = float(features.get("oi_change_24h") or 0.0)

    t2_components.append(score_taker_sell_pressure(taker_buy, taker_change, weight=0.30))
    t2_components.append(score_oi_divergence(price_ret_24h, oi_change, weight=0.25))
    t2_components.append(score_funding_spike(funding_z, funding_raw, weight=0.25))
    t2_components.append(score_momentum_exhaustion(mom_decel, price_ret_4h, weight=0.20))

    t2_raw_weight = sum(c.weight for c in t2_components)
    ltf_trigger_score = _clamp_score(sum(c.weighted_score for c in t2_components) / (t2_raw_weight or 1.0))
    ltf_state = "FIRED" if ltf_trigger_score >= 48.0 else ("WATCH" if ltf_trigger_score >= 30.0 else "STANDBY")

    # --- BTC MACRO CONTEXT MODIFIER ---
    btc_comp = score_btc_context(btc, weight=0.10)

    # --- COMPOSITE TWO-TIER SYNERGY ---
    all_components = [*t1_components, *t2_components, btc_comp]

    if htf_state == "ARMED" and ltf_state == "FIRED":
        # Synergy: High Climax + Realtime Trigger Active
        synergy_boost = min(18.0, (htf_climax_score - 50.0) * 0.2 + (ltf_trigger_score - 48.0) * 0.2)
        total_score = _clamp_score(0.40 * htf_climax_score + 0.60 * ltf_trigger_score + synergy_boost)
        if btc.regime == "FOMO":
            total_score = max(0.0, total_score - 15.0)
        recommendation = "SHORT_CANDIDATE" if total_score >= 55.0 else "WATCH"
        explanation_summary = (
            f"⚡ [2-TIER CLIMAX FIRED] HTF ARMED ({htf_climax_score:.0f}/100) + "
            f"LTF 5m TRIGGER ({ltf_trigger_score:.0f}/100). Aggressive distribution in progress."
        )
    elif htf_state == "ARMED":
        # Pump is hot, but whales haven't pulled the dump trigger yet
        total_score = _clamp_score(0.65 * htf_climax_score + 0.35 * ltf_trigger_score)
        if btc.regime == "FOMO":
            total_score = max(0.0, total_score - 10.0)
        recommendation = "WATCH"
        explanation_summary = (
            f"🧭 [HTF CLIMAX ARMED] Pump at peak ({htf_climax_score:.0f}/100). "
            f"Awaiting 5m order flow trigger (current: {ltf_trigger_score:.0f}/100)."
        )
    else:
        # Normal baseline
        total_score = _clamp_score(0.40 * htf_climax_score + 0.60 * ltf_trigger_score)
        recommendation = "WAIT" if total_score < 40.0 else "WATCH"
        explanation_summary = f"Normal price action (HTF: {htf_climax_score:.0f}/100, LTF: {ltf_trigger_score:.0f}/100)."

    # Calibrated probability mapping via sigmoid curve
    calibrated_probability = 1.0 / (1.0 + math.exp(-0.075 * (total_score - 48.0)))
    calibrated_probability = max(0.01, min(0.99, calibrated_probability))

    logger.info(
        "two_tier_distribution_scored",
        symbol=symbol,
        total_score=round(total_score, 1),
        htf_state=htf_state,
        ltf_state=ltf_state,
        prob=round(calibrated_probability, 3),
        recommendation=recommendation,
    )

    return TwoTierDistributionScore(
        symbol=symbol,
        total_score=total_score,
        calibrated_probability=calibrated_probability,
        htf_climax_score=htf_climax_score,
        htf_state=htf_state,
        ltf_trigger_score=ltf_trigger_score,
        ltf_state=ltf_state,
        tier1_components=t1_components,
        tier2_components=t2_components,
        components=all_components,
        btc_regime=btc.regime,
        btc_explanation=btc.explanation,
        recommendation=recommendation,
        pump_pct=pump_pct,
        pump_days=pump_days,
        explanation_summary=explanation_summary,
    )
