"""Independent market-anomaly detection for the live Radar.

The frozen model remains the source of calibrated probability and alert tier.
This module is deliberately a separate, auditable layer that answers a
different question: *which market behaviours are unusual right now?*

All rules consume point-in-time feature snapshots.  They are descriptive
observations, not trading instructions, and no anomaly score is ever exposed
as a probability.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from dao_vang.config.settings import MarketAnomalyConfig

ANOMALY_ENGINE_VERSION = "market_anomalies_v1"


@dataclass(frozen=True, slots=True)
class MarketAnomaly:
    """One detected abnormal market behaviour."""

    code: str
    category: str
    severity: str
    score: float
    direction: str
    metric: str
    value: float | None
    threshold: float | None
    title: str
    title_vi: str
    explanation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "category": self.category,
            "severity": self.severity,
            "score": round(float(self.score), 1),
            "direction": self.direction,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "title": self.title,
            "title_vi": self.title_vi,
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class AnomalyReport:
    """Complete anomaly result for one latest feature snapshot."""

    enabled: bool
    score: float
    level: str
    anomalies: tuple[MarketAnomaly, ...] = ()
    engine_version: str = ANOMALY_ENGINE_VERSION

    @property
    def categories(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.category for item in self.anomalies))

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine_version": self.engine_version,
            "enabled": self.enabled,
            "score": round(float(self.score), 1),
            "level": self.level,
            "count": len(self.anomalies),
            "categories": list(self.categories),
            "anomalies": [item.to_dict() for item in self.anomalies],
        }


def _number(features: Mapping[str, Any], name: str) -> float | None:
    value = features.get(name)
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _config_value(config: Any, name: str, default: float) -> float:
    raw: Any
    if isinstance(config, Mapping):
        raw = config.get(name, default)
    else:
        raw = getattr(config, name, default)
    try:
        result = float(raw)
    except (TypeError, ValueError):
        return default
    return result if isfinite(result) else default


def _enabled(config: Any) -> bool:
    if isinstance(config, Mapping):
        return bool(config.get("enabled", True))
    return bool(getattr(config, "enabled", True))


def _threshold_score(value: float, threshold: float, extreme: float) -> float:
    """Map a value at/above a threshold to a bounded anomaly score."""

    if value < threshold:
        return 0.0
    if extreme <= threshold:
        return 100.0
    progress = min(1.0, max(0.0, (value - threshold) / (extreme - threshold)))
    return min(100.0, 50.0 + progress * 50.0)


def _severity(score: float) -> str:
    if score >= 80.0:
        return "extreme"
    if score >= 60.0:
        return "high"
    return "medium"


def _level(score: float) -> str:
    if score >= 80.0:
        return "EXTREME"
    if score >= 60.0:
        return "ELEVATED"
    if score >= 35.0:
        return "WATCH"
    return "NORMAL"


def detect_market_anomalies(
    features: Mapping[str, Any],
    config: MarketAnomalyConfig | Mapping[str, Any] | Any | None = None,
) -> AnomalyReport:
    """Detect unusual price, flow and derivatives behaviour.

    The detector only emits a rule when the required feature is present and
    finite.  Missing data therefore produces fewer observations instead of a
    false anomaly caused by a synthetic zero.
    """

    resolved = config or MarketAnomalyConfig()
    if not _enabled(resolved):
        return AnomalyReport(enabled=False, score=0.0, level="NORMAL")

    min_signal_score = _config_value(resolved, "min_signal_score", 35.0)
    anomalies: list[MarketAnomaly] = []

    def add(
        *,
        code: str,
        category: str,
        score: float,
        direction: str,
        metric: str,
        value: float | None,
        threshold: float | None,
        title: str,
        title_vi: str,
        explanation: str,
    ) -> None:
        bounded = max(0.0, min(100.0, float(score)))
        if bounded < min_signal_score:
            return
        anomalies.append(
            MarketAnomaly(
                code=code,
                category=category,
                severity=_severity(bounded),
                score=bounded,
                direction=direction,
                metric=metric,
                value=value,
                threshold=threshold,
                title=title,
                title_vi=title_vi,
                explanation=explanation,
            )
        )

    # 1. Volume shock: combine a 5m distribution z-score, a 1h/previous-1h
    # ratio and the existing 24h high-volume position.  Any one can be
    # missing during a warm-up period.
    volume_z = _number(features, "volume_zscore_24h")
    volume_ratio = _number(features, "volume_ratio_1h")
    volume_percentile = _number(features, "volume_percentile_24h")
    z_threshold = _config_value(resolved, "volume_zscore_threshold", 2.5)
    ratio_threshold = _config_value(resolved, "volume_ratio_1h_threshold", 1.8)
    percentile_threshold = _config_value(
        resolved, "volume_percentile_threshold", 0.85
    )
    volume_candidates: list[tuple[str, float, float, float]] = []
    if volume_z is not None:
        volume_candidates.append(
            (
                "volume_zscore_24h",
                _threshold_score(volume_z, z_threshold, max(z_threshold + 0.1, 5.0)),
                volume_z,
                z_threshold,
            )
        )
    if volume_ratio is not None:
        volume_candidates.append(
            (
                "volume_ratio_1h",
                _threshold_score(
                    volume_ratio, ratio_threshold, max(ratio_threshold + 0.1, 4.0)
                ),
                volume_ratio,
                ratio_threshold,
            )
        )
    if volume_percentile is not None:
        volume_candidates.append(
            (
                "volume_percentile_24h",
                _threshold_score(
                    volume_percentile,
                    percentile_threshold,
                    max(percentile_threshold + 0.01, 1.0),
                ),
                volume_percentile,
                percentile_threshold,
            )
        )
    if volume_candidates:
        volume_metric, volume_score, volume_value, volume_limit = max(
            volume_candidates, key=lambda item: item[1]
        )
        if volume_score >= min_signal_score:
            recent_return = _number(features, "price_ret_1h")
            if recent_return is None:
                recent_return = _number(features, "price_ret_15m")
            taker_buy = _number(features, "taker_buy_ratio")
            if recent_return is not None and recent_return < -0.01:
                volume_direction = "bearish"
            elif (
                recent_return is not None
                and recent_return > 0.01
                and taker_buy is not None
                and taker_buy < 0.48
            ):
                volume_direction = "bearish"
            elif recent_return is not None and recent_return > 0.01:
                volume_direction = "bullish"
            else:
                volume_direction = "neutral"
            add(
                code="volume_spike",
                category="volume",
                score=volume_score,
                direction=volume_direction,
                metric=volume_metric,
                value=volume_value,
                threshold=volume_limit,
                title="Volume spike",
                title_vi="Đột biến khối lượng",
                explanation=(
                    f"Khối lượng bất thường ({volume_metric}={volume_value:.2f}, "
                    f"ngưỡng {volume_limit:.2f}); cần kiểm tra xem dòng tiền "
                    "đang xác nhận hay phân phối vào nhịp giá."
                ),
            )

    # 2. Funding extremes and abrupt funding changes.  Funding is ignored
    # when its as-of observation is older than the configured safety window.
    funding_age = _number(features, "funding_age_minutes")
    funding_max_age = _config_value(resolved, "funding_max_age_minutes", 720.0)
    funding_fresh = funding_age is None or funding_age <= funding_max_age
    funding_raw = _number(features, "funding_rate_raw")
    funding_z = _number(features, "funding_zscore_30d")
    funding_pct = _number(features, "funding_percentile_30d")
    funding_z_threshold = _config_value(resolved, "funding_zscore_threshold", 2.0)
    extreme_candidates: list[tuple[str, float, float, float]] = []
    if funding_fresh and funding_z is not None:
        extreme_candidates.append(
            (
                "funding_zscore_30d",
                _threshold_score(
                    abs(funding_z),
                    funding_z_threshold,
                    max(funding_z_threshold + 0.1, 4.0),
                ),
                funding_z,
                funding_z_threshold,
            )
        )
    if funding_fresh and funding_pct is not None:
        extreme_candidates.append(
            (
                "funding_percentile_30d",
                _threshold_score(
                    abs(funding_pct - 0.5),
                    0.35,
                    0.5,
                ),
                funding_pct,
                0.35,
            )
        )
    if funding_fresh and funding_raw is not None:
        # Fallback for a short history where a z-score/percentile is not yet
        # available.  0.05% per settlement is already an unusual carry cost.
        extreme_candidates.append(
            (
                "funding_rate_raw",
                _threshold_score(abs(funding_raw), 0.0005, 0.0015),
                funding_raw,
                0.0005,
            )
        )
    if extreme_candidates:
        funding_metric, funding_score, funding_value, funding_limit = max(
            extreme_candidates, key=lambda item: item[1]
        )
        if funding_score >= min_signal_score:
            positive_funding = (funding_raw or funding_value) >= 0.0
            add(
                code="funding_extreme",
                category="funding",
                score=funding_score,
                direction="bearish" if positive_funding else "squeeze_risk",
                metric=funding_metric,
                value=funding_value,
                threshold=funding_limit,
                title="Extreme funding",
                title_vi="Funding cực trị",
                explanation=(
                    f"Funding lệch xa mức bình thường ({funding_metric}="
                    f"{funding_value:.4f}); funding dương cho thấy long crowded, "
                    "funding âm cảnh báo rủi ro short squeeze."
                ),
            )

    funding_change = _number(features, "funding_change_8h")
    funding_change_threshold = _config_value(
        resolved, "funding_change_8h_threshold", 0.0003
    )
    if funding_fresh and funding_change is not None:
        funding_shift_score = _threshold_score(
            abs(funding_change), funding_change_threshold, 0.001
        )
        previous_funding = (
            funding_raw - funding_change
            if funding_raw is not None
            else None
        )
        sign_flip = (
            funding_raw is not None
            and previous_funding is not None
            and funding_raw != 0.0
            and previous_funding != 0.0
            and funding_raw * previous_funding < 0.0
        )
        if funding_shift_score >= min_signal_score:
            add(
                code="funding_flip" if sign_flip else "funding_shift",
                category="funding",
                score=funding_shift_score,
                direction=(
                    "bearish"
                    if (funding_raw or 0.0) > 0.0
                    else "squeeze_risk"
                ),
                metric="funding_change_8h",
                value=funding_change,
                threshold=funding_change_threshold,
                title="Funding direction shift" if sign_flip else "Funding acceleration",
                title_vi="Funding đổi chiều" if sign_flip else "Funding tăng tốc",
                explanation=(
                    f"Funding thay đổi {funding_change:+.4%} trong 8h"
                    + (" và đã đổi dấu." if sign_flip else ".")
                    + " Đòn bẩy phe đang trả phí có thể bị unwind nhanh."
                ),
            )

    # 3. Trend reversal: a meaningful move in the preceding 4h followed by a
    # sharp 1h move in the opposite direction, with deceleration as a softer
    # exhaustion confirmation.
    price_4h = _number(features, "price_ret_4h")
    price_1h = _number(features, "price_ret_1h")
    price_15m = _number(features, "price_ret_15m")
    momentum_deceleration = _number(features, "momentum_deceleration_4h")
    prior_threshold = _config_value(
        resolved, "reversal_prior_return_threshold", 0.03
    )
    current_threshold = _config_value(
        resolved, "reversal_current_return_threshold", 0.01
    )
    if price_4h is not None:
        bearish_reversal = (
            price_1h is not None
            and price_4h >= prior_threshold
            and price_1h <= -current_threshold
        )
        bullish_reversal = (
            price_1h is not None
            and price_4h <= -prior_threshold
            and price_1h >= current_threshold
        )
        soft_bearish_reversal = (
            price_1h is not None
            and price_4h >= prior_threshold
            and momentum_deceleration is not None
            and momentum_deceleration <= -current_threshold
            and price_1h <= current_threshold / 2.0
        )
        fast_bearish_reversal = (
            price_15m is not None
            and price_4h >= prior_threshold
            and price_15m <= -(current_threshold / 2.0)
            and (price_1h is None or price_1h <= current_threshold)
        )
        fast_bullish_reversal = (
            price_15m is not None
            and price_4h <= -prior_threshold
            and price_15m >= current_threshold / 2.0
            and (price_1h is None or price_1h >= -current_threshold)
        )
        if (
            bearish_reversal
            or soft_bearish_reversal
            or bullish_reversal
            or fast_bearish_reversal
            or fast_bullish_reversal
        ):
            magnitude = max(
                abs(price_1h or 0.0),
                abs(price_15m or 0.0),
                abs(momentum_deceleration or 0.0),
            )
            reversal_score = max(
                _threshold_score(abs(price_4h), prior_threshold, 0.12),
                _threshold_score(
                    magnitude,
                    current_threshold / 2.0
                    if (fast_bearish_reversal or fast_bullish_reversal)
                    else current_threshold,
                    0.05,
                ),
            )
            uses_fast_reversal = (
                (fast_bearish_reversal or fast_bullish_reversal)
                and not (bearish_reversal or bullish_reversal or soft_bearish_reversal)
            )
            reversal_metric = "price_ret_15m" if uses_fast_reversal else "price_ret_1h"
            reversal_value = price_15m if uses_fast_reversal else price_1h
            add(
                code="trend_reversal",
                category="reversal",
                score=reversal_score,
                direction="bullish"
                if (bullish_reversal or fast_bullish_reversal)
                else "bearish",
                metric=reversal_metric,
                value=reversal_value,
                threshold=(current_threshold / 2.0 if uses_fast_reversal else current_threshold),
                title="Trend reversal",
                title_vi="Đảo chiều xu hướng",
                explanation=(
                    f"Giá 4h {price_4h:+.2%} nhưng nhịp gần nhất "
                    f"{reversal_value:+.2%}; "
                    "đà trước đó đang bị đảo hướng."
                ),
            )

    # 4. Price/OI divergence and leverage build-up.
    oi_age = _number(features, "oi_age_minutes")
    oi_max_age = _config_value(resolved, "oi_max_age_minutes", 60.0)
    oi_fresh = oi_age is None or oi_age <= oi_max_age
    oi_4h = _number(features, "oi_change_4h") if oi_fresh else None
    oi_24h = _number(features, "oi_change_24h") if oi_fresh else None
    price_oi_divergence = _number(features, "price_oi_divergence_1h") if oi_fresh else None
    oi_threshold = _config_value(resolved, "oi_unwind_threshold", 0.03)
    oi_unwind_score = 0.0
    oi_metric = "oi_change_4h"
    oi_value: float | None = None
    if oi_fresh and price_4h is not None and price_4h >= prior_threshold:
        if oi_4h is not None and oi_4h <= -oi_threshold:
            oi_unwind_score = _threshold_score(abs(oi_4h), oi_threshold, 0.15)
            oi_value = oi_4h
        elif oi_24h is not None and oi_24h <= -oi_threshold:
            oi_metric = "oi_change_24h"
            oi_unwind_score = _threshold_score(abs(oi_24h), oi_threshold, 0.25)
            oi_value = oi_24h
        elif price_oi_divergence is not None and price_oi_divergence < -0.0003:
            oi_metric = "price_oi_divergence_1h"
            oi_unwind_score = _threshold_score(
                abs(price_oi_divergence), 0.0003, 0.003
            )
            oi_value = price_oi_divergence
    if oi_unwind_score >= min_signal_score:
        add(
            code="oi_unwind",
            category="open_interest",
            score=oi_unwind_score,
            direction="bearish",
            metric=oi_metric,
            value=oi_value,
            threshold=-oi_threshold if oi_metric.startswith("oi_change") else -0.0003,
            title="Price/OI unwind",
            title_vi="Giá tăng nhưng OI rút",
            explanation=(
                f"Giá vẫn tăng trong khi {oi_metric}={oi_value:+.2%}; "
                "vị thế đang đóng/rút thay vì mở long mới. Đây là proxy unwind, "
                "không phải dữ liệu thanh lý trực tiếp."
            ),
        )

    if (
        oi_fresh
        and oi_4h is not None
        and oi_4h >= 0.05
        and (price_4h is None or abs(price_4h) <= 0.02)
    ):
        leverage_score = _threshold_score(oi_4h, 0.05, 0.20)
        add(
            code="leverage_build_up",
            category="open_interest",
            score=leverage_score,
            direction="squeeze_risk",
            metric="oi_change_4h",
            value=oi_4h,
            threshold=0.05,
            title="Leverage build-up",
            title_vi="Đòn bẩy tích tụ",
            explanation=(
                f"OI tăng {oi_4h:+.2%} trong 4h nhưng giá gần như đi ngang; "
                "đòn bẩy tích tụ có thể làm biên độ breakout/breakdown phình to."
            ),
        )

    # 5. Aggressive sell flow and long crowding.
    taker_buy = _number(features, "taker_buy_ratio")
    taker_change = _number(features, "taker_buy_ratio_change_1h")
    taker_threshold = _config_value(
        resolved, "taker_buy_ratio_threshold", 0.45
    )
    taker_change_threshold = _config_value(
        resolved, "taker_ratio_change_threshold", 0.05
    )
    flow_scores: list[tuple[str, float, float, float]] = []
    if taker_buy is not None:
        flow_scores.append(
            (
                "taker_buy_ratio",
                _threshold_score(0.5 - taker_buy, 0.5 - taker_threshold, 0.15),
                taker_buy,
                taker_threshold,
            )
        )
    if taker_change is not None:
        flow_scores.append(
            (
                "taker_buy_ratio_change_1h",
                _threshold_score(
                    abs(taker_change), taker_change_threshold, 0.15
                )
                if taker_change < 0.0
                else 0.0,
                taker_change,
                -taker_change_threshold,
            )
        )
    if flow_scores:
        flow_metric, flow_score, flow_value, flow_limit = max(
            flow_scores, key=lambda item: item[1]
        )
        if flow_score >= min_signal_score:
            flow_display = (
                f"{flow_value:.3f}"
                if flow_metric == "taker_buy_ratio"
                else f"{flow_value:+.3f}"
            )
            add(
                code="taker_sell_imbalance",
                category="order_flow",
                score=flow_score,
                direction="bearish",
                metric=flow_metric,
                value=flow_value,
                threshold=flow_limit,
                title="Aggressive sell flow",
                title_vi="Áp lực bán chủ động",
                explanation=(
                    f"Dòng taker nghiêng về bán ({flow_metric}={flow_display}); "
                    "lực bán đang chiếm ưu thế ở thị trường Futures."
                ),
            )

    long_ratio_threshold = _config_value(
        resolved, "crowded_long_ratio_threshold", 1.5
    )
    short_ratio_threshold = (
        1.0 / long_ratio_threshold if long_ratio_threshold > 1.0 else 0.67
    )
    position_candidates = [
        (name, value)
        for name in (
            "top_long_short_position_ratio",
            "top_ls_ratio",
            "global_ls_ratio",
        )
        if (value := _number(features, name)) is not None
    ]
    if position_candidates:
        long_metric, long_value = max(position_candidates, key=lambda item: item[1])
        short_metric, short_value = min(position_candidates, key=lambda item: item[1])
        if long_value >= long_ratio_threshold:
            crowd_score = _threshold_score(long_value, long_ratio_threshold, 2.5)
            add(
                code="long_crowding",
                category="positioning",
                score=crowd_score,
                direction=(
                    "bearish"
                    if (funding_raw is not None and funding_raw > 0.0)
                    else "squeeze_risk"
                ),
                metric=long_metric,
                value=long_value,
                threshold=long_ratio_threshold,
                title="Long crowding",
                title_vi="Phe Long quá đông",
                explanation=(
                    f"Tỷ lệ long/short {long_metric}={long_value:.2f}; "
                    "nếu funding cũng dương, rủi ro unwind dây chuyền tăng."
                ),
            )
        if short_value <= short_ratio_threshold:
            crowd_score = _threshold_score(
                short_ratio_threshold / max(short_value, 0.01),
                1.0,
                1.5,
            )
            add(
                code="short_crowding",
                category="positioning",
                score=crowd_score,
                direction="squeeze_risk",
                metric=short_metric,
                value=short_value,
                threshold=short_ratio_threshold,
                title="Short crowding",
                title_vi="Phe Short quá đông",
                explanation=(
                    f"Tỷ lệ long/short {short_metric}={short_value:.2f} thấp; "
                    "nếu giá bật lên, short squeeze có thể lan nhanh."
                ),
            )

    # 6. A confirmed fake breakout is a useful reversal precursor.
    fake_breakout = _number(features, "fake_breakout_1h")
    if fake_breakout is not None and fake_breakout > 0.0:
        add(
            code="fake_breakout",
            category="reversal",
            score=fake_breakout * 100.0,
            direction="bearish",
            metric="fake_breakout_1h",
            value=fake_breakout,
            threshold=0.35,
            title="Fake breakout",
            title_vi="Phá vỡ giả",
            explanation=(
                f"Giá quét qua đỉnh gần nhất rồi đóng cửa trở lại bên dưới "
                f"(cường độ {fake_breakout:.2f}); có dấu hiệu bull trap."
            ),
        )

    anomalies.sort(key=lambda item: (-item.score, item.code))
    categories = tuple(dict.fromkeys(item.category for item in anomalies))
    if not anomalies:
        return AnomalyReport(enabled=True, score=0.0, level="NORMAL")

    # Reward independent domains without allowing duplicate correlated rules
    # in one domain to inflate the score too much.
    base_score = max(item.score for item in anomalies)
    combined_score = min(100.0, base_score + min(24.0, 8.0 * (len(categories) - 1)))
    return AnomalyReport(
        enabled=True,
        score=combined_score,
        level=_level(combined_score),
        anomalies=tuple(anomalies),
    )


__all__ = [
    "ANOMALY_ENGINE_VERSION",
    "AnomalyReport",
    "MarketAnomaly",
    "detect_market_anomalies",
]
