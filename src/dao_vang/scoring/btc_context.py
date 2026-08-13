"""BTC context filter — adjust short score based on BTC trend.

If BTC is pumping strongly (+5% 24h), altcoin distribution may be delayed
by FOMO money flowing into the whole market. Short is dangerous.

If BTC is weak (-2% 24h), market sentiment is bearish, short is favorable.
"""

from __future__ import annotations

from dataclasses import dataclass

from dao_vang.config.settings import ScoringConfig
from dao_vang.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BtcContext:
    """BTC market context snapshot."""

    btc_ret_24h: float
    btc_ret_4h: float
    btc_ret_1h: float
    regime: str  # "FOMO" | "NEUTRAL" | "WEAK"
    score_adjustment: float  # 0-100, higher = more favorable for short
    explanation: str


def classify_btc(
    btc_ret_24h: float,
    btc_ret_4h: float,
    btc_ret_1h: float,
    config: ScoringConfig,
) -> BtcContext:
    """Classify BTC regime and compute score adjustment.

    Args:
        btc_ret_24h: BTC 24h return (e.g. 0.05 = +5%).
        btc_ret_4h: BTC 4h return.
        btc_ret_1h: BTC 1h return.
        config: ScoringConfig with thresholds.

    Returns BtcContext with regime + score adjustment (0-100).
    """
    # FOMO: BTC pumping hard — short dangerous
    if btc_ret_24h >= config.btc_fomo_threshold:
        regime = "FOMO"
        # Higher BTC pump → lower short score (more dangerous)
        # Scale: +5% → score 20, +10% → score 5, +15%+ → score 0
        excess = btc_ret_24h - config.btc_fomo_threshold
        score = max(0.0, 20.0 - (excess * 200.0))
        explanation = (
            f"BTC +{btc_ret_24h:.1%} 24h — FOMO risk HIGH. "
            f"Altcoin distribution may be delayed by market-wide money flow. "
            f"Short dangerous."
        )
    # WEAK: BTC dumping — short favorable
    elif btc_ret_24h <= config.btc_weak_threshold:
        regime = "WEAK"
        # More negative BTC → higher short score (more favorable)
        # Scale: -2% → score 70, -5% → score 90, -10%+ → score 100
        deficit = config.btc_weak_threshold - btc_ret_24h
        score = min(100.0, 70.0 + (deficit * 800.0))
        explanation = (
            f"BTC {btc_ret_24h:.1%} 24h — market WEAK. "
            f"Bearish sentiment supports altcoin distribution. "
            f"Short favorable."
        )
    # NEUTRAL: BTC flat — no strong bias
    else:
        regime = "NEUTRAL"
        # Scale linearly between weak and fomo thresholds
        # -2% → 70, 0% → 50, +5% → 20
        score = 50.0 - (btc_ret_24h * 6.0)
        score = max(20.0, min(70.0, score))
        explanation = (
            f"BTC {btc_ret_24h:.1%} 24h — NEUTRAL. "
            f"No strong market bias. Score on altcoin fundamentals."
        )

    logger.info(
        "btc_context_classified",
        regime=regime,
        btc_ret_24h=btc_ret_24h,
        score_adjustment=score,
    )
    return BtcContext(
        btc_ret_24h=btc_ret_24h,
        btc_ret_4h=btc_ret_4h,
        btc_ret_1h=btc_ret_1h,
        regime=regime,
        score_adjustment=score,
        explanation=explanation,
    )
