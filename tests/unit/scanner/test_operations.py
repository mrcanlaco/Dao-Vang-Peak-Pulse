from __future__ import annotations

from dao_vang.scanner.operations import (
    KillSwitch,
    RollbackManager,
    compute_prediction_drift,
    evaluate_canary_policy,
)


def test_kill_switch_is_fail_closed_for_malformed_state(tmp_path):
    path = tmp_path / "kill.json"
    switch = KillSwitch(path)
    assert switch.active is False
    path.write_text("not-json", encoding="utf-8")
    assert switch.active is True
    switch.clear()
    assert switch.active is False
    switch.activate("incident")
    assert switch.state()["reason"] == "incident"


def test_canary_requires_high_confidence_and_budget():
    common = dict(
        mode="canary",
        quality_status="valid",
        calibrated_probability=0.9,
        threshold=0.6,
        in_cooldown=False,
        global_count=0,
        coin_count=0,
        global_limit=2,
        coin_limit=1,
    )
    assert evaluate_canary_policy(tier="WATCH", **common).reason == "tier_not_high_confidence"
    assert evaluate_canary_policy(tier="HIGH_CONFIDENCE", **common).allowed
    assert evaluate_canary_policy(tier="HIGH_CONFIDENCE", **{**common, "global_count": 2}).reason == "global_daily_budget_exhausted"
    assert evaluate_canary_policy(tier="HIGH_CONFIDENCE", **{**common, "kill_switch_active": True}).reason == "kill_switch_active"
    assert not evaluate_canary_policy(**{**common, "mode": "shadow", "tier": "HIGH_CONFIDENCE"}).allowed
    assert evaluate_canary_policy(
        **{
            **common,
            "mode": "shadow",
            "tier": "HIGH_CONFIDENCE",
            "allow_shadow_telegram": True,
        }
    ).allowed
    shadow_observation = evaluate_canary_policy(
        **{
            **common,
            "mode": "shadow",
            "tier": "WAIT",
            "quality_status": "invalid",
            "allow_shadow_telegram": True,
        }
    )
    assert shadow_observation.allowed
    assert shadow_observation.reason == "shadow_observation"
    shadow_without_probability = evaluate_canary_policy(
        **{
            **common,
            "mode": "shadow",
            "tier": "WAIT",
            "quality_status": "invalid",
            "calibrated_probability": None,
            "allow_shadow_telegram": True,
        }
    )
    assert shadow_without_probability.allowed
    shadow_limits_are_ignored = evaluate_canary_policy(
        **{
            **common,
            "mode": "shadow",
            "tier": "WAIT",
            "quality_status": "invalid",
            "calibrated_probability": None,
            "in_cooldown": True,
            "global_count": 999,
            "coin_count": 999,
            "allow_shadow_telegram": True,
        }
    )
    assert shadow_limits_are_ignored.allowed
    assert shadow_limits_are_ignored.reason == "shadow_observation"

    telegram_threshold = {
        **common,
        "mode": "shadow",
        "tier": "WAIT",
        "allow_shadow_telegram": True,
        "telegram_min_probability": 0.70,
    }
    assert evaluate_canary_policy(
        **{**telegram_threshold, "calibrated_probability": 0.701}
    ).allowed
    assert evaluate_canary_policy(
        **{**telegram_threshold, "calibrated_probability": 0.70}
    ).reason == "telegram_probability_below_threshold"
    assert evaluate_canary_policy(
        **{**telegram_threshold, "calibrated_probability": 0.69}
    ).reason == "telegram_probability_below_threshold"
    assert evaluate_canary_policy(
        **{**telegram_threshold, "calibrated_probability": None}
    ).reason == "telegram_probability_missing"

    # Gated allowed_tiers testing
    assert evaluate_canary_policy(
        **{
            **telegram_threshold,
            "calibrated_probability": 0.85,
            "tier": "WATCH",
            "allowed_tiers": ["HIGH_CONFIDENCE"],
        }
    ).reason == "tier_not_allowed"

    assert evaluate_canary_policy(
        **{
            **telegram_threshold,
            "calibrated_probability": 0.85,
            "tier": "HIGH_CONFIDENCE",
            "allowed_tiers": ["HIGH_CONFIDENCE"],
        }
    ).allowed

    # Shadow cooldown enforcement testing
    assert evaluate_canary_policy(
        **{
            **telegram_threshold,
            "calibrated_probability": 0.85,
            "in_cooldown": True,
            "enforce_shadow_cooldown": True,
        }
    ).reason == "cooldown_active"


def test_drift_does_not_claim_kpi_with_small_sample():
    result = compute_prediction_drift([0.1, 0.2], [0.8, 0.9], min_samples=3)
    assert result.status == "insufficient_data"
    assert result.psi is None


def test_rollback_drill_does_not_drop_audit(tmp_path):
    manager = RollbackManager(tmp_path / "rollback.json")
    manager.promote("bundle-a", mode="canary")
    state = manager.rollback_to_shadow(reason="drift")
    assert state["mode"] == "shadow"
    report = manager.run_drill(audit_count_before=10, audit_count_after=10)
    assert report["status"] == "pass"
    assert (tmp_path / "rollback_drill.json").exists()
