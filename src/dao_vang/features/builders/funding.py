from dao_vang.features.models import FeatureDefinition
from dao_vang.features.registry import registry

FUNDING_RATE_RAW = FeatureDefinition(
    id="funding_rate_raw",
    version="1.0",
    description="Last known raw funding rate",
    lookback_minutes=0,
    missing_policy="fill_zero",
)

FUNDING_PERCENTILE_7D = FeatureDefinition(
    id="funding_percentile_7d",
    version="1.0",
    description="Funding rate percentile rank over the past 7 days",
    lookback_minutes=10080,
    missing_policy="fill_mean",
)

FUNDING_PERCENTILE_30D = FeatureDefinition(
    id="funding_percentile_30d",
    version="1.0",
    description="Funding rate percentile rank over the past 30 days",
    lookback_minutes=43200,
    missing_policy="fill_mean",
)

FUNDING_ZSCORE_30D = FeatureDefinition(
    id="funding_zscore_30d",
    version="1.0",
    description="Funding rate Z-score over the past 30 days",
    lookback_minutes=43200,
    missing_policy="fill_zero",
)

FUNDING_CHANGE_8H = FeatureDefinition(
    id="funding_change_8h",
    version="1.0",
    description="Funding rate absolute change over 8 hours",
    lookback_minutes=480,
    missing_policy="fill_zero",
)

FUNDING_CHANGE_24H = FeatureDefinition(
    id="funding_change_24h",
    version="1.0",
    description="Funding rate absolute change over 24 hours",
    lookback_minutes=1440,
    missing_policy="fill_zero",
)

FUNDING_PERSISTENCE_7D = FeatureDefinition(
    id="funding_persistence_7d",
    version="1.0",
    description="Rolling average of funding rate over 7 days (measures persistent high/low funding)",
    lookback_minutes=10080,
    missing_policy="fill_mean",
)

registry.register_feature(FUNDING_RATE_RAW)
registry.register_feature(FUNDING_PERCENTILE_7D)
registry.register_feature(FUNDING_PERCENTILE_30D)
registry.register_feature(FUNDING_ZSCORE_30D)
registry.register_feature(FUNDING_CHANGE_8H)
registry.register_feature(FUNDING_CHANGE_24H)
registry.register_feature(FUNDING_PERSISTENCE_7D)


def build_funding_features_sql(source_table: str) -> str:
    """
    Returns a SQL CTE that computes funding features from the source timeline table.
    Assumes `funding_rate_last_known` exists in the timeline (already joined with asof).
    """
    return f"""
    funding_features AS (
        SELECT
            feature_time,
            symbol,
            COALESCE(funding_rate_last_known, 0.0) AS {FUNDING_RATE_RAW.id},
            
            -- Relative position within 7d range
            (funding_rate_last_known - min(funding_rate_last_known) OVER w_2016) 
            / NULLIF(max(funding_rate_last_known) OVER w_2016 - min(funding_rate_last_known) OVER w_2016, 0) AS {FUNDING_PERCENTILE_7D.id},
            
            -- Relative position within 30d range
            (funding_rate_last_known - min(funding_rate_last_known) OVER w_8640) 
            / NULLIF(max(funding_rate_last_known) OVER w_8640 - min(funding_rate_last_known) OVER w_8640, 0) AS {FUNDING_PERCENTILE_30D.id},
            
            -- Z-score 30d
            (funding_rate_last_known - avg(funding_rate_last_known) OVER w_8640) / NULLIF(stddev_samp(funding_rate_last_known) OVER w_8640, 0) AS {FUNDING_ZSCORE_30D.id},
            
            -- Change 8h (lag 96)
            funding_rate_last_known - lag(funding_rate_last_known, 96) OVER w_all AS {FUNDING_CHANGE_8H.id},
            
            -- Change 24h (lag 288)
            funding_rate_last_known - lag(funding_rate_last_known, 288) OVER w_all AS {FUNDING_CHANGE_24H.id},
            
            -- Persistence 7d (rolling average)
            avg(funding_rate_last_known) OVER w_2016 AS {FUNDING_PERSISTENCE_7D.id}
            
        FROM {source_table}
        WINDOW
            w_all AS (PARTITION BY symbol ORDER BY feature_time),
            w_2016 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 2015 PRECEDING AND CURRENT ROW),
            w_8640 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 8639 PRECEDING AND CURRENT ROW)
    )
    """
