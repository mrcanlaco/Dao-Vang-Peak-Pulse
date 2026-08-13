from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class DistributionLabelResultV1(BaseModel):
    signal_time: datetime
    symbol: str
    signal_price: Decimal
    label_version: str
    horizon_hours: int

    label_value: Optional[int] = None
    target_reached: Optional[bool] = None
    target_time: Optional[datetime] = None
    lead_time_minutes: Optional[float] = None

    max_adverse_excursion: Optional[float] = None
    max_favorable_excursion: Optional[float] = None

    future_max_high: Optional[Decimal] = None
    future_min_low: Optional[Decimal] = None

    exclusion_reason: Optional[str] = None
    
    # Intrabar ambiguity flag
    ambiguous_intrabar: bool = False

    # Preserve the quality decision used during materialization.  These fields
    # have defaults so older serialized label rows remain readable.
    quality_status: Optional[str] = None
    event_id: Optional[str] = None
