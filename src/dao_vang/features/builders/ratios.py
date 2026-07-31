from dao_vang.features.models import FeatureDefinition
from dao_vang.features.registry import registry

GLOBAL_LS_RATIO = FeatureDefinition(
    id="global_ls_ratio",
    version="1.0",
    description="Global long/short ratio",
    lookback_minutes=0,
    missing_policy="fill_mean",
)

TOP_LS_RATIO = FeatureDefinition(
    id="top_ls_ratio",
    version="1.0",
    description="Top trader long/short ratio",
    lookback_minutes=0,
    missing_policy="fill_mean",
)

RETAIL_TOP_SPREAD = FeatureDefinition(
    id="retail_top_spread",
    version="1.0",
    description="Spread between global LS ratio and top trader LS ratio",
    lookback_minutes=0,
    missing_policy="fill_zero",
)

SPREAD_TREND_1H = FeatureDefinition(
    id="spread_trend_1h",
    version="1.0",
    description="Moving average of retail-top spread over 1 hour",
    lookback_minutes=60,
    missing_policy="fill_zero",
)

SPREAD_TREND_4H = FeatureDefinition(
    id="spread_trend_4h",
    version="1.0",
    description="Moving average of retail-top spread over 4 hours",
    lookback_minutes=240,
    missing_policy="fill_zero",
)

registry.register_feature(GLOBAL_LS_RATIO)
registry.register_feature(TOP_LS_RATIO)
registry.register_feature(RETAIL_TOP_SPREAD)
registry.register_feature(SPREAD_TREND_1H)
registry.register_feature(SPREAD_TREND_4H)


def build_ratio_features_sql(source_table: str) -> str:
    """
    Returns a SQL CTE that computes ratio features from the source timeline table.
    Assumes `global_long_short_ratio` and `top_long_short_ratio` exist in the source_table.
    """
    return f"""
    ratios_base AS (
        SELECT
            *,
            COALESCE(global_long_short_ratio, 1.0) AS global_ls,
            COALESCE(top_long_short_ratio, 1.0) AS top_ls
        FROM {source_table}
    ),
    ratios_features AS (
        SELECT
            feature_time,
            
            global_ls AS {GLOBAL_LS_RATIO.id},
            top_ls AS {TOP_LS_RATIO.id},
            
            -- Spread
            global_ls - top_ls AS {RETAIL_TOP_SPREAD.id},
            
            -- Spread Trend 1h (12 periods)
            avg(global_ls - top_ls) OVER w_12 AS {SPREAD_TREND_1H.id},
            
            -- Spread Trend 4h (48 periods)
            avg(global_ls - top_ls) OVER w_48 AS {SPREAD_TREND_4H.id}
            
        FROM ratios_base
        WINDOW 
            w_12 AS (ORDER BY feature_time ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
            w_48 AS (ORDER BY feature_time ROWS BETWEEN 47 PRECEDING AND CURRENT ROW)
    )
    """
