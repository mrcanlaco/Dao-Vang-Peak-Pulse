import duckdb


def group_events(
    db: duckdb.DuckDBPyConnection,
    input_table: str,
    output_table: str,
    gap_minutes: int = 60
) -> None:
    query = f"""
    CREATE OR REPLACE TABLE {output_table} AS
    WITH positive_rows AS (
        SELECT 
            symbol,
            signal_time,
            signal_price,
            target_time,
            max_favorable_excursion
        FROM {input_table}
        WHERE label_value = 1
    ),
    lagged AS (
        SELECT 
            *,
            LAG(signal_time) OVER (PARTITION BY symbol ORDER BY signal_time) AS prev_time
        FROM positive_rows
    ),
    new_event_flags AS (
        SELECT 
            *,
            CASE 
                WHEN prev_time IS NULL THEN 1
                WHEN EXTRACT(EPOCH FROM (signal_time - prev_time))/60 >= {gap_minutes} THEN 1
                ELSE 0
            END AS is_new_event
        FROM lagged
    ),
    event_ids AS (
        SELECT 
            *,
            SUM(is_new_event) OVER (PARTITION BY symbol ORDER BY signal_time) AS event_seq
        FROM new_event_flags
    ),
    events_mapped AS (
        SELECT 
            symbol || '_' || CAST(EXTRACT(EPOCH FROM MIN(signal_time)) AS BIGINT) AS event_id,
            symbol,
            event_seq
        FROM event_ids
        GROUP BY symbol, event_seq
    ),
    final_mapping AS (
        SELECT
            e1.symbol,
            e1.signal_time,
            e2.event_id
        FROM event_ids e1
        JOIN events_mapped e2 ON e1.symbol = e2.symbol AND e1.event_seq = e2.event_seq
    )
    SELECT 
        l.*,
        f.event_id
    FROM {input_table} l
    LEFT JOIN final_mapping f
      ON l.symbol = f.symbol 
     AND l.signal_time = f.signal_time;
    """
    db.execute(query)

def create_event_summary_table(
    db: duckdb.DuckDBPyConnection,
    events_table: str,
    summary_table: str
) -> None:
    query = f"""
    CREATE OR REPLACE TABLE {summary_table} AS
    SELECT 
        event_id,
        symbol,
        MIN(signal_time) AS event_start_time,
        MAX(signal_time) AS event_end_time,
        COUNT(*) AS member_rows,
        MIN(target_time) AS first_target_time,
        MIN(max_favorable_excursion) AS peak_favorable_excursion
    FROM {events_table}
    WHERE event_id IS NOT NULL
    GROUP BY event_id, symbol;
    """
    db.execute(query)
