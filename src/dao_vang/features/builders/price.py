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

PRICE_RET_15M = FeatureDefinition(
    id="price_ret_15m",
    version="1.0",
    description="15-minute price return",
    lookback_minutes=15,
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

VOLUME_ZSCORE_24H = FeatureDefinition(
    id="volume_zscore_24h",
    version="1.0",
    description="Current 5-minute volume Z-score over the past 24 hours",
    lookback_minutes=1440,
    missing_policy="fill_zero",
)

VOLUME_RATIO_1H = FeatureDefinition(
    id="volume_ratio_1h",
    version="1.0",
    description="Current 1-hour volume divided by the preceding 1-hour volume",
    lookback_minutes=120,
    missing_policy="fill_zero",
)

MOMENTUM_DECELERATION_4H = FeatureDefinition(
    id="momentum_deceleration_4h",
    version="1.0",
    description="Change in 1h momentum over the past 4 hours",
    lookback_minutes=240,
    missing_policy="fill_zero",
)

MOMENTUM_DECEL_15M = FeatureDefinition(
    id="momentum_decel_15m",
    version="1.0",
    description="Short-term momentum deceleration (15-minute)",
    lookback_minutes=30,
    missing_policy="fill_zero",
)

LOWER_HIGH_4H = FeatureDefinition(
    id="lower_high_4h",
    version="1.0",
    description="Boolean flag when current 4h high is lower than previous 4h high",
    lookback_minutes=480,
    missing_policy="fill_zero",
)

VOLUME_DRY_UP_1H = FeatureDefinition(
    id="volume_dry_up_1h",
    version="1.0",
    description="Current 1h volume divided by moving average of last 12 1h volumes",
    lookback_minutes=780,
    missing_policy="fill_zero",
)

FAKE_BREAKOUT_1H = FeatureDefinition(
    id="fake_breakout_1h",
    version="1.0",
    description=(
        "False breakout (bull trap) score 0-1 over the last 1h. "
        "1.0 = candle poked above the prior 12-candle high then closed "
        "back below it (FOMO bait). 0.0 = no breakout or breakout held."
    ),
    lookback_minutes=60,
    missing_policy="fill_zero",
)

# Register features
registry.register_feature(PRICE_RET_5M)
registry.register_feature(PRICE_RET_1H)
registry.register_feature(PRICE_RET_15M)
registry.register_feature(PRICE_RET_4H)
registry.register_feature(PRICE_RET_24H)
registry.register_feature(PRICE_VOLATILITY_24H)
registry.register_feature(DISTANCE_FROM_HIGH_24H)
registry.register_feature(VOLUME_PERCENTILE_24H)
registry.register_feature(VOLUME_ZSCORE_24H)
registry.register_feature(VOLUME_RATIO_1H)
registry.register_feature(MOMENTUM_DECELERATION_4H)
registry.register_feature(MOMENTUM_DECEL_15M)
registry.register_feature(LOWER_HIGH_4H)
registry.register_feature(VOLUME_DRY_UP_1H)
registry.register_feature(FAKE_BREAKOUT_1H)

def build_price_features_sql(source_table: str) -> str:
    """
    The source_table must contain: feature_time, close, high, volume_base.
    Assuming 5-minute intervals.
    """
    return f"""
    price_base AS (
        SELECT
            *,
            close / lag(close, 1) OVER w_all - 1 AS {PRICE_RET_5M.id},
            close / lag(close, 12) OVER w_all - 1 AS {PRICE_RET_1H.id},
            close / lag(close, 3) OVER w_all - 1 AS {PRICE_RET_15M.id},
            close / lag(close, 48) OVER w_all - 1 AS {PRICE_RET_4H.id},
            close / lag(close, 288) OVER w_all - 1 AS {PRICE_RET_24H.id},
            max(high) OVER w_12_prev AS prev_max_high_12,
            
            max(high) OVER w_48 AS high_4h,
            sum(volume_base) OVER w_12 AS quote_volume_1h
        FROM {source_table}
        WINDOW
            w_all AS (PARTITION BY symbol ORDER BY feature_time),
            w_12_prev AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING),
            w_48 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 47 PRECEDING AND CURRENT ROW),
            w_12 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
    ),
    price_features AS (
        SELECT
            feature_time,
            symbol,
            {PRICE_RET_5M.id},
            {PRICE_RET_1H.id},
            {PRICE_RET_15M.id},
            {PRICE_RET_4H.id},
            {PRICE_RET_24H.id},
            
            stddev_samp({PRICE_RET_5M.id}) OVER w_288 AS {PRICE_VOLATILITY_24H.id},
            
            close / max(high) OVER w_288 - 1 AS {DISTANCE_FROM_HIGH_24H.id},
            
            -- Volume relative to 24h max
            volume_base / NULLIF(max(volume_base) OVER w_288, 0) AS {VOLUME_PERCENTILE_24H.id},

            -- A percentile alone cannot distinguish a regularly active coin
            -- from a one-candle shock. Keep both a distribution-normalized
            -- score and a one-hour versus prior-hour ratio for the radar.
            (volume_base - avg(volume_base) OVER w_288)
                / NULLIF(stddev_samp(volume_base) OVER w_288, 0)
                AS {VOLUME_ZSCORE_24H.id},
            sum(volume_base) OVER w_12
                / NULLIF(sum(volume_base) OVER w_prev_12, 0)
                AS {VOLUME_RATIO_1H.id},
            
            -- Momentum deceleration: current 1h return - 1h return 3 hours ago (lag 36)
            {PRICE_RET_1H.id} - lag({PRICE_RET_1H.id}, 36) OVER w_all AS {MOMENTUM_DECELERATION_4H.id},

            -- Multi-timeframe features
            {PRICE_RET_15M.id} - lag({PRICE_RET_15M.id}, 3) OVER w_all AS {MOMENTUM_DECEL_15M.id},
            CASE WHEN high_4h < lag(high_4h, 48) OVER w_all THEN 1.0 ELSE 0.0 END AS {LOWER_HIGH_4H.id},
            quote_volume_1h / NULLIF(avg(quote_volume_1h) OVER w_144_prev, 0) AS {VOLUME_DRY_UP_1H.id},

            -- False breakout (bull trap): high poked above prior 12-candle high
            -- but close fell back below it. Continuous 0-1 score scaled by
            -- reclaim depth (2% reclaim = full 1.0).
            CASE
                WHEN prev_max_high_12 IS NOT NULL
                    AND high > prev_max_high_12
                    AND close < prev_max_high_12
                THEN LEAST(
                    1.0,
                    (prev_max_high_12 - close) / NULLIF(prev_max_high_12, 0) / 0.02
                )
                ELSE 0.0
            END AS {FAKE_BREAKOUT_1H.id}
            
        FROM price_base
        WINDOW 
            w_all AS (PARTITION BY symbol ORDER BY feature_time),
            w_288 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 287 PRECEDING AND CURRENT ROW),
            w_12 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
            w_prev_12 AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 23 PRECEDING AND 12 PRECEDING),
            w_144_prev AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 144 PRECEDING AND 1 PRECEDING)
    )
    """
