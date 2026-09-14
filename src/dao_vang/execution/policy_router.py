"""Versioned scale-in policy router for research, backtests and serving.

The router separates whether a short signal is credible from how a position
should be built. It only selects from frozen templates; a future ML selector
cannot invent arbitrary prices or widen a stop at runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from dao_vang.config.settings import (
    ExecutionPolicyRouterConfig,
    ScaleInTemplateConfig,
)


class PolicySelector(Protocol):
    """Interface implemented by a future backtest or ML policy selector."""

    name: str
    version: str

    def select_policy(
        self,
        features: Mapping[str, float | None],
        available_policy_ids: tuple[str, ...],
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class PolicyScores:
    signal: float
    quality: float | None
    volatility: float | None
    squeeze: float
    liquidity: float | None

    def to_dict(self) -> dict[str, float | None]:
        return {
            "signal": round(self.signal, 2),
            "quality": None if self.quality is None else round(self.quality, 2),
            "volatility": (
                None if self.volatility is None else round(self.volatility, 2)
            ),
            "squeeze": round(self.squeeze, 2),
            "liquidity": (
                None if self.liquidity is None else round(self.liquidity, 2)
            ),
        }


@dataclass(frozen=True, slots=True)
class PolicyContext:
    signal_probability: float | None = None
    label_version: str | None = None
    signal_score: float | None = None
    quality_score: float | None = None
    volatility_percentile: float | None = None
    squeeze_score: float | None = None
    liquidity_score: float | None = None
    volume_24h_usd: float | None = None
    features: Mapping[str, Any] | None = None
    anomalies: tuple[Mapping[str, Any], ...] = ()


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    router_version: str
    feature_schema_version: str
    selector_name: str
    selector_version: str
    policy: ScaleInTemplateConfig
    scores: PolicyScores
    eligible: bool
    advisory_only: bool
    reason_codes: tuple[str, ...]
    challenger_policy_id: str | None = None
    challenger_selector: str | None = None

    @property
    def policy_version(self) -> str:
        return f"{self.policy.policy_id}:{self.policy.version}"

    def to_dict(
        self,
        *,
        signal_price: float,
        target_drawdown: float,
    ) -> dict[str, Any]:
        materialized = materialize_template(
            self.policy,
            signal_price=signal_price,
            target_drawdown=target_drawdown,
        )
        audit_payload = {
            "router_version": self.router_version,
            "feature_schema_version": self.feature_schema_version,
            "selector_name": self.selector_name,
            "selector_version": self.selector_version,
            "policy_id": self.policy.policy_id,
            "policy_version": self.policy_version,
            "scores": self.scores.to_dict(),
            "eligible": self.eligible,
            "advisory_only": self.advisory_only,
            "reason_codes": list(self.reason_codes),
            "challenger_policy_id": self.challenger_policy_id,
            "challenger_selector": self.challenger_selector,
        }
        audit_payload["decision_checksum"] = hashlib.sha256(
            json.dumps(audit_payload, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        return {**audit_payload, **materialized}


def _finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _score_0_100(value: float | None) -> float | None:
    if value is None:
        return None
    normalized = value * 100.0 if 0.0 <= value <= 1.0 else value
    return max(0.0, min(100.0, normalized))


def _first_number(source: Mapping[str, Any], names: Iterable[str]) -> float | None:
    for name in names:
        value = _finite_number(source.get(name))
        if value is not None:
            return value
    return None


def _score_liquidity(volume_24h_usd: float | None) -> float | None:
    if volume_24h_usd is None:
        return None
    if volume_24h_usd < 500_000:
        return 0.0
    if volume_24h_usd < 1_000_000:
        return 25.0
    if volume_24h_usd < 5_000_000:
        return 50.0
    if volume_24h_usd < 20_000_000:
        return 75.0
    return 100.0


def _score_volatility_proxy(value: float | None) -> float | None:
    """Map raw 5-minute return volatility to a versioned 0-100 proxy score."""

    if value is None or value < 0.0:
        return None
    anchors = (
        (0.0, 0.0),
        (0.001, 15.0),
        (0.002, 35.0),
        (0.004, 60.0),
        (0.007, 80.0),
        (0.012, 95.0),
        (0.020, 100.0),
    )
    for (left_x, left_y), (right_x, right_y) in zip(
        anchors,
        anchors[1:],
    ):
        if value <= right_x:
            width = right_x - left_x
            return left_y + (value - left_x) / width * (right_y - left_y)
    return 100.0


def _score_squeeze(
    features: Mapping[str, Any], anomalies: tuple[Mapping[str, Any], ...]
) -> float:
    explicit = _score_0_100(
        _first_number(features, ("squeeze_score", "short_squeeze_score"))
    )
    if explicit is not None:
        return explicit

    anomaly_scores = [
        _finite_number(item.get("score")) or 0.0
        for item in anomalies
        if str(item.get("direction", "")).lower() in {"squeeze_risk", "bullish"}
        or str(item.get("code", "")).lower() in {"short_crowding", "trend_reversal"}
    ]
    rule_score = max(anomaly_scores, default=0.0)
    price_ret_1h = _finite_number(features.get("price_ret_1h"))
    oi_change_1h = _finite_number(features.get("oi_change_1h"))
    taker_buy_ratio = _finite_number(features.get("taker_buy_ratio"))
    top_ls_ratio = _finite_number(features.get("top_ls_ratio"))
    if price_ret_1h is not None and price_ret_1h >= 0.03:
        rule_score += 20.0
    if oi_change_1h is not None and oi_change_1h >= 0.03:
        rule_score += 15.0
    if taker_buy_ratio is not None and taker_buy_ratio >= 0.55:
        rule_score += 20.0
    if top_ls_ratio is not None and top_ls_ratio <= 0.67:
        rule_score += 25.0
    return max(0.0, min(100.0, rule_score))


def score_policy_context(context: PolicyContext) -> PolicyScores:
    """Create auditable subscores from point-in-time inputs only."""

    features = context.features or {}
    # Calibrated model probability is the primary signal-confidence scale.
    # The heuristic score is only a fallback because the two are not
    # interchangeable and the frozen model threshold is probability-based.
    signal = _score_0_100(context.signal_probability)
    if signal is None:
        signal = _score_0_100(context.signal_score) or 0.0
    quality = _score_0_100(context.quality_score)

    volatility = _score_0_100(context.volatility_percentile)
    if volatility is None:
        volatility = _score_0_100(
            _first_number(
                features,
                (
                    "volatility_percentile_30d",
                    "price_volatility_percentile_30d",
                    "volatility_percentile",
                ),
            )
        )
    if volatility is None:
        volatility = _score_volatility_proxy(
            _first_number(
                features,
                ("price_volatility_24h", "volatility_24h"),
            )
        )

    squeeze = _score_0_100(context.squeeze_score)
    if squeeze is None:
        squeeze = _score_squeeze(features, context.anomalies)

    liquidity = _score_0_100(context.liquidity_score)
    if liquidity is None:
        explicit_liquidity = _first_number(features, ("liquidity_score",))
        liquidity = _score_0_100(explicit_liquidity)
    if liquidity is None:
        volume = context.volume_24h_usd
        if volume is None:
            volume = _first_number(features, ("volume_24h_usd", "volume_quote_24h"))
        liquidity = _score_liquidity(volume)

    return PolicyScores(
        signal=signal,
        quality=quality,
        volatility=volatility,
        squeeze=squeeze,
        liquidity=liquidity,
    )


def materialize_template(
    template: ScaleInTemplateConfig,
    *,
    signal_price: float,
    target_drawdown: float,
) -> dict[str, Any]:
    if not math.isfinite(signal_price) or signal_price <= 0.0:
        raise ValueError("signal_price must be positive and finite")
    if not 0.0 < target_drawdown < 1.0:
        raise ValueError("target_drawdown must be between 0 and 1")

    legs = [
        {
            "index": index + 1,
            "offset_pct": round(offset * 100.0, 4),
            "allocation_pct": round(allocation * 100.0, 4),
            "price": round(signal_price * (1.0 + offset), 8),
        }
        for index, (offset, allocation) in enumerate(
            zip(template.entry_offsets, template.allocations, strict=True)
        )
    ]
    average = sum(
        leg["price"] * allocation
        for leg, allocation in zip(legs, template.allocations, strict=True)
    )
    stop_price = signal_price * (1.0 + template.hard_stop_pct)
    target_price = average * (1.0 - target_drawdown)
    stop_risk_pct = (stop_price - average) / average
    rr = target_drawdown / stop_risk_pct if stop_risk_pct > 0.0 else None
    return {
        "entry_legs": legs,
        "hard_stop_pct": round(template.hard_stop_pct * 100.0, 4),
        "hard_stop_price": round(stop_price, 8),
        "scale_in_hours": template.scale_in_hours,
        "horizon_hours": template.horizon_hours,
        "risk_multiplier": template.risk_multiplier,
        "projected_average_entry": round(average, 8),
        "projected_target_price": round(target_price, 8),
        "target_drawdown_pct": round(target_drawdown * 100.0, 4),
        "projected_stop_risk_pct": round(stop_risk_pct * 100.0, 4),
        "projected_rr_ratio": None if rr is None else round(rr, 4),
    }


def build_trade_setup(
    *,
    signal_price: float,
    context: PolicyContext,
    config: ExecutionPolicyRouterConfig | None = None,
    selector: PolicySelector | None = None,
    target_drawdown: float | None = None,
) -> dict[str, Any]:
    """Return legacy trade fields plus the complete versioned policy audit."""

    if not math.isfinite(signal_price) or signal_price <= 0.0:
        return {}
    resolved_config = config or ExecutionPolicyRouterConfig()
    target = target_drawdown or resolved_config.target_drawdown
    decision = ExecutionPolicyRouter(resolved_config, selector=selector).route(context)
    policy = decision.to_dict(signal_price=signal_price, target_drawdown=target)
    projected_average = float(policy["projected_average_entry"])
    return {
        "entry_price": round(signal_price, 8),
        "entry_zone": (
            f"${signal_price * 0.998:.4f} - ${signal_price * 1.005:.4f}"
        ),
        "stop_loss": policy["hard_stop_price"],
        "stop_loss_pct": policy["hard_stop_pct"],
        "tp1": round(projected_average * 0.92, 8),
        "tp1_pct": 8.0,
        "tp2": policy["projected_target_price"],
        "tp2_pct": round(target * 100.0, 4),
        "tp3": round(projected_average * 0.70, 8),
        "tp3_pct": 30.0,
        "rr_ratio": policy["projected_rr_ratio"],
        "target_basis": "weighted_average_after_each_fill",
        "entry_legs": policy["entry_legs"],
        "projected_average_entry": policy["projected_average_entry"],
        "projected_stop_risk_pct": policy["projected_stop_risk_pct"],
        "execution_policy": policy,
    }


class ExecutionPolicyRouter:
    """Choose a champion template and optionally record a shadow challenger."""

    def __init__(
        self,
        config: ExecutionPolicyRouterConfig | None = None,
        selector: PolicySelector | None = None,
    ) -> None:
        self.config = config or ExecutionPolicyRouterConfig()
        self.selector = selector
        self._templates = {item.policy_id: item for item in self.config.templates}

    def _rule_policy_id(self, scores: PolicyScores) -> tuple[str, list[str]]:
        reasons: list[str] = []
        if scores.volatility is None:
            reasons.append("volatility_unknown_fallback")
            return self.config.fallback_policy_id, reasons
        if (
            scores.volatility >= self.config.deep_volatility_min
            and scores.squeeze >= self.config.deep_squeeze_min
            and scores.signal >= self.config.deep_signal_min
        ):
            reasons.append("deep_squeeze_profile")
            return self.config.deep_policy_id, reasons
        if (
            scores.volatility < self.config.compact_volatility_max
            and scores.squeeze < 50.0
        ):
            reasons.append("compact_volatility_profile")
            return self.config.compact_policy_id, reasons
        reasons.append("balanced_volatility_profile")
        return self.config.fallback_policy_id, reasons

    def route(self, context: PolicyContext) -> PolicyDecision:
        scores = score_policy_context(context)
        policy_id, reasons = self._rule_policy_id(scores)
        eligible = self.config.enabled
        if not self.config.enabled:
            eligible = False
            reasons.append("router_disabled")
        if self.config.require_matching_label:
            if context.label_version is None:
                eligible = False
                reasons.append("signal_label_version_unknown")
            elif context.label_version != self.config.required_label_version:
                eligible = False
                reasons.append("signal_label_version_mismatch")
        if scores.signal < self.config.min_signal_score:
            eligible = False
            reasons.append("signal_below_minimum")
        if scores.quality is None:
            eligible = False
            reasons.append("quality_unknown")
        elif scores.quality < self.config.min_quality_score:
            eligible = False
            reasons.append("quality_below_minimum")
        if scores.liquidity is None:
            eligible = False
            reasons.append("liquidity_unknown")
        elif scores.liquidity < self.config.min_liquidity_score:
            eligible = False
            reasons.append("liquidity_below_minimum")
        if (
            scores.volatility is not None
            and scores.volatility >= self.config.skip_volatility_min
        ):
            eligible = False
            reasons.append("volatility_above_safety_ceiling")

        selector_name = "rule_selector"
        selector_version = self.config.router_version
        challenger_policy_id: str | None = None
        challenger_selector: str | None = None
        model_policy_id: str | None = None
        if self.selector is not None:
            model_policy_id = self.selector.select_policy(
                scores.to_dict(), tuple(self._templates)
            )
            if model_policy_id not in self._templates:
                reasons.append("selector_returned_unknown_policy")
                model_policy_id = None

        if self.config.selector_mode == "model":
            if model_policy_id is None:
                reasons.append("model_unavailable_fallback_rules")
            else:
                policy_id = model_policy_id
                selector_name = self.selector.name
                selector_version = self.selector.version
                reasons.append("model_policy_selected")
        elif self.config.selector_mode == "shadow_model":
            if model_policy_id is None:
                reasons.append("shadow_model_unavailable")
            else:
                challenger_policy_id = model_policy_id
                challenger_selector = f"{self.selector.name}:{self.selector.version}"
                reasons.append("shadow_model_recorded")

        policy = self._templates.get(policy_id)
        if policy is None:
            policy = self._templates[self.config.fallback_policy_id]
            reasons.append("unknown_rule_policy_fallback")
        return PolicyDecision(
            router_version=self.config.router_version,
            feature_schema_version=self.config.feature_schema_version,
            selector_name=selector_name,
            selector_version=selector_version,
            policy=policy,
            scores=scores,
            eligible=eligible,
            advisory_only=self.config.advisory_only,
            reason_codes=tuple(dict.fromkeys(reasons)),
            challenger_policy_id=challenger_policy_id,
            challenger_selector=challenger_selector,
        )


__all__ = [
    "ExecutionPolicyRouter",
    "PolicyContext",
    "PolicyDecision",
    "PolicyScores",
    "PolicySelector",
    "build_trade_setup",
    "materialize_template",
    "score_policy_context",
]
