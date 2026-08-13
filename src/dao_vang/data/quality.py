import re
from decimal import Decimal
from typing import Any

from dao_vang.data.schemas import (
    NormalizedBase,
    NormalizedFunding,
    NormalizedGlobalRatio,
    NormalizedKline,
    NormalizedOpenInterest,
    NormalizedTakerVolume,
    NormalizedTopPositionRatio,
    NormalizedTopRatio,
    QualityStatus,
)


def _apply_flag(obj: NormalizedBase, status: QualityStatus, flag: str):
    # Upgrades severity if necessary
    severity = {
        QualityStatus.VALID: 0,
        QualityStatus.QUARANTINED: 1,
        QualityStatus.WARNING: 2,
        QualityStatus.INVALID: 3,
    }
    if severity[status] > severity[obj.quality_status]:
        obj.quality_status = status
    if flag not in obj.quality_flags:
        obj.quality_flags.append(flag)


def assess_kline(kline: NormalizedKline) -> NormalizedKline:
    if kline.volume_base < Decimal("0") or kline.volume_quote < Decimal("0"):
        _apply_flag(kline, QualityStatus.INVALID, "negative_volume")

    if kline.high < kline.open or kline.high < kline.close or kline.high < kline.low:
        _apply_flag(kline, QualityStatus.INVALID, "invalid_high_price")

    if kline.low > kline.open or kline.low > kline.close or kline.low > kline.high:
        _apply_flag(kline, QualityStatus.INVALID, "invalid_low_price")

    if kline.trade_count < 0:
        _apply_flag(kline, QualityStatus.INVALID, "negative_trade_count")

    return kline


def assess_funding(funding: NormalizedFunding) -> NormalizedFunding:
    if abs(funding.funding_rate) > Decimal("0.1"):
        _apply_flag(funding, QualityStatus.WARNING, "extreme_funding_rate")

    if funding.mark_price is not None and funding.mark_price <= Decimal("0"):
        _apply_flag(funding, QualityStatus.INVALID, "invalid_mark_price")

    return funding


def assess_open_interest(oi: NormalizedOpenInterest) -> NormalizedOpenInterest:
    if oi.open_interest_contracts < Decimal("0"):
        _apply_flag(oi, QualityStatus.INVALID, "negative_open_interest")

    if oi.open_interest_value is not None and oi.open_interest_value < Decimal("0"):
        _apply_flag(oi, QualityStatus.INVALID, "negative_open_interest_value")

    return oi


def assess_taker_volume(tv: NormalizedTakerVolume) -> NormalizedTakerVolume:
    if tv.buy_volume < Decimal("0") or tv.sell_volume < Decimal("0"):
        _apply_flag(tv, QualityStatus.INVALID, "negative_taker_volume")

    if tv.buy_sell_ratio is not None and tv.buy_sell_ratio <= Decimal("0"):
        _apply_flag(tv, QualityStatus.INVALID, "invalid_buy_sell_ratio")

    return tv


def assess_global_ratio(gr: NormalizedGlobalRatio) -> NormalizedGlobalRatio:
    if gr.long_account is not None and gr.long_account < Decimal("0"):
        _apply_flag(gr, QualityStatus.INVALID, "negative_long_account")

    if gr.short_account is not None and gr.short_account < Decimal("0"):
        _apply_flag(gr, QualityStatus.INVALID, "negative_short_account")

    if gr.long_short_ratio <= Decimal("0"):
        _apply_flag(gr, QualityStatus.INVALID, "invalid_long_short_ratio")

    return gr


def assess_top_ratio(tr: NormalizedTopRatio) -> NormalizedTopRatio:
    if tr.long_account is not None and tr.long_account < Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "negative_long_account")

    if tr.short_account is not None and tr.short_account < Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "negative_short_account")

    if tr.long_short_ratio <= Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "invalid_long_short_ratio")

    return tr


def assess_top_position_ratio(
    tr: NormalizedTopPositionRatio,
) -> NormalizedTopPositionRatio:
    """Validate top-trader position ratios using the same contract as accounts."""
    if tr.long_position is not None and tr.long_position < Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "negative_long_position")
    if tr.short_position is not None and tr.short_position < Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "negative_short_position")
    if tr.long_short_ratio <= Decimal("0"):
        _apply_flag(tr, QualityStatus.INVALID, "invalid_long_short_ratio")
    return tr


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _safe_identifier(value: str) -> str:
    if not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Unsafe DuckDB identifier: {value!r}")
    return value


def _get_connection(db: Any) -> Any:
    """Accept either DuckDBQueryLayer or a raw DuckDB connection."""
    return getattr(db, "conn", db)


def _table_columns(conn: Any, table_name: str) -> set[str]:
    table_name = _safe_identifier(table_name)
    try:
        rows = conn.execute(f"DESCRIBE {table_name}").fetchall()
    except Exception:
        rows = conn.execute(f"PRAGMA table_info('{table_name}')").fetchall()
    return {str(row[0]) for row in rows}


def compute_data_quality(
    db: Any,
    input_view: str = "raw_timeline_pre_quality",
    output_table: str = "raw_timeline",
    max_feature_age_minutes: float = 10.0,
) -> None:
    """Materialize deterministic row-level quality metadata for a timeline.

    This is intentionally a SQL transform rather than a Python ``fillna(0)``
    operation.  The output preserves all source columns and adds:

    ``data_quality_score``
        A bounded score in ``[0, 1]``; missing optional inputs reduce the score.
    ``quality_status``
        ``invalid`` for invalid source rows or missing OHLC, ``warning`` for
        partial/missing derivatives, otherwise ``valid``.
    ``quality_reason_codes``
        A stable pipe-delimited list suitable for audit logs.
    ``max_feature_age_minutes``
        Age of the latest available feature relative to ``decision_time``.

    Historical replays are deterministic: age is calculated from timestamps in
    the snapshot, never from wall-clock ``now()``.
    """
    conn = _get_connection(db)
    source = _safe_identifier(input_view)
    target = _safe_identifier(output_table)
    cols = _table_columns(conn, source)

    # A timeline always has these fields in production, but use conservative
    # fallbacks so small test/replay tables can still be quality-scored.
    quality_expr = (
        "LOWER(CAST(quality_status AS VARCHAR))"
        if "quality_status" in cols
        else "'valid'"
    )
    replace_columns = {
        name
        for name in (
            "quality_status",
            "data_quality_score",
            "max_feature_age_minutes",
            "quality_reason_codes",
        )
        if name in cols
    }
    source_star = (
        "* EXCLUDE (" + ", ".join(sorted(replace_columns)) + ")"
        if replace_columns
        else "*"
    )
    feature_time_expr = (
        "feature_time" if "feature_time" in cols else "NULL::TIMESTAMP"
    )
    decision_time_expr = (
        "decision_time" if "decision_time" in cols else feature_time_expr
    )
    available_expr = (
        "feature_available_time" if "feature_available_time" in cols else "NULL::TIMESTAMP"
    )

    # Missing derivatives are warnings, not hidden risk evidence.  OHLC and
    # symbol/time are required for a usable prediction row.
    optional_cols = [
        "open_interest_contracts",
        "buy_volume",
        "sell_volume",
        "global_long_short_ratio",
        "top_long_short_ratio",
        "top_long_short_position_ratio",
        "funding_rate_last_known",
    ]
    missing_terms = [
        f"CASE WHEN {col} IS NULL THEN 1 ELSE 0 END"
        for col in optional_cols
        if col in cols
    ]
    missing_count_expr = " + ".join(missing_terms) if missing_terms else "0"
    required_missing = " OR ".join(
        f"{col} IS NULL" for col in ("symbol", "feature_time", "close") if col in cols
    ) or "FALSE"
    age_expr = (
        f"date_diff('second', {available_expr}, {decision_time_expr}) / 60.0"
        if "feature_available_time" in cols
        else "0.0"
    )
    age_bad = (
        f"({available_expr} IS NOT NULL AND ({age_expr} > {float(max_feature_age_minutes)} OR {age_expr} < 0.0))"
        if "feature_available_time" in cols
        else "FALSE"
    )
    future_bad = (
        f"({available_expr} IS NOT NULL AND {age_expr} < 0.0)"
        if "feature_available_time" in cols
        else "FALSE"
    )

    # DuckDB supports EXCLUDE, which avoids duplicate quality_status while
    # preserving source columns and keeping this transform idempotent.
    # DuckDB raises when DROP TABLE targets an existing view (and vice versa),
    # so make replacement idempotent across replay runs.
    for statement in (f"DROP TABLE IF EXISTS {target}", f"DROP VIEW IF EXISTS {target}"):
        try:
            conn.execute(statement)
        except Exception:
            pass
    conn.execute(
        f"""
        CREATE TABLE {target} AS
        WITH scored AS (
            SELECT
                {source_star},
                {quality_expr} AS _source_quality_status,
                ({missing_count_expr}) AS _missing_count,
                {age_expr} AS _feature_age_minutes,
                {required_missing} AS _required_missing,
                {age_bad} AS _age_bad
                ,{future_bad} AS _future_bad
            FROM {source}
        )
        SELECT
            * EXCLUDE (
                _source_quality_status,
                _missing_count,
                _feature_age_minutes,
                _required_missing,
                _age_bad,
                _future_bad
            ),
            CAST(
                GREATEST(
                    0.0,
                    LEAST(1.0, 1.0 - 0.15 * _missing_count - CASE WHEN _age_bad THEN 0.25 ELSE 0.0 END)
                ) AS DOUBLE
            ) AS data_quality_score,
            CAST(_feature_age_minutes AS DOUBLE) AS max_feature_age_minutes,
            CASE
                WHEN _source_quality_status IN ('invalid', 'quarantined') OR _required_missing OR _age_bad
                    THEN 'invalid'
                WHEN _source_quality_status = 'warning' OR _missing_count > 0
                    THEN 'warning'
                ELSE 'valid'
            END AS quality_status,
            TRIM(BOTH '|' FROM CONCAT(
                CASE WHEN _source_quality_status IN ('invalid', 'quarantined') THEN 'source_invalid|' ELSE '' END,
                CASE WHEN _required_missing THEN 'required_missing|' ELSE '' END,
                CASE WHEN _missing_count > 0 THEN 'optional_missing|' ELSE '' END,
                CASE WHEN _future_bad THEN 'feature_future|' ELSE '' END,
                CASE WHEN _age_bad THEN 'stale_feature|' ELSE '' END
            )) AS quality_reason_codes
        FROM scored
        """
    )
