"""Distribution scorer — composite 0-100 score for short distribution risk.

8 signals, each scored 0-100, weighted sum = total score:
  1. price_volume_divergence (20%): price up but volume down → fake pump
  2. funding_spike (15%): funding rate abnormally high → longs overleveraged
  3. momentum_exhaustion (15%): 1h return decelerating → pump losing steam
  4. distance_from_high (10%): close near 24h high → good R:R for short
  5. taker_sell_pressure (10%): sell volume > buy → distribution in progress
  6. btc_context (15%): BTC trend filter — FOMO reduces short score
  7. oi_divergence (10%): price up but OI down → unwinding, not new longs
  8. fake_breakout (5%): candle poked above prior high then closed back below
     → bull trap / FOMO bait, market makers distributing into breakout buyers

Higher score = more likely to distribute (short candidate).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dao_vang.config.settings import ScoringConfig
from dao_vang.logging import get_logger
from dao_vang.scoring.btc_context import BtcContext

logger = get_logger(__name__)


@dataclass(frozen=True)
class ScoreComponent:
    """One signal contribution to the total score."""

    name: str
    raw_value: float
    score: float  # 0-100
    weight: float  # 0-1
    weighted_score: float  # score * weight
    explanation: str


@dataclass(frozen=True)
class DistributionScore:
    """Composite distribution score for a coin."""

    symbol: str
    total_score: float  # 0-100
    components: list[ScoreComponent] = field(default_factory=list[ScoreComponent])
    btc_regime: str = "NEUTRAL"
    btc_explanation: str = ""
    recommendation: str = "WATCH"  # "WAIT" | "WATCH" | "SHORT_CANDIDATE"
    pump_pct: float = 0.0
    pump_days: int = 0

    @property
    def top_signals(self) -> list[ScoreComponent]:
        """Top 3 contributing signals by weighted_score."""
        return sorted(self.components, key=lambda c: c.weighted_score, reverse=True)[:3]


def _clamp_score(x: float) -> float:
    """Clamp to 0-100."""
    return max(0.0, min(100.0, x))


def score_price_volume_divergence(
    price_ret_24h: float,
    volume_percentile_24h: float,
    weight: float = 0.20
) -> ScoreComponent:
    """Price up but volume down → fake pump, no real demand.

    volume_percentile_24h: 0-1 (1 = at 24h max volume).
    """
    if price_ret_24h <= 0:
        score = 0.0
        explanation = (
            f"Price {price_ret_24h:.1%} 24h — not pumping, no divergence signal."
        )
    else:
        # High price return + low volume percentile = high divergence
        # Scale: price +50% with volume at 20th percentile → score ~90
        # price +50% with volume at 80th percentile → score ~20
        volume_factor = 1.0 - volume_percentile_24h  # low vol → high factor
        price_factor = min(1.0, price_ret_24h / 0.5)  # cap at +50%
        score = _clamp_score(90.0 * volume_factor * price_factor)
        explanation = (
            f"Price +{price_ret_24h:.1%} 24h but volume at "
            f"{volume_percentile_24h:.0%} of 24h range. "
            + (
                "Divergence — pump without real demand."
                if score > 50
                else "Volume supports price move."
            )
        )
    return ScoreComponent(
        name="price_volume_divergence",
        raw_value=volume_percentile_24h,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        explanation=explanation,
    )


def score_funding_spike(
    funding_zscore_30d: float,
    funding_rate_raw: float,
    weight: float = 0.15
) -> ScoreComponent:
    """Funding rate abnormally high → longs overleveraged, ready to unwind."""
    # Z-score > 2 = abnormal, > 3 = extreme
    if funding_zscore_30d <= 0:
        score = 0.0
        explanation = (
            f"Funding z-score {funding_zscore_30d:.2f} — normal or low, no spike."
        )
    else:
        # Scale: z=1 → 30, z=2 → 60, z=3+ → 100
        score = _clamp_score(30.0 * funding_zscore_30d)
        explanation = (
            f"Funding rate {funding_rate_raw:.4%} (z-score {funding_zscore_30d:.2f}, "
            f"{'top 1%' if funding_zscore_30d > 3 else 'elevated'} 30d). "
            f"Longs paying high premium — unwind risk."
        )
    return ScoreComponent(
        name="funding_spike",
        raw_value=funding_zscore_30d,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        explanation=explanation,
    )


def score_momentum_exhaustion(
    momentum_deceleration_4h: float,
    price_ret_4h: float,
    weight: float = 0.15
) -> ScoreComponent:
    """1h momentum decelerating → pump losing steam."""
    # momentum_deceleration_4h = current_1h_ret - 1h_ret_3h_ago
    # Negative = decelerating (current return < past return)
    if price_ret_4h <= 0:
        score = 0.0
        explanation = "Price not up 4h — no momentum to exhaust."
    elif momentum_deceleration_4h >= 0:
        score = 10.0  # still accelerating, low exhaustion
        explanation = (
            f"Momentum accelerating (+{momentum_deceleration_4h:.2%}) — "
            f"pump still strong."
        )
    else:
        # Negative deceleration = exhaustion
        # Scale: -2% → 40, -5% → 70, -10%+ → 100
        score = _clamp_score(40.0 + abs(momentum_deceleration_4h) * 600.0)
        explanation = (
            f"1h return decelerating by {momentum_deceleration_4h:.2%} over 4h. "
            f"Pump losing steam — exhaustion signal."
        )
    return ScoreComponent(
        name="momentum_exhaustion",
        raw_value=momentum_deceleration_4h,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        explanation=explanation,
    )


def score_distance_from_high(
    distance_from_high_24h: float,
    weight: float = 0.10
) -> ScoreComponent:
    """Close near 24h high → good risk:reward for short entry."""
    # distance_from_high_24h is negative (close / high - 1)
    # 0 = at high (best for short), -0.3 = 30% below high (missed)
    if distance_from_high_24h >= 0:
        score = 100.0
        explanation = "Close at 24h high — optimal short entry R:R."
    else:
        # Scale: 0% → 100, -5% → 70, -15% → 30, -30%+ → 0
        score = _clamp_score(100.0 + distance_from_high_24h * 300.0)
        explanation = f"Close {distance_from_high_24h:.1%} from 24h high. " + (
            "Near peak — good short entry."
            if score > 50
            else "Far from peak — missed optimal entry."
        )
    return ScoreComponent(
        name="distance_from_high",
        raw_value=distance_from_high_24h,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        explanation=explanation,
    )


def score_taker_sell_pressure(
    taker_buy_ratio: float,
    taker_buy_ratio_change_1h: float,
    weight: float = 0.10
) -> ScoreComponent:
    """Sell volume > buy volume → distribution in progress."""
    # taker_buy_ratio < 0.5 = sell dominant
    if taker_buy_ratio >= 0.55:
        score = 10.0
        explanation = (
            f"Buy ratio {taker_buy_ratio:.2f} — buyers dominant, no sell pressure."
        )
    else:
        # Scale: 0.50 → 50, 0.45 → 70, 0.40 → 90, 0.35- → 100
        deficit = 0.55 - taker_buy_ratio
        score = _clamp_score(50.0 + deficit * 400.0)
        # Bonus if buy ratio dropping (change_1h negative)
        if taker_buy_ratio_change_1h < 0:
            score = _clamp_score(score + 10.0)
        explanation = (
            f"Buy ratio {taker_buy_ratio:.2f} (change 1h: "
            f"{taker_buy_ratio_change_1h:+.2f}) — sell pressure dominant. "
            f"Distribution in progress."
        )
    return ScoreComponent(
        name="taker_sell_pressure",
        raw_value=taker_buy_ratio,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        explanation=explanation,
    )


def score_oi_divergence(
    price_ret_24h: float,
    oi_change_24h: float,
    weight: float = 0.10
) -> ScoreComponent:
    """Price up but OI down → positions unwinding, not new longs.

    oi_change_24h: percent change in open interest 24h (e.g. -0.1 = -10%).
    """
    if price_ret_24h <= 0:
        score = 0.0
        explanation = "Price not up — OI divergence not applicable."
    elif oi_change_24h >= 0:
        score = 15.0
        explanation = (
            f"Price +{price_ret_24h:.1%} with OI +{oi_change_24h:.1%} — "
            f"new positions opening, not unwinding."
        )
    else:
        # Price up + OI down = bearish divergence
        # Scale: OI -5% → 50, OI -10% → 75, OI -20%+ → 100
        score = _clamp_score(50.0 + abs(oi_change_24h) * 250.0)
        explanation = (
            f"Giá tăng +{price_ret_24h:.1%} nhưng OI thay đổi {oi_change_24h:.1%} — "
            f"các vị thế đang chốt lời. Đà pump đến từ việc short chốt lỗ/thanh lý, không phải dòng tiền long mới."
        )
    return ScoreComponent(
        name="oi_divergence",
        raw_value=oi_change_24h,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        explanation=explanation,
    )


def score_fake_breakout(
    fake_breakout_1h: float,
    weight: float = 0.05
) -> ScoreComponent:
    """Candle poked above prior high then closed back below → bull trap.

    Market makers create false breakouts to trigger FOMO buyers' stop
    orders and breakout traders, then distribute into the buying pressure.
    A fake breakout is a strong short signal because it shows:
    1. Sellers are waiting at the prior high (supply).
    2. Buyers are trapped above the high and will be forced to sell.

    Args:
        fake_breakout_1h: Continuous 0-1 score from the feature builder.
            0 = no breakout or breakout held.
            1 = deep reclaim (≥2% below the broken high).

    Returns ScoreComponent with weight 0.05.
    """
    if fake_breakout_1h <= 0.0:
        score = 0.0
        explanation = (
            "Không có tín hiệu phá vỡ giả (bull trap) trong 1h qua."
        )
    else:
        # Scale: feature 0.5 → score 50, feature 1.0 → score 100
        score = _clamp_score(fake_breakout_1h * 100.0)
        if fake_breakout_1h >= 0.5:
            explanation = (
                f"Phát hiện phá vỡ giả (cường độ {fake_breakout_1h:.2f}) — "
                f"nến đâm qua đỉnh 1h trước đó rồi tụt xuống đóng cửa bên dưới. "
                f"Bẫy tăng giá: phe FOMO mắc kẹt, cá mập đang xả hàng."
            )
        else:
            explanation = (
                f"Phá vỡ giả nhẹ (cường độ {fake_breakout_1h:.2f}) — "
                f"chỉ đóng cửa thấp hơn đỉnh cũ một chút. Tín hiệu bẫy tăng giá yếu."
            )
    return ScoreComponent(
        name="fake_breakout",
        raw_value=fake_breakout_1h,
        score=score,
        weight=weight,
        weighted_score=score * weight,
        explanation=explanation,
    )


def score_btc_context(
    btc: BtcContext,
    weight: float = 0.15
) -> ScoreComponent:
    """BTC trend filter — FOMO reduces short score."""
    return ScoreComponent(
        name="btc_context",
        raw_value=btc.btc_ret_24h,
        score=btc.score_adjustment,
        weight=weight,
        weighted_score=btc.score_adjustment * weight,
        explanation=btc.explanation,
    )


def compute_distribution_score(
    symbol: str,
    features: dict[str, Any],
    btc: BtcContext,
    config: ScoringConfig,
    pump_pct: float = 0.0,
    pump_days: int = 0,
) -> DistributionScore:
    """Compute composite distribution score 0-100.

    Args:
        symbol: Coin symbol (e.g. "EULUSDT").
        features: Dict of feature values (from feature_results row).
        btc: BTC context snapshot.
        config: ScoringConfig with weights + thresholds.
        pump_pct: Pump magnitude from pump filter (e.g. 1.8 = +180%).
        pump_days: Days to reach peak.

    Returns DistributionScore with all components + recommendation.
    
    # Validate weights sum to 1.0 (with a small tolerance for floating point)
    total_weight = (
        config.weight_price_volume_divergence
        + config.weight_funding_spike
        + config.weight_momentum_exhaustion
        + config.weight_distance_from_high
        + config.weight_taker_sell_pressure
        + config.weight_oi_divergence
        + config.weight_btc_context
        + config.weight_fake_breakout
    )
    if abs(total_weight - 1.0) > 0.01:
        logger.warning("scorer_weights_do_not_sum_to_1", total_weight=total_weight)

"""
    components: list[ScoreComponent] = []

    components.append(
        score_price_volume_divergence(
            price_ret_24h=features.get("price_ret_24h", 0.0) if features.get("price_ret_24h") is not None else 0.0,
            volume_percentile_24h=features.get("volume_percentile_24h", 0.5) if features.get("volume_percentile_24h") is not None else 0.5,
            weight=config.weight_price_volume_divergence
        )
    )

    components.append(
        score_funding_spike(
            funding_zscore_30d=features.get("funding_zscore_30d", 0.0) if features.get("funding_zscore_30d") is not None else 0.0,
            funding_rate_raw=features.get("funding_rate_raw", 0.0) if features.get("funding_rate_raw") is not None else 0.0,
            weight=config.weight_funding_spike
        )
    )

    components.append(
        score_momentum_exhaustion(
            momentum_deceleration_4h=features.get("momentum_deceleration_4h", 0.0) if features.get("momentum_deceleration_4h") is not None else 0.0,
            price_ret_4h=features.get("price_ret_4h", 0.0) if features.get("price_ret_4h") is not None else 0.0,
            weight=config.weight_momentum_exhaustion
        )
    )

    components.append(
        score_distance_from_high(
            distance_from_high_24h=features.get("distance_from_high_24h", 0.0) if features.get("distance_from_high_24h") is not None else 0.0,
            weight=config.weight_distance_from_high
        )
    )

    components.append(
        score_taker_sell_pressure(
            taker_buy_ratio=features.get("taker_buy_ratio", 0.5) if features.get("taker_buy_ratio") is not None else 0.5,
            taker_buy_ratio_change_1h=features.get("taker_buy_ratio_change_1h", 0.0) if features.get("taker_buy_ratio_change_1h") is not None else 0.0,
            weight=config.weight_taker_sell_pressure
        )
    )

    components.append(
        score_oi_divergence(
            price_ret_24h=features.get("price_ret_24h", 0.0) if features.get("price_ret_24h") is not None else 0.0,
            oi_change_24h=features.get("oi_change_24h", 0.0) if features.get("oi_change_24h") is not None else 0.0,
            weight=config.weight_oi_divergence
        )
    )

    components.append(score_btc_context(btc, config.weight_btc_context))

    components.append(
        score_fake_breakout(
            fake_breakout_1h=features.get("fake_breakout_1h", 0.0) if features.get("fake_breakout_1h") is not None else 0.0,
            weight=config.weight_fake_breakout
        )
    )

    # Weighted sum
    total_score = sum(c.weighted_score for c in components)
    total_score = _clamp_score(total_score)

    # Recommendation
    if total_score >= config.alert_score_threshold:
        recommendation = "SHORT_CANDIDATE"
    elif total_score >= config.alert_score_threshold - 20:
        recommendation = "WATCH"
    else:
        recommendation = "WAIT"

    logger.info(
        "distribution_scored",
        symbol=symbol,
        total_score=total_score,
        recommendation=recommendation,
        btc_regime=btc.regime,
    )

    return DistributionScore(
        symbol=symbol,
        total_score=total_score,
        components=components,
        btc_regime=btc.regime,
        btc_explanation=btc.explanation,
        recommendation=recommendation,
        pump_pct=pump_pct,
        pump_days=pump_days,
    )
