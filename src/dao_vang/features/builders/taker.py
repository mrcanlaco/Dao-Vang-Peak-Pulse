from dao_vang.features.models import FeatureDefinition
from dao_vang.features.registry import registry

TAKER_BUY_RATIO = FeatureDefinition(
    id="taker_buy_ratio",
    version="1.0",
    description="Taker buy volume / total volume",
    lookback_minutes=0,
    missing_policy="fill_mean",
)

TAKER_BUY_RATIO_TREND_1H = FeatureDefinition(
    id="taker_buy_ratio_trend_1h",
    version="1.0",
    description="Moving average of taker buy ratio over 1 hour",
    lookback_minutes=60,
    missing_policy="fill_mean",
)

TAKER_BUY_RATIO_TREND_4H = FeatureDefinition(
    id="taker_buy_ratio_trend_4h",
    version="1.0",
    description="Moving average of taker buy ratio over 4 hours",
    lookback_minutes=240,
    missing_policy="fill_mean",
)

TAKER_BUY_RATIO_CHANGE_1H = FeatureDefinition(
    id="taker_buy_ratio_change_1h",
    version="1.0",
    description="Change in taker buy ratio over 1 hour",
    lookback_minutes=60,
    missing_policy="fill_zero",
)

PRICE_FLOW_DIVERGENCE_1H = FeatureDefinition(
    id="price_flow_divergence_1h",
    version="1.0",
    description="Product of price return 1h and (buy ratio - 0.5) over 1h",
    lookback_minutes=60,
    missing_policy="fill_zero",
)

registry.register_feature(TAKER_BUY_RATIO)
registry.register_feature(TAKER_BUY_RATIO_TREND_1H)
registry.register_feature(TAKER_BUY_RATIO_TREND_4H)
registry.register_feature(TAKER_BUY_RATIO_CHANGE_1H)
registry.register_feature(PRICE_FLOW_DIVERGENCE_1H)


def build_taker_features_sql(source_table: str) -> str:
    """
    Returns a SQL CTE that computes Taker volume features from the source timeline table.
    Assumes `buy_volume`, `sell_volume`, `buy_sell_ratio`, and `close` exist in the source_table.
    """
    return f"""
    taker_base AS (
        SELECT
            *,
            -- Taker buy ratio (safe division)
            buy_volume / NULLIF(buy_volume + sell_volume, 0) AS raw_buy_ratio,
            -- Price return 1h for divergence calculation
            close / NULLIF(lag(close, 12) OVER w_all, 0) - 1 AS price_ret_1h
        FROM {source_table}
        WINDOW w_all AS (ORDER BY feature_time)
    ),
    taker_features AS (
        SELECT
            feature_time,
            
            COALESCE(raw_buy_ratio, 0.5) AS {TAKER_BUY_RATIO.id},
            
            -- Trend 1h (12 periods)
            avg(raw_buy_ratio) OVER w_12 AS {TAKER_BUY_RATIO_TREND_1H.id},
            
            -- Trend 4h (48 periods)
            avg(raw_buy_ratio) OVER w_48 AS {TAKER_BUY_RATIO_TREND_4H.id},
            
            -- Change 1h (lag 12)
            raw_buy_ratio - lag(raw_buy_ratio, 12) OVER w_all AS {TAKER_BUY_RATIO_CHANGE_1H.id},
            
            -- Divergence (price return * buy dominance)
            -- if price goes up (+) but buy_ratio is low (- dominance), divergence is negative
            price_ret_1h * (avg(raw_buy_ratio) OVER w_12 - 0.5) AS {PRICE_FLOW_DIVERGENCE_1H.id}
            
        FROM taker_base
        WINDOW 
            w_all AS (ORDER BY feature_time),
            w_12 AS (ORDER BY feature_time ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
            w_48 AS (ORDER BY feature_time ROWS BETWEEN 47 PRECEDING AND CURRENT ROW)
    )
    """
