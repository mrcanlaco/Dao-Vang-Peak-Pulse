"""Frozen research contract. Never changes v1/v2 or live model defaults."""

import json
from dataclasses import asdict, dataclass
from hashlib import sha256


@dataclass(frozen=True)
class DistributionV3Spec:
    version: str = "distribution_short_v3_policy_48h"
    engine_version: str = "policy_path_v3.1"
    policy_id: str = "timing_compact_v1"
    horizon_hours: int = 48
    scale_in_hours: int = 6
    bar_minutes: int = 5
    target: float = 0.20
    stop: float = 0.16
    offsets: tuple[float, ...] = (0.0, 0.03, 0.06)
    notional_weights: tuple[float, ...] = (0.20, 0.30, 0.50)
    cost_per_side: float = 0.001
    intrabar_rule: str = "old_stop_first_then_old_target_then_adds_then_close"
    funding_rule: str = "settle_at_bar_open_before_orders;exclude_entry1_time"

    @property
    def checksum(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, allow_nan=False)
        return sha256(payload.encode()).hexdigest()


SPEC = DistributionV3Spec()


@dataclass(frozen=True)
class ReferenceTimingSpec:
    version: str = "challenger_reference_v3.1"
    min_return_24h: float = 0.15
    min_armed_peak_return_24h: float = 0.30
    min_episode_age_hours: int = 4
    confirmations: int = 2
    max_confirmation_gap_minutes: int = 90
    score_threshold: float = 0.39
    post_confirmation_score_tolerance: float = 0.10
    episode_gap_hours: int = 6
    cooldown_hours: int = 24
    scout_percentile_min: float = 0.80
    scout_persistence_min_exclusive: float = 0.0
    scout_change_min_exclusive: float = 0.0
    scout_max_distance_from_high: float = -0.02

TIMING = ReferenceTimingSpec()
