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
BTC_RET_4H = FeatureDefinition(
    id="btc_ret_4h",
    version="1.0",
    description="BTC 4-hour price return — nhiệt kế thị trường ngắn hạn",
    lookback_minutes=240,
    missing_policy="fill_zero",
)

BTC_RET_24H = FeatureDefinition(
    id="btc_ret_24h",
    version="1.0",
    description="BTC 24-hour price return — xu hướng thị trường tổng thể",
    lookback_minutes=1440,
    missing_policy="fill_zero",
)

BTC_VOLATILITY_24H = FeatureDefinition(
    id="btc_volatility_24h",
    version="1.0",
    description="BTC 24-hour rolling volatility — mức độ bất ổn thị trường",
    lookback_minutes=1440,
    missing_policy="fill_mean",
)

BTC_DOMINANCE_SLOPE_24H = FeatureDefinition(
    id="btc_dominance_slope_24h",
    version="1.0",
    description=(
        "Slope của BTC return so với median altcoin return trong 24h. "
        "Dương = BTC mạnh hơn altcoin (tiền chảy về BTC, bất lợi cho altcoin short). "
        "Âm = altcoin mạnh hơn BTC (rủi ro pump riêng lẻ)."
    ),
    lookback_minutes=1440,
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

registry.register_feature(BTC_RET_4H)
registry.register_feature(BTC_RET_24H)
registry.register_feature(BTC_VOLATILITY_24H)
registry.register_feature(BTC_DOMINANCE_SLOPE_24H)
def build_price_features_sql(source_table: str) -> str:
    """
    The source_table must contain: feature_time, symbol, close, high, volume_base.
    Assuming 5-minute intervals.

    BTC context features (btc_ret_4h, btc_ret_24h, btc_volatility_24h,
    btc_dominance_slope_24h) are computed from the BTCUSDT rows inside the same
    source_table and then joined back to every altcoin row by feature_time.
    This is a pure point-in-time operation — the BTCUSDT row at time T is
    available to every altcoin row at the same T, which is valid because BTCUSDT
    is collected in the same pipeline cycle.
    """
    return f"""
    price_base AS (
        SELECT
            *,
            close / lag(close, 1)   OVER w_all - 1 AS {PRICE_RET_5M.id},
            close / lag(close, 12)  OVER w_all - 1 AS {PRICE_RET_1H.id},
            close / lag(close, 3)   OVER w_all - 1 AS {PRICE_RET_15M.id},
            close / lag(close, 48)  OVER w_all - 1 AS {PRICE_RET_4H.id},
            close / lag(close, 288) OVER w_all - 1 AS {PRICE_RET_24H.id},
            max(high) OVER w_12_prev AS prev_max_high_12,
            max(high) OVER w_48     AS high_4h,
            sum(volume_base) OVER w_12 AS quote_volume_1h
        FROM {source_table}
        WINDOW
            w_all     AS (PARTITION BY symbol ORDER BY feature_time),
            w_12_prev AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING),
            w_48      AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 47 PRECEDING AND CURRENT ROW),
            w_12      AS (PARTITION BY symbol ORDER BY feature_time ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
    ),
    -- Bối cảnh BTC: tính riêng trên symbol = 'BTCUSDT' rồi JOIN vào mọi altcoin
    -- theo feature_time (point-in-time, không lookahead).
    btc_raw AS (
        SELECT
            feature_time,
            close / lag(close, 48)  OVER (ORDER BY feature_time) - 1 AS btc_raw_ret_4h,
            close / lag(close, 288) OVER (ORDER BY feature_time) - 1 AS btc_raw_ret_24h,
            close / lag(close, 1)   OVER (ORDER BY feature_time) - 1 AS btc_raw_ret_5m
        FROM {source_table}
        WHERE symbol = 'BTCUSDT'
    ),
    btc_context AS (
        SELECT
            feature_time,
            COALESCE(btc_raw_ret_4h,  0.0) AS {BTC_RET_4H.id},
            COALESCE(btc_raw_ret_24h, 0.0) AS {BTC_RET_24H.id},
            -- Biến động 24h của BTC (độ lệch chuẩn return 5m trong 288 bar)
            stddev_samp(btc_raw_ret_5m) OVER (
                ORDER BY feature_time
                ROWS BETWEEN 287 PRECEDING AND CURRENT ROW
            ) AS {BTC_VOLATILITY_24H.id}
        FROM btc_raw
    ),
    -- Slope BTC so với median altcoin: trung vị return_24h của các altcoin tại cùng thời điểm
    -- Tránh window function sinh Cartesian, gom nhóm trực tiếp:
    altcoin_median AS (
        SELECT
            feature_time,
            median({PRICE_RET_24H.id}) AS median_altcoin_ret_24h
        FROM price_base
        WHERE symbol <> 'BTCUSDT'
        GROUP BY feature_time
    ),
    price_features AS (
        SELECT
            p.feature_time,
            p.symbol,
            {PRICE_RET_5M.id},
            {PRICE_RET_1H.id},
            {PRICE_RET_15M.id},
            {PRICE_RET_4H.id},
            {PRICE_RET_24H.id},

            stddev_samp({PRICE_RET_5M.id}) OVER w_288 AS {PRICE_VOLATILITY_24H.id},

            p.close / max(p.high) OVER w_288 - 1 AS {DISTANCE_FROM_HIGH_24H.id},

            -- Khối lượng tương đối so với 24h
            volume_base / NULLIF(max(volume_base) OVER w_288, 0) AS {VOLUME_PERCENTILE_24H.id},

            (volume_base - avg(volume_base) OVER w_288)
                / NULLIF(stddev_samp(volume_base) OVER w_288, 0)
                AS {VOLUME_ZSCORE_24H.id},
            sum(volume_base) OVER w_12
                / NULLIF(sum(volume_base) OVER w_prev_12, 0)
                AS {VOLUME_RATIO_1H.id},

            -- Tốc độ thoái trào của đà tăng
            {PRICE_RET_1H.id} - lag({PRICE_RET_1H.id}, 36) OVER w_all AS {MOMENTUM_DECELERATION_4H.id},
            {PRICE_RET_15M.id} - lag({PRICE_RET_15M.id}, 3) OVER w_all AS {MOMENTUM_DECEL_15M.id},
            CASE WHEN high_4h < lag(high_4h, 48) OVER w_all THEN 1.0 ELSE 0.0 END AS {LOWER_HIGH_4H.id},
            quote_volume_1h / NULLIF(avg(quote_volume_1h) OVER w_144_prev, 0) AS {VOLUME_DRY_UP_1H.id},

            -- Phá vỡ giả (bull trap)
            CASE
                WHEN prev_max_high_12 IS NOT NULL
                    AND p.high > prev_max_high_12
                    AND p.close < prev_max_high_12
                THEN LEAST(
                    1.0,
                    (prev_max_high_12 - p.close) / NULLIF(prev_max_high_12, 0) / 0.02
                )
                ELSE 0.0
            END AS {FAKE_BREAKOUT_1H.id},

            -- Bối cảnh BTC (nhiệt kế thị trường)
            COALESCE(b.{BTC_RET_4H.id},        0.0) AS {BTC_RET_4H.id},
            COALESCE(b.{BTC_RET_24H.id},       0.0) AS {BTC_RET_24H.id},
            COALESCE(b.{BTC_VOLATILITY_24H.id}, avg(b.{BTC_VOLATILITY_24H.id}) OVER ()) AS {BTC_VOLATILITY_24H.id},

            -- Slope BTC vs altcoin: BTC mạnh hơn median altcoin = bất lợi cho short altcoin
            COALESCE(b.{BTC_RET_24H.id}, 0.0)
                - COALESCE(a.median_altcoin_ret_24h, 0.0)
                AS {BTC_DOMINANCE_SLOPE_24H.id}

        FROM price_base p
        LEFT JOIN btc_context  b ON p.feature_time = b.feature_time
        LEFT JOIN altcoin_median a ON p.feature_time = a.feature_time AND p.symbol <> 'BTCUSDT'
        WINDOW
            w_all      AS (PARTITION BY p.symbol ORDER BY p.feature_time),
            w_288      AS (PARTITION BY p.symbol ORDER BY p.feature_time ROWS BETWEEN 287 PRECEDING AND CURRENT ROW),
            w_12       AS (PARTITION BY p.symbol ORDER BY p.feature_time ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
            w_prev_12  AS (PARTITION BY p.symbol ORDER BY p.feature_time ROWS BETWEEN 23 PRECEDING AND 12 PRECEDING),
            w_144_prev AS (PARTITION BY p.symbol ORDER BY p.feature_time ROWS BETWEEN 144 PRECEDING AND 1 PRECEDING)
    )
    """
