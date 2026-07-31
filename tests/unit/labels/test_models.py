from datetime import datetime, timezone
from decimal import Decimal

from dao_vang.labels.models import DistributionLabelResult


def test_distribution_label_result_valid():
    dt = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)

    result = DistributionLabelResult(
        signal_time=dt,
        signal_price=Decimal("100.0"),
        label_value=1,
        target_reached=True,
        target_time=dt,
        lead_time_minutes=0,
        max_adverse_excursion=0.01,
        max_favorable_excursion_24h=0.09,
        future_max_high=Decimal("101.0"),
        future_min_low=Decimal("90.0"),
    )

    assert result.signal_time == dt
    assert result.signal_price == Decimal("100.0")
    assert result.label_version == "0.1.0"
    assert result.label_value == 1
    assert result.target_reached is True


def test_distribution_label_result_null():
    dt = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)

    result = DistributionLabelResult(
        signal_time=dt,
        signal_price=Decimal("100.0"),
        exclusion_reason="ambiguous_intrabar",
    )

    assert result.label_value is None
    assert result.target_reached is None
    assert result.exclusion_reason == "ambiguous_intrabar"
