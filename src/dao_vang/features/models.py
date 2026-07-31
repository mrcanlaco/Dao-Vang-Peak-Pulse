from typing import Literal

from pydantic import BaseModel, Field


class FeatureDefinition(BaseModel):
    """
    Metadata model for a single feature definition.
    """

    id: str = Field(..., description="Unique identifier for the feature")
    version: str = Field(..., description="Version of the feature logic")
    description: str = Field(
        ..., description="Business rationale and what this feature measures"
    )
    lookback_minutes: int = Field(
        default=0,
        description="Minutes of historical data required to compute this feature",
    )
    missing_policy: Literal[
        "drop", "fill_zero", "fill_mean", "ffill", "bfill", "null"
    ] = Field(default="null", description="Policy for handling missing values")
    point_in_time: bool = Field(
        default=True, description="Whether the feature is point-in-time safe"
    )


class FeatureSetVersion(BaseModel):
    """
    Collection of features representing a specific model input version.
    """

    id: str = Field(..., description="Unique identifier for the feature set")
    version: str = Field(..., description="Version of the feature set")
    description: str = Field(..., description="Description of the feature set purpose")
    features: list[FeatureDefinition] = Field(
        default_factory=list, description="List of included features"
    )
