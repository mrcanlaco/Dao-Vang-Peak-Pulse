from dao_vang.scoring.evidence import (
    EVIDENCE_POLICY_VERSION,
    evaluate_evidence,
    evidence_groups_for_components,
)


def test_evidence_counts_groups_not_correlated_components() -> None:
    components = [
        {"name": "price_volume_divergence", "score": 90},
        {"name": "momentum_exhaustion", "score": 90},
        {"name": "distance_from_high", "score": 90},
    ]
    assert evidence_groups_for_components(components) == ("price_weakening",)
    decision = evaluate_evidence(components, min_groups=2)
    assert not decision.passed
    assert decision.reason_codes == ("insufficient_independent_evidence",)


def test_evidence_requires_fresh_quality() -> None:
    decision = evaluate_evidence(
        [
            {"name": "price_volume_divergence", "score": 80},
            {"name": "funding_spike", "score": 80},
        ],
        min_groups=2,
        quality_usable=False,
    )
    assert decision.policy_version == EVIDENCE_POLICY_VERSION
    assert not decision.passed
    assert "quality_gate_failed" in decision.reason_codes
