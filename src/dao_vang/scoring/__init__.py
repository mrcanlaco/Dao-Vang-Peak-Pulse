"""Scoring module — composite distribution score 0-100."""

from __future__ import annotations

from dao_vang.scoring.btc_context import BtcContext, classify_btc
from dao_vang.scoring.distribution_scorer import (
    DistributionScore,
    ScoreComponent,
    compute_distribution_score,
)
from dao_vang.scoring.evidence import (
    EVIDENCE_GROUPS,
    EVIDENCE_POLICY_VERSION,
    EvidenceDecision,
    evaluate_evidence,
    evidence_groups_for_components,
)
from dao_vang.scoring.frozen_inference import (
    FrozenInferenceError,
    SnapshotQuality,
    SnapshotScore,
    assess_snapshot_quality,
    score_snapshot,
)
from dao_vang.scoring.two_tier_scorer import (
    TwoTierDistributionScore,
    compute_two_tier_distribution_score,
)

__all__ = [
    "BtcContext",
    "classify_btc",
    "DistributionScore",
    "ScoreComponent",
    "compute_distribution_score",
    "TwoTierDistributionScore",
    "compute_two_tier_distribution_score",
    "FrozenInferenceError",
    "SnapshotQuality",
    "SnapshotScore",
    "assess_snapshot_quality",
    "score_snapshot",
    "EVIDENCE_GROUPS",
    "EVIDENCE_POLICY_VERSION",
    "EvidenceDecision",
    "evaluate_evidence",
    "evidence_groups_for_components",
]
