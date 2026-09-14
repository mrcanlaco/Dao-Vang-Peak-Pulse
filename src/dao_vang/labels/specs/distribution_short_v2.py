"""Label contract for detecting a 20% drawdown within 24 hours.

This is intentionally versioned separately from ``distribution_short_v1``.
Changing the v1 thresholds in place would invalidate historical labels and
make existing frozen-model evidence impossible to reproduce.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DistributionShortV2Spec:
    horizon_hours: int = 24
    target_drawdown: Decimal = Decimal("0.20")
    max_adverse_excursion: Decimal = Decimal("0.16")
    gap_tolerance_minutes: int = 15
    version: str = "distribution_short_v2"


specs = {24: DistributionShortV2Spec()}


__all__ = ["DistributionShortV2Spec", "specs"]
