from dao_vang.data.storage.duckdb import DuckDBQueryLayer


def align_exact_5m(
    db: DuckDBQueryLayer,
    output_view: str,
    kline_view: str = "kline",
    oi_view: str = "open_interest",
    taker_view: str = "taker_volume",
    global_ratio_view: str = "global_ratio",
    top_ratio_view: str = "top_ratio",
    max_lag_seconds: int = 5,
):
    """
    Creates a view that aligns 5m period data (OHLCV, OI, Taker Volume, Ratios)
    exactly on their period_end / close_time.

    A record is only joined if its available_time <= close_time + max_lag_seconds
    and its quality_status is 'valid' or 'warning'.
    """

    sql = f"""
    CREATE OR REPLACE VIEW {output_view} AS
    SELECT
        k.symbol,
        k.close_time AS feature_time,
        k.close_time + INTERVAL {max_lag_seconds} SECONDS AS decision_time,
        k.open, k.high, k.low, k.close, k.volume_base, k.volume_quote, k.trade_count,
        oi.open_interest_contracts, oi.open_interest_value,
        tv.buy_volume, tv.sell_volume, tv.buy_sell_ratio,
        gr.long_account AS global_long_account, gr.short_account AS global_short_account, gr.long_short_ratio AS global_long_short_ratio,
        tr.long_account AS top_long_account, tr.short_account AS top_short_account, tr.long_short_ratio AS top_long_short_ratio
    FROM {kline_view} k
    LEFT JOIN {oi_view} oi 
        ON k.symbol = oi.symbol AND k.close_time = oi.period_end 
        AND oi.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND oi.quality_status IN ('valid', 'warning')
    LEFT JOIN {taker_view} tv 
        ON k.symbol = tv.symbol AND k.close_time = tv.period_end 
        AND tv.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND tv.quality_status IN ('valid', 'warning')
    LEFT JOIN {global_ratio_view} gr 
        ON k.symbol = gr.symbol AND k.close_time = gr.period_end 
        AND gr.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND gr.quality_status IN ('valid', 'warning')
    LEFT JOIN {top_ratio_view} tr 
        ON k.symbol = tr.symbol AND k.close_time = tr.period_end 
        AND tr.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND tr.quality_status IN ('valid', 'warning')
    WHERE k.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
      AND k.quality_status IN ('valid', 'warning')
    """

    db.conn.execute(sql)


def align_funding_asof(
    db: DuckDBQueryLayer,
    output_view: str,
    aligned_view: str = "aligned_5m",
    funding_view: str = "funding",
    max_funding_age_hours: int = 12,
):
    """
    Creates a view that adds funding rate data to the exactly-aligned 5m timeline,
    using a backward AS-OF join on available_time <= decision_time.

    If the most recent funding rate is older than max_funding_age_hours, it is set to NULL.
    """
    max_age_minutes = max_funding_age_hours * 60

    sql = f"""
    CREATE OR REPLACE VIEW {output_view} AS
    WITH joined AS (
        SELECT
            a.*,
            f.funding_rate,
            f.event_time AS funding_event_time,
            date_diff('minute', f.event_time, a.feature_time) AS funding_age_minutes
        FROM {aligned_view} a
        ASOF LEFT JOIN {funding_view} f
            ON a.symbol = f.symbol
            AND a.decision_time >= f.available_time
    )
    SELECT
        * EXCLUDE (funding_rate, funding_event_time, funding_age_minutes),
        CASE 
            WHEN funding_age_minutes <= {max_age_minutes} THEN funding_rate 
            ELSE NULL 
        END AS funding_rate_last_known,
        CASE 
            WHEN funding_age_minutes <= {max_age_minutes} THEN funding_event_time 
            ELSE NULL 
        END AS funding_event_time,
        CASE 
            WHEN funding_age_minutes <= {max_age_minutes} THEN funding_age_minutes 
            ELSE NULL 
        END AS funding_age_minutes
    FROM joined
    """

    db.conn.execute(sql)
