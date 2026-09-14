from __future__ import annotations

import pytest
from pydantic import ValidationError

from dao_vang.config.settings import (
    ExecutionPolicyRouterConfig,
    ScaleInTemplateConfig,
)
from dao_vang.execution.policy_router import (
    ExecutionPolicyRouter,
    PolicyContext,
    materialize_template,
)


def _context(volatility: float, squeeze: float = 20.0) -> PolicyContext:
    return PolicyContext(
        signal_probability=0.82,
        label_version="distribution_short_v2",
        quality_score=0.92,
        volatility_percentile=volatility,
        squeeze_score=squeeze,
        volume_24h_usd=8_000_000,
    )


@pytest.mark.parametrize(
    ("context", "expected"),
    [
        (_context(50.0), "scale_in_compact"),
        (_context(75.0), "scale_in_balanced"),
        (_context(92.0, 80.0), "scale_in_deep_squeeze"),
    ],
)
def test_rule_router_selects_frozen_profile(context, expected):
    decision = ExecutionPolicyRouter().route(context)

    assert decision.policy.policy_id == expected
    assert decision.eligible is True


def test_extreme_volatility_is_not_eligible():
    decision = ExecutionPolicyRouter().route(_context(98.0, 90.0))

    assert decision.eligible is False
    assert "volatility_above_safety_ceiling" in decision.reason_codes


def test_balanced_template_materializes_weighted_average_target_and_rr():
    config = ExecutionPolicyRouterConfig()
    template = next(
        item for item in config.templates
        if item.policy_id == "scale_in_balanced"
    )

    plan = materialize_template(
        template,
        signal_price=100.0,
        target_drawdown=0.20,
    )

    assert [leg["price"] for leg in plan["entry_legs"]] == [100.0, 105.0, 110.0]
    assert plan["projected_average_entry"] == 106.5
    assert plan["projected_target_price"] == 85.2
    assert plan["hard_stop_price"] == 116.0
    assert plan["projected_rr_ratio"] == 2.2421


class _Selector:
    name = "test_selector"
    version = "2026-09-13"

    def __init__(self, choice: str):
        self.choice = choice

    def select_policy(self, features, available_policy_ids):
        assert set(features) == {
            "signal", "quality", "volatility", "squeeze", "liquidity"
        }
        assert self.choice in available_policy_ids or self.choice == "invented"
        return self.choice


def test_shadow_model_records_challenger_but_keeps_rule_champion():
    config = ExecutionPolicyRouterConfig(selector_mode="shadow_model")
    decision = ExecutionPolicyRouter(
        config,
        selector=_Selector("scale_in_deep_squeeze"),
    ).route(_context(50.0))

    assert decision.policy.policy_id == "scale_in_compact"
    assert decision.challenger_policy_id == "scale_in_deep_squeeze"
    assert decision.selector_name == "rule_selector"


def test_model_cannot_invent_a_runtime_policy():
    config = ExecutionPolicyRouterConfig(selector_mode="model")
    decision = ExecutionPolicyRouter(
        config,
        selector=_Selector("invented"),
    ).route(_context(75.0))

    assert decision.policy.policy_id == "scale_in_balanced"
    assert "selector_returned_unknown_policy" in decision.reason_codes
    assert "model_unavailable_fallback_rules" in decision.reason_codes


def test_template_rejects_stop_below_last_entry():
    with pytest.raises(ValidationError):
        ScaleInTemplateConfig(
            policy_id="unsafe",
            entry_offsets=[0.0, 0.08, 0.14],
            allocations=[0.1, 0.3, 0.6],
            hard_stop_pct=0.12,
        )

def test_raw_live_volatility_feature_uses_versioned_proxy():
    decision = ExecutionPolicyRouter().route(
        PolicyContext(
            signal_probability=0.82,
            label_version="distribution_short_v2",
            quality_score=0.92,
            squeeze_score=20.0,
            volume_24h_usd=8_000_000,
            features={"price_volatility_24h": 0.002},
        )
    )

    assert decision.scores.volatility == 35.0
    assert decision.policy.policy_id == "scale_in_compact"
    assert "volatility_unknown_fallback" not in decision.reason_codes

def test_raw_volatility_proxy_caps_extreme_values():
    decision = ExecutionPolicyRouter().route(
        PolicyContext(
            signal_probability=0.82,
            label_version="distribution_short_v2",
            quality_score=0.92,
            squeeze_score=90.0,
            volume_24h_usd=8_000_000,
            features={"price_volatility_24h": 0.03},
        )
    )

    assert decision.scores.volatility == 100.0
    assert decision.eligible is False

def test_calibrated_probability_is_preferred_to_heuristic_score():
    decision = ExecutionPolicyRouter().route(
        PolicyContext(
            signal_probability=0.82,
            label_version="distribution_short_v2",
            signal_score=20.0,
            quality_score=0.92,
            volatility_percentile=75.0,
            squeeze_score=20.0,
            volume_24h_usd=8_000_000,
        )
    )

    assert decision.scores.signal == 82.0
    assert decision.eligible is True

def test_v1_signal_is_advisory_only_for_v2_execution_contract():
    decision = ExecutionPolicyRouter().route(
        PolicyContext(
            signal_probability=0.82,
            label_version="distribution_short_v1",
            quality_score=0.92,
            volatility_percentile=75.0,
            squeeze_score=20.0,
            volume_24h_usd=8_000_000,
        )
    )

    assert decision.eligible is False
    assert "signal_label_version_mismatch" in decision.reason_codes
