from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class DistributionShortV1Spec:
    horizon_hours: int
    target_drawdown: Decimal = Decimal("0.08")
    max_adverse_excursion: Decimal = Decimal("0.04")
    gap_tolerance_minutes: int = 15
    version: str = "distribution_short_v1"

specs = {
    6: DistributionShortV1Spec(horizon_hours=6),
    12: DistributionShortV1Spec(horizon_hours=12),
    24: DistributionShortV1Spec(horizon_hours=24),
}
