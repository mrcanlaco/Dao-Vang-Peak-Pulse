"""Independent evidence-group policy for high-confidence decisions.

Several indicators can be correlated (for example funding and a positioning
ratio).  Counting each indicator independently would overstate confidence, so
the policy counts only the three domain groups defined here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

EVIDENCE_POLICY_VERSION = "evidence_groups_v1"

EVIDENCE_GROUPS: dict[str, frozenset[str]] = {
    "price_weakening": frozenset(
        {
            "price_volume_divergence",
            "momentum_exhaustion",
            "distance_from_high",
        }
    ),
    "derivs_abnormality": frozenset(
        {
            "funding_spike",
            "oi_divergence",
            "global_long_short_ratio",
            "top_long_short_account_ratio",
            "top_long_short_position_ratio",
        }
    ),
    "sell_pressure": frozenset(
        {
            "taker_sell_pressure",
            "fake_breakout",
        }
    ),
}


@dataclass(frozen=True)
class EvidenceDecision:
    """Result of evaluating evidence groups for one snapshot."""

    groups: tuple[str, ...]
    count: int
    passed: bool
    policy_version: str = EVIDENCE_POLICY_VERSION
    reason_codes: tuple[str, ...] = ()

    @property
    def evidence_groups(self) -> tuple[str, ...]:
        return self.groups


def _component_values(component: Any) -> tuple[str, float, str | None]:
    if isinstance(component, Mapping):
        name = str(component.get("name", ""))
        score = component.get("score", 0.0)
        reason = component.get("reason_code") or component.get("reason")
    else:
        name = str(getattr(component, "name", ""))
        score = getattr(component, "score", 0.0)
        reason = getattr(component, "reason_code", None)
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        numeric_score = 0.0
    return name, numeric_score, str(reason) if reason else None


def evidence_groups_for_components(
    components: Iterable[Any], *, min_component_score: float = 50.0
) -> tuple[str, ...]:
    """Return unique independent groups supported by strong components."""

    groups: set[str] = set()
    for component in components:
        name, score, _ = _component_values(component)
        if score < min_component_score:
            continue
        for group, names in EVIDENCE_GROUPS.items():
            if name in names:
                groups.add(group)
                break
    return tuple(group for group in EVIDENCE_GROUPS if group in groups)


def evaluate_evidence(
    components: Iterable[Any],
    *,
    min_groups: int = 2,
    min_component_score: float = 50.0,
    quality_usable: bool = True,
    reason_codes: Iterable[str] = (),
) -> EvidenceDecision:
    """Apply the independent evidence rule with a fresh-data gate."""

    if min_groups < 1 or min_groups > len(EVIDENCE_GROUPS):
        raise ValueError("min_groups must be between 1 and the number of groups")
    groups = evidence_groups_for_components(
        components, min_component_score=min_component_score
    )
    reasons = list(reason_codes)
    if not quality_usable:
        reasons.append("quality_gate_failed")
    if len(groups) < min_groups:
        reasons.append("insufficient_independent_evidence")
    return EvidenceDecision(
        groups=groups,
        count=len(groups),
        passed=quality_usable and len(groups) >= min_groups,
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


# Short aliases for callers that use policy terminology.
independent_evidence_groups = evidence_groups_for_components
check_evidence_policy = evaluate_evidence
