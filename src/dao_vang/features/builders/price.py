from dao_vang.features.models import FeatureDefinition
from dao_vang.features.registry import registry

# Define features
PRICE_RET_5M = FeatureDefinition(
    id="price_ret_5m",
    version="1.0",
    description="5-minute price return",
    lookback_minutes=5,
    missing_policy="ffill",
)

PRICE_RET_1H = FeatureDefinition(
    id="price_ret_1h",
    version="1.0",
    description="1-hour price return",
    lookback_minutes=60,
    missing_policy="ffill",
)

PRICE_RET_4H = FeatureDefinition(
    id="price_ret_4h",
    version="1.0",
    description="4-hour price return",
    lookback_minutes=240,
    missing_policy="ffill",
)

PRICE_RET_24H = FeatureDefinition(
    id="price_ret_24h",
    version="1.0",
    description="24-hour price return",
    lookback_minutes=1440,
    missing_policy="ffill",
)

PRICE_VOLATILITY_24H = FeatureDefinition(
    id="price_volatility_24h",
    version="1.0",
    description="24-hour rolling volatility (stddev of 5m returns)",
    lookback_minutes=1440,
    missing_policy="fill_mean",
)

DISTANCE_FROM_HIGH_24H = FeatureDefinition(
    id="distance_from_high_24h",
    version="1.0",
    description="Distance from the 24-hour rolling high",
    lookback_minutes=1440,
    missing_policy="fill_zero",
)

VOLUME_PERCENTILE_24H = FeatureDefinition(
    id="volume_percentile_24h",
    version="1.0",
    description="Volume percentile rank over the past 24 hours",
    lookback_minutes=1440,
    missing_policy="fill_mean",
)

MOMENTUM_DECELERATION_4H = FeatureDefinition(
    id="momentum_deceleration_4h",
    version="1.0",
    description="Change in 1h momentum over the past 4 hours",
    lookback_minutes=240,
    missing_policy="fill_zero",
)

# Register features
registry.register_feature(PRICE_RET_5M)
registry.register_feature(PRICE_RET_1H)
registry.register_feature(PRICE_RET_4H)
registry.register_feature(PRICE_RET_24H)
registry.register_feature(PRICE_VOLATILITY_24H)
registry.register_feature(DISTANCE_FROM_HIGH_24H)
registry.register_feature(VOLUME_PERCENTILE_24H)
registry.register_feature(MOMENTUM_DECELERATION_4H)


def build_price_features_sql(source_table: str) -> str:
    """
    Returns a SQL CTE that computes price features from the source timeline table.
    The source_table must contain: feature_time, close, high, volume_base.
    Assuming 5-minute intervals.
    """
    return f"""
    price_base AS (
        SELECT
            *,
            close / lag(close, 1) OVER w_all - 1 AS {PRICE_RET_5M.id},
            close / lag(close, 12) OVER w_all - 1 AS {PRICE_RET_1H.id},
            close / lag(close, 48) OVER w_all - 1 AS {PRICE_RET_4H.id},
            close / lag(close, 288) OVER w_all - 1 AS {PRICE_RET_24H.id}
        FROM {source_table}
        WINDOW w_all AS (PARTITION BY symbol ORDER BY feature_time)
    ),
    price_features AS (
        SELECT
            feature_time,
            symbol,
            {PRICE_RET_5M.id},
            {PRICE_RET_1H.id},
            {PRICE_RET_4H.id},
            {PRICE_RET_24H.id},
            
            stddev_samp({PRICE_RET_5M.id}) OVER w_288 AS {PRICE_VOLATILITY_24H.id},
            
            close / max(high) OVER w_288 - 1 AS {DISTANCE_FROM_HIGH_24H.id},
            
            -- Volume relative to 24h max
            volume_base / NULLIF(max(volume_base) OVER w_288, 0) AS {VOLUME_PERCENTILE_24H.id},
            
            -- Momentum deceleration: current 1h return - 1h return 3 hours ago (lag 36)
            {PRICE_RET_1H.id} - lag({PRICE_RET_1H.id}, 36) OVER w_all AS {MOMENTUM_DECELERATION_4H.id}
            
        FROM price_base
        WINDOW 
            w_all AS (PARTITION BY symbol ORDER BY feature_time),
            w_288 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 287 PRECEDING AND CURRENT ROW)
    )
    """
