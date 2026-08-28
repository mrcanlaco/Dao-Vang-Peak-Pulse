from dao_vang.features.models import FeatureDefinition
from dao_vang.features.registry import registry

OI_CHANGE_1H = FeatureDefinition(
    id="oi_change_1h",
    version="1.0",
    description="Open interest value percentage change over 1 hour",
    lookback_minutes=60,
    missing_policy="fill_zero",
)

OI_CHANGE_4H = FeatureDefinition(
    id="oi_change_4h",
    version="1.0",
    description="Open interest value percentage change over 4 hours",
    lookback_minutes=240,
    missing_policy="fill_zero",
)

OI_CHANGE_24H = FeatureDefinition(
    id="oi_change_24h",
    version="1.0",
    description="Open interest value percentage change over 24 hours",
    lookback_minutes=1440,
    missing_policy="fill_zero",
)

OI_ZSCORE_7D = FeatureDefinition(
    id="oi_zscore_7d",
    version="1.0",
    description="Z-score of Open Interest over the past 7 days",
    lookback_minutes=10080,
    missing_policy="fill_zero",
)

OI_ACCELERATION_1H = FeatureDefinition(
    id="oi_acceleration_1h",
    version="1.0",
    description="Change in 1h OI return over the past 1h (second derivative)",
    lookback_minutes=120,
    missing_policy="fill_zero",
)

PRICE_OI_DIVERGENCE_1H = FeatureDefinition(
    id="price_oi_divergence_1h",
    version="1.0",
    description="Product of price return 1h and OI return 1h. Negative means divergence.",
    lookback_minutes=60,
    missing_policy="fill_zero",
)

registry.register_feature(OI_CHANGE_1H)
registry.register_feature(OI_CHANGE_4H)
registry.register_feature(OI_CHANGE_24H)
registry.register_feature(OI_ZSCORE_7D)
registry.register_feature(OI_ACCELERATION_1H)
registry.register_feature(PRICE_OI_DIVERGENCE_1H)


def build_oi_features_sql(source_table: str) -> str:
    """
    Returns a SQL CTE that computes Open Interest features from the source timeline table.
    Assumes `open_interest_value` and `close` exist in the source_table.
    """
    return f"""
    oi_base AS (
        SELECT
            *,
            -- Safe division for returns
            open_interest_value / NULLIF(lag(open_interest_value, 12) OVER w_all, 0) - 1 AS oi_ret_1h,
            open_interest_value / NULLIF(lag(open_interest_value, 48) OVER w_all, 0) - 1 AS oi_ret_4h,
            open_interest_value / NULLIF(lag(open_interest_value, 288) OVER w_all, 0) - 1 AS oi_ret_24h,
            
            close / NULLIF(lag(close, 12) OVER w_all, 0) - 1 AS price_ret_1h
        FROM {source_table}
        WINDOW w_all AS (PARTITION BY symbol ORDER BY feature_time)
    ),
    oi_features AS (
        SELECT
            feature_time,
            symbol,
            
            -- Fall back to 0 change if history is missing, but propagate NULL if current value is missing
            CASE WHEN open_interest_value IS NULL THEN NULL ELSE COALESCE(oi_ret_1h, 0.0) END AS {OI_CHANGE_1H.id},
            CASE WHEN open_interest_value IS NULL THEN NULL ELSE COALESCE(oi_ret_4h, 0.0) END AS {OI_CHANGE_4H.id},
            CASE WHEN open_interest_value IS NULL THEN NULL ELSE COALESCE(oi_ret_24h, 0.0) END AS {OI_CHANGE_24H.id},
            
            -- Z-score 7d (2016 periods)
            (open_interest_value - avg(open_interest_value) OVER w_2016) / NULLIF(stddev_samp(open_interest_value) OVER w_2016, 0) AS {OI_ZSCORE_7D.id},
            
            -- Acceleration: current 1h return - 1h return 1h ago
            -- Fall back to 0 acceleration if history is missing, but propagate NULL if current value is missing
            CASE WHEN open_interest_value IS NULL THEN NULL ELSE COALESCE(oi_ret_1h - lag(oi_ret_1h, 12) OVER w_all, 0.0) END AS {OI_ACCELERATION_1H.id},
            
            -- Divergence
            price_ret_1h * oi_ret_1h AS {PRICE_OI_DIVERGENCE_1H.id}
            
        FROM oi_base
        WINDOW 
            w_all AS (PARTITION BY symbol ORDER BY feature_time),
            w_2016 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 2015 PRECEDING AND CURRENT ROW)
    )
    """
