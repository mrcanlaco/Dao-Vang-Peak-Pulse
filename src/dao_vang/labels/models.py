from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class DistributionLabelResult(BaseModel):
    """
    Result model for the Distribution Label v0.1 engine.
    Measures early detection of a significant downside distribution after a signal.
    """

    signal_time: datetime = Field(..., description="Time of the signal (UTC)")
    symbol: str = Field(..., description="Trading pair symbol")
    signal_price: Decimal = Field(
        ..., description="Price at the signal time (e.g., close price)"
    )
    label_version: str = Field(
        default="0.1.0", description="Version of the label engine"
    )

    label_value: Optional[int] = Field(
        default=None,
        description="1 if target reached without exceeding MAE, 0 if not. None if ambiguous or invalid.",
    )
    target_reached: Optional[bool] = Field(
        default=None, description="Whether the target was reached within horizon"
    )
    target_time: Optional[datetime] = Field(
        default=None, description="Time the target was first reached, if reached"
    )
    lead_time_minutes: Optional[int] = Field(
        default=None, description="Minutes between signal and target_time"
    )

    max_adverse_excursion: Optional[float] = Field(
        default=None,
        description="Max adverse excursion (upside) before target or end of horizon",
    )
    max_favorable_excursion_24h: Optional[float] = Field(
        default=None, description="Max favorable excursion (downside) within 24h"
    )

    future_max_high: Optional[Decimal] = Field(
        default=None, description="Highest high in the 24h horizon"
    )
    future_min_low: Optional[Decimal] = Field(
        default=None, description="Lowest low in the 24h horizon"
    )

    exclusion_reason: Optional[str] = Field(
        default=None,
        description="Reason for exclusion (e.g., missing_future_data, ambiguous_intrabar)",
    )
