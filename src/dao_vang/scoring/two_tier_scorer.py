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
    trigger_pattern: str = ""
    trigger_pattern_vi: str = ""
    trade_setup: dict[str, Any] = field(default_factory=dict)

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
            "trigger_pattern": self.trigger_pattern,
            "trigger_pattern_vi": self.trigger_pattern_vi,
            "trade_setup": self.trade_setup,
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
    calibrator: Any | None = None,
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

    # Calibrated probability mapping
    if calibrator is not None:
        try:
            if hasattr(calibrator, "transform"):
                calibrated_probability = float(calibrator.transform([total_score])[0])
            elif hasattr(calibrator, "predict"):
                calibrated_probability = float(calibrator.predict([total_score])[0])
            elif callable(calibrator):
                calibrated_probability = float(calibrator(total_score))
            else:
                # Fallback to static sigmoid
                calibrated_probability = 1.0 / (1.0 + math.exp(-0.075 * (total_score - 48.0)))
        except Exception:
            # Fail-open: use static sigmoid if calibrator errors
            calibrated_probability = 1.0 / (1.0 + math.exp(-0.075 * (total_score - 48.0)))
    else:
        # Legacy static sigmoid fallback
        calibrated_probability = 1.0 / (1.0 + math.exp(-0.075 * (total_score - 48.0)))
    calibrated_probability = max(0.01, min(0.99, calibrated_probability))

    # Determine primary trigger pattern
    pat_en, pat_vi = determine_trigger_pattern(features, htf_state, ltf_state)

    # Calculate trade setup if close price is provided
    close_price = float(features.get("close") or features.get("close_price") or 0.0)
    trade_setup = calculate_trade_setup(close_price, dist_high=dist_high, features=features)

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
        trigger_pattern=pat_en,
        trigger_pattern_vi=pat_vi,
        trade_setup=trade_setup,
    )


def determine_trigger_pattern(
    features: dict[str, Any],
    htf_state: str,
    ltf_state: str,
) -> tuple[str, str]:
    """Identify the primary price action & microstructure trigger pattern."""
    dist_high = float(features.get("distance_from_high_24h") or 0.0)
    fake_breakout = float(features.get("fake_breakout_1h") or 0.0)
    taker_buy = float(features.get("taker_buy_ratio") or 0.5)
    oi_change = float(features.get("oi_change_24h") or 0.0)
    price_ret_24h = float(features.get("price_ret_24h") or 0.0)
    price_ret_4h = float(features.get("price_ret_4h") or 0.0)
    price_ret_1h = float(features.get("price_ret_1h") or 0.0)
    mom_decel = float(features.get("momentum_deceleration_4h") or 0.0)
    funding_z = float(features.get("funding_zscore_30d") or 0.0)

    patterns_en: list[str] = []
    patterns_vi: list[str] = []

    if fake_breakout >= 0.015 or dist_high <= 0.015:
        patterns_en.append("Liquidity Sweep High")
        patterns_vi.append("Quét thanh khoản đỉnh")
    elif price_ret_24h >= 0.30:
        patterns_en.append("Parabolic Climax")
        patterns_vi.append("Đỉnh cao trào Parabolic")

    if price_ret_4h >= 0.05 and price_ret_1h <= -0.01:
        patterns_en.append("M15 Structure Breakdown")
        patterns_vi.append("Gãy cấu trúc M15")
    elif mom_decel <= -0.02:
        patterns_en.append("Momentum Deceleration")
        patterns_vi.append("Kiệt sức đà tăng")

    if oi_change <= -0.04:
        patterns_en.append("OI Climax Unwind")
        patterns_vi.append("OI tháo chạy (Longs Exit)")
    elif taker_buy <= 0.45:
        patterns_en.append("Aggressive Taker Sell")
        patterns_vi.append("Bán chủ động áp đảo")
    elif funding_z >= 2.0:
        patterns_en.append("Extreme Funding Shock")
        patterns_vi.append("Funding Rate quá nhiệt")

    if not patterns_en:
        if htf_state == "ARMED":
            return "HTF Climax Zone", "Vùng cao trào khung lớn"
        return "Market Distribution Watch", "Theo dõi phân phối"

    return " + ".join(patterns_en[:2]), " + ".join(patterns_vi[:2])


def calculate_trade_setup(
    close_price: float,
    dist_high: float = 0.0,
    features: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Calculate concrete actionable Entry, SL, TP1, TP2, TP3 and Risk/Reward."""
    if close_price <= 0:
        return {}

    # Adaptive Stop Loss: above recent sweep high or default +3.5% to +4.0%
    sl_pct_raw = max(3.2, min(4.5, (dist_high + 0.006) * 100 if dist_high > 0 else 3.8))
    sl_price = round(close_price * (1.0 + sl_pct_raw / 100.0), 8)
    sl_pct = round(sl_pct_raw, 1)

    # Multi TP targets
    tp1_pct = 4.0   # Scalp partial close & move SL to BE
    tp2_pct = 8.0   # Standard target drawdown
    tp3_pct = 15.0  # Runner target for full distribution dump

    tp1_price = round(close_price * (1.0 - tp1_pct / 100.0), 8)
    tp2_price = round(close_price * (1.0 - tp2_pct / 100.0), 8)
    tp3_price = round(close_price * (1.0 - tp3_pct / 100.0), 8)

    rr_ratio = round(tp2_pct / (sl_pct if sl_pct > 0 else 3.8), 2)

    return {
        "entry_price": close_price,
        "entry_zone": f"{close_price * 0.998:.6g} - {close_price * 1.002:.6g}",
        "stop_loss": sl_price,
        "stop_loss_pct": sl_pct,
        "tp1": tp1_price,
        "tp1_pct": tp1_pct,
        "tp2": tp2_price,
        "tp2_pct": tp2_pct,
        "tp3": tp3_price,
        "tp3_pct": tp3_pct,
        "rr_ratio": rr_ratio,
    }

