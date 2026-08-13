from dao_vang.data.storage.duckdb import DuckDBQueryLayer


def align_exact_5m(
    db: DuckDBQueryLayer,
    output_view: str,
    kline_view: str = "kline",
    oi_view: str = "open_interest",
    taker_view: str = "taker_volume",
    global_ratio_view: str = "global_ratio",
    top_ratio_view: str = "top_ratio",
    top_position_view: str | None = None,
    max_lag_seconds: int = 5,
):
    """
    Creates a view that aligns 5m period data (OHLCV, OI, Taker Volume, Ratios)
    exactly on their period_end / close_time.

    A record is only joined if its available_time <= close_time + max_lag_seconds
    and its quality_status is 'valid' or 'warning'.
    """

    # DuckDB's DROP ... IF EXISTS checks only the name, not the type,
    # so a VIEW/TABLE type mismatch still raises. Try both explicitly.
    for kind in ("VIEW", "TABLE"):
        try:
            db.conn.execute(f"DROP {kind} {output_view}")
        except Exception:
            pass

    # Align timestamps to 5-minute buckets for joining.
    # kline close_time ends at xx:xx:59.999 (end of candle),
    # while OI/taker/ratio period_end is at xx:xx:00 (start of period).
    # We truncate both to 5-minute boundaries to match them.
    # E.g., kline 07:04:59.999 → 07:00:00, OI 07:00:00 → 07:00:00
    if top_position_view:
        top_position_select = (
            "tpr.long_short_ratio AS top_long_short_position_ratio,"
        )
        top_position_join = f"""
    LEFT JOIN {top_position_view} tpr
        ON k.symbol = tpr.symbol
        AND time_bucket(INTERVAL '5 minutes', k.close_time) = time_bucket(INTERVAL '5 minutes', tpr.period_end)
        AND tpr.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND tpr.quality_status IN ('valid', 'warning')
"""
    else:
        top_position_select = "CAST(NULL AS DECIMAL(20,8)) AS top_long_short_position_ratio,"
        top_position_join = ""

    sql = f"""
    CREATE OR REPLACE VIEW {output_view} AS
    SELECT
        k.symbol,
        k.close_time AS feature_time,
        k.close_time + INTERVAL {max_lag_seconds} SECONDS AS decision_time,
        k.available_time AS feature_available_time,
        k.open, k.high, k.low, k.close, k.volume_base, k.volume_quote, k.trade_count,
        oi.open_interest_contracts, oi.open_interest_value,
        tv.buy_volume, tv.sell_volume, tv.buy_sell_ratio,
        gr.long_account AS global_long_account, gr.short_account AS global_short_account, gr.long_short_ratio AS global_long_short_ratio,
        tr.long_account AS top_long_account, tr.short_account AS top_short_account, tr.long_short_ratio AS top_long_short_ratio,
        {top_position_select}
        k.quality_status
    FROM {kline_view} k
    LEFT JOIN {oi_view} oi
        ON k.symbol = oi.symbol
        AND time_bucket(INTERVAL '5 minutes', k.close_time) = time_bucket(INTERVAL '5 minutes', oi.period_end)
        AND oi.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND oi.quality_status IN ('valid', 'warning')
    LEFT JOIN {taker_view} tv
        ON k.symbol = tv.symbol
        AND time_bucket(INTERVAL '5 minutes', k.close_time) = time_bucket(INTERVAL '5 minutes', tv.period_end)
        AND tv.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND tv.quality_status IN ('valid', 'warning')
    LEFT JOIN {global_ratio_view} gr
        ON k.symbol = gr.symbol
        AND time_bucket(INTERVAL '5 minutes', k.close_time) = time_bucket(INTERVAL '5 minutes', gr.period_end)
        AND gr.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND gr.quality_status IN ('valid', 'warning')
    LEFT JOIN {top_ratio_view} tr
        ON k.symbol = tr.symbol
        AND time_bucket(INTERVAL '5 minutes', k.close_time) = time_bucket(INTERVAL '5 minutes', tr.period_end)
        AND tr.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
        AND tr.quality_status IN ('valid', 'warning')
    {top_position_join}
    WHERE k.available_time <= (k.close_time + INTERVAL {max_lag_seconds} SECONDS)
      -- Binance's kline endpoint also returns the currently open candle. Its
      -- close_time is in the future until the 5m interval has closed. Never
      -- expose that candle to features/scoring: doing so makes the live
      -- freshness gate reject every candidate as feature_time_in_future.
      AND k.close_time <= CURRENT_TIMESTAMP
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

    for kind in ("VIEW", "TABLE"):
        try:
            db.conn.execute(f"DROP {kind} {output_view}")
        except Exception:
            pass

    sql = f"""
    CREATE OR REPLACE TABLE {output_view} AS
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
