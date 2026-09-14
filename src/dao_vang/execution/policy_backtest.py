"""Out-of-sample comparison of frozen scale-in policies on scanner signals."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean, median
from typing import Any

import duckdb

from dao_vang.config.settings import AppSettings, ExecutionPolicyRouterConfig
from dao_vang.execution.policy_evaluator import PriceBar, evaluate_price_path
from dao_vang.execution.policy_router import (
    ExecutionPolicyRouter,
    PolicyContext,
    score_policy_context,
)

BACKTEST_VERSION = "execution_policy_backtest_v1"


@dataclass(frozen=True, slots=True)
class PolicyBacktestConfig:
    db_path: Path
    output_json: Path
    output_csv: Path
    model_id: str | None = None
    probability_threshold: float = 0.41
    reset_gap_minutes: int = 30
    fee_bps_per_side: float = 5.0
    slippage_bps_per_side: float = 5.0
    target_drawdown: float = 0.20
    fold_days: int = 7


def _event_query(config: PolicyBacktestConfig) -> tuple[str, list[Any]]:
    model_filter = ""
    params: list[Any] = [
        config.probability_threshold,
        config.probability_threshold,
    ]
    if config.model_id:
        model_filter = "WHERE model_id = ?"
        params.append(config.model_id)
    params.append(config.reset_gap_minutes)
    query = f"""
    WITH ordered AS (
        SELECT
            p.*,
            CAST(p.signal_time AS TIMESTAMP) AS signal_ts,
            CASE
                WHEN p.calibrated_probability >= ?
                 AND p.quality_status = 'valid'
                THEN TRUE ELSE FALSE
            END AS qualified,
            LAG(
                CASE
                    WHEN p.calibrated_probability >= ?
                     AND p.quality_status = 'valid'
                    THEN TRUE ELSE FALSE
                END
            ) OVER (
                PARTITION BY p.symbol
                ORDER BY p.signal_time, p.prediction_id
            ) AS previous_qualified,
            LAG(CAST(p.signal_time AS TIMESTAMP)) OVER (
                PARTITION BY p.symbol
                ORDER BY p.signal_time, p.prediction_id
            ) AS previous_signal_ts
        FROM predictions p
        {model_filter}
    ),
    events AS (
        SELECT *
        FROM ordered
        WHERE qualified
          AND (
              COALESCE(previous_qualified, FALSE) = FALSE
              OR DATE_DIFF(
                  'minute',
                  previous_signal_ts,
                  signal_ts
              ) > ?
          )
    ),
    last_bar AS (
        SELECT MAX(CAST(close_time AS TIMESTAMP)) AS max_time
        FROM kline
        WHERE interval = '5m'
    )
    SELECT
        e.prediction_id,
        e.symbol,
        e.signal_ts AS signal_time,
        e.model_id,
        e.label_version,
        e.calibrated_probability,
        e.heuristic_score,
        e.data_quality_score,
        k.close AS signal_price,
        f.price_ret_1h,
        f.price_ret_24h,
        f.price_volatility_24h,
        f.funding_rate_raw,
        f.funding_zscore_30d,
        f.oi_change_1h,
        f.oi_change_24h,
        f.taker_buy_ratio,
        f.top_ls_ratio,
        f.volume_percentile_24h
    FROM events e
    CROSS JOIN last_bar lb
    INNER JOIN kline k
        ON k.symbol = e.symbol
       AND k.interval = '5m'
       AND CAST(k.close_time AS TIMESTAMP) = e.signal_ts
    LEFT JOIN feature_results f
        ON f.symbol = e.symbol
       AND CAST(f.feature_time AS TIMESTAMP) = e.signal_ts
    WHERE e.signal_ts <= lb.max_time - INTERVAL 24 HOURS
    ORDER BY e.signal_ts, e.symbol
    """
    return query, params


def _values_relation(events: list[dict[str, Any]]) -> tuple[str, list[Any]]:
    placeholders = ", ".join("(?, ?, ?)" for _ in events)
    params: list[Any] = []
    for event in events:
        params.extend(
            (
                event["prediction_id"],
                event["symbol"],
                event["signal_time"],
            )
        )
    return (
        f"(VALUES {placeholders}) AS e(prediction_id, symbol, signal_time)",
        params,
    )


def _load_events(
    connection: duckdb.DuckDBPyConnection,
    config: PolicyBacktestConfig,
) -> list[dict[str, Any]]:
    query, params = _event_query(config)
    cursor = connection.execute(query, params)
    columns = [item[0] for item in cursor.description]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _load_paths(
    connection: duckdb.DuckDBPyConnection,
    events: list[dict[str, Any]],
) -> dict[str, list[PriceBar]]:
    relation, params = _values_relation(events)
    rows = connection.execute(
        f"""
        SELECT
            e.prediction_id,
            CAST(k.close_time AS TIMESTAMP),
            CAST(k.high AS DOUBLE),
            CAST(k.low AS DOUBLE),
            CAST(k.close AS DOUBLE)
        FROM {relation}
        INNER JOIN kline k
            ON k.symbol = e.symbol
           AND k.interval = '5m'
           AND CAST(k.close_time AS TIMESTAMP)
               BETWEEN e.signal_time
                   AND e.signal_time + INTERVAL 24 HOURS
        ORDER BY e.prediction_id, k.close_time
        """,
        params,
    ).fetchall()
    result: dict[str, list[PriceBar]] = defaultdict(list)
    for prediction_id, timestamp, high, low, close in rows:
        result[str(prediction_id)].append(
            PriceBar(timestamp, float(high), float(low), float(close))
        )
    return dict(result)


def _load_volume_24h(
    connection: duckdb.DuckDBPyConnection,
    events: list[dict[str, Any]],
) -> dict[str, float]:
    relation, params = _values_relation(events)
    rows = connection.execute(
        f"""
        SELECT
            e.prediction_id,
            COALESCE(SUM(CAST(k.volume_quote AS DOUBLE)), 0.0)
        FROM {relation}
        LEFT JOIN kline k
            ON k.symbol = e.symbol
           AND k.interval = '5m'
           AND CAST(k.close_time AS TIMESTAMP) > e.signal_time - INTERVAL 24 HOURS
           AND CAST(k.close_time AS TIMESTAMP) <= e.signal_time
        GROUP BY e.prediction_id
        """,
        params,
    ).fetchall()
    return {str(prediction_id): float(volume or 0.0) for prediction_id, volume in rows}


def _load_funding(
    connection: duckdb.DuckDBPyConnection,
    events: list[dict[str, Any]],
) -> dict[str, list[tuple[datetime, float]]]:
    relation, params = _values_relation(events)
    rows = connection.execute(
        f"""
        SELECT DISTINCT
            e.prediction_id,
            CAST(f.funding_time AS TIMESTAMP),
            CAST(f.funding_rate AS DOUBLE)
        FROM {relation}
        INNER JOIN funding f
            ON f.symbol = e.symbol
           AND CAST(f.funding_time AS TIMESTAMP) > e.signal_time
           AND CAST(f.funding_time AS TIMESTAMP)
               <= e.signal_time + INTERVAL 24 HOURS
        ORDER BY e.prediction_id, f.funding_time
        """,
        params,
    ).fetchall()
    result: dict[str, list[tuple[datetime, float]]] = defaultdict(list)
    for prediction_id, timestamp, rate in rows:
        result[str(prediction_id)].append((timestamp, float(rate)))
    return dict(result)


def _features(event: dict[str, Any]) -> dict[str, Any]:
    names = (
        "price_ret_1h",
        "price_ret_24h",
        "price_volatility_24h",
        "funding_rate_raw",
        "funding_zscore_30d",
        "oi_change_1h",
        "oi_change_24h",
        "taker_buy_ratio",
        "top_ls_ratio",
        "volume_percentile_24h",
    )
    return {name: event.get(name) for name in names}


def _liquidity_tier(volume: float) -> str:
    if volume < 5_000_000:
        return "thin_lt_5m"
    if volume < 25_000_000:
        return "low_5m_25m"
    if volume < 100_000_000:
        return "medium_25m_100m"
    return "high_gte_100m"


def _volatility_tier(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score < 60.0:
        return "compact"
    if score < 90.0:
        return "balanced"
    if score < 97.0:
        return "deep"
    return "safety_ceiling"


def _funding_return(
    points: list[tuple[datetime, float]],
    filled_legs: Any,
    exit_time: datetime,
) -> float:
    total = 0.0
    for timestamp, rate in points:
        if timestamp > exit_time:
            break
        active_allocation = sum(
            leg.allocation for leg in filled_legs if leg.timestamp < timestamp
        )
        total += rate * active_allocation
    return total


def _max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    for value in returns:
        equity *= max(0.0, 1.0 + value)
        peak = max(peak, equity)
        if peak > 0:
            drawdown = max(drawdown, (peak - equity) / peak)
    return drawdown


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"signals": 0}
    returns = [float(row["net_return_planned"]) for row in rows]
    maes = [
        float(row["mae"])
        for row in rows
        if row.get("mae") is not None
    ]
    sorted_mae = sorted(maes)

    def percentile(values: list[float], quantile: float) -> float | None:
        if not values:
            return None
        index = min(len(values) - 1, math.ceil(quantile * len(values)) - 1)
        return values[max(0, index)]

    return {
        "signals": len(rows),
        "target_rate": round(
            sum(row["status"] == "target" for row in rows) / len(rows),
            4,
        ),
        "stop_rate": round(
            sum(row["status"] in {"stop", "stop_ambiguous"} for row in rows)
            / len(rows),
            4,
        ),
        "ambiguous_rate": round(
            sum(row["status"] == "stop_ambiguous" for row in rows) / len(rows),
            4,
        ),
        "timeout_rate": round(
            sum(row["status"] == "timeout" for row in rows) / len(rows),
            4,
        ),
        "entry2_fill_rate": round(
            sum(row["filled_legs"] >= 2 for row in rows) / len(rows),
            4,
        ),
        "entry3_fill_rate": round(
            sum(row["filled_legs"] >= 3 for row in rows) / len(rows),
            4,
        ),
        "average_filled_allocation": round(
            mean(float(row["filled_allocation"]) for row in rows),
            4,
        ),
        "expected_gross_return_planned": round(
            mean(float(row["gross_return_planned"]) for row in rows),
            6,
        ),
        "expected_net_return_planned": round(mean(returns), 6),
        "median_net_return_planned": round(median(returns), 6),
        "funding_return_mean": round(
            mean(float(row["funding_return_planned"]) for row in rows),
            7,
        ),
        "mae_p50": None if not maes else round(median(maes), 6),
        "mae_p90": (
            None if not maes else round(float(percentile(sorted_mae, 0.90)), 6)
        ),
        "mae_p95": (
            None if not maes else round(float(percentile(sorted_mae, 0.95)), 6)
        ),
        "sequential_compounded_max_drawdown": round(
            _max_drawdown(returns),
            6,
        ),
    }


def _grouped_summary(
    rows: list[dict[str, Any]],
    field: str,
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row[field])].append(row)
    return {name: _summary(items) for name, items in sorted(grouped.items())}


def run_policy_backtest(
    config: PolicyBacktestConfig,
    *,
    policy_config: ExecutionPolicyRouterConfig | None = None,
) -> dict[str, Any]:
    policy_config = policy_config or ExecutionPolicyRouterConfig()
    connection = duckdb.connect(str(config.db_path), read_only=True)
    connection.execute("PRAGMA disable_progress_bar")
    try:
        events = _load_events(connection, config)
        if not events:
            raise ValueError("no eligible out-of-sample signal episodes found")
        paths = _load_paths(connection, events)
        volumes = _load_volume_24h(connection, events)
        funding = _load_funding(connection, events)
    finally:
        connection.close()

    start_time = min(event["signal_time"] for event in events)
    round_trip_cost = 2.0 * (
        config.fee_bps_per_side + config.slippage_bps_per_side
    ) / 10_000.0
    router = ExecutionPolicyRouter(policy_config)
    templates = {item.policy_id: item for item in policy_config.templates}
    output_rows: list[dict[str, Any]] = []
    router_rows: list[dict[str, Any]] = []

    for event in events:
        prediction_id = str(event["prediction_id"])
        signal_time = event["signal_time"]
        event_features = _features(event)
        volume_24h = volumes.get(prediction_id, 0.0)
        context = PolicyContext(
            signal_probability=event.get("calibrated_probability"),
            label_version=event.get("label_version"),
            signal_score=event.get("heuristic_score"),
            quality_score=event.get("data_quality_score"),
            volume_24h_usd=volume_24h,
            features=event_features,
        )
        scores = score_policy_context(context)
        decision = router.route(context)
        fold = 1 + (signal_time.date() - start_time.date()).days // config.fold_days
        event_rows: dict[str, dict[str, Any]] = {}

        for policy_id, template in templates.items():
            outcome = evaluate_price_path(
                template,
                signal_time=signal_time,
                signal_price=float(event["signal_price"]),
                bars=paths.get(prediction_id, ()),
                target_drawdown=config.target_drawdown,
            )
            filled_allocation = sum(
                leg.allocation for leg in outcome.filled_legs
            )
            gross_filled = float(outcome.realized_return or 0.0)
            gross_planned = (
                gross_filled * filled_allocation * template.risk_multiplier
            )
            trading_cost = (
                round_trip_cost * filled_allocation * template.risk_multiplier
            )
            exit_time = outcome.exit_time or (
                signal_time + timedelta(hours=template.horizon_hours)
            )
            funding_planned = (
                _funding_return(
                    funding.get(prediction_id, []),
                    outcome.filled_legs,
                    exit_time,
                )
                * template.risk_multiplier
            )
            net_planned = gross_planned - trading_cost + funding_planned
            row = {
                "prediction_id": prediction_id,
                "symbol": event["symbol"],
                "signal_time": signal_time.isoformat(),
                "fold": fold,
                "model_id": event["model_id"],
                "label_version": event["label_version"],
                "model_probability": event["calibrated_probability"],
                "heuristic_score": event["heuristic_score"],
                "quality_score": event["data_quality_score"],
                "volume_24h_usd": round(volume_24h, 2),
                "liquidity_tier": _liquidity_tier(volume_24h),
                "market_cap_tier": "unavailable",
                "volatility_score": scores.volatility,
                "volatility_tier": _volatility_tier(scores.volatility),
                "squeeze_score": scores.squeeze,
                "router_policy_id": decision.policy.policy_id,
                "router_eligible": decision.eligible,
                "evaluated_policy_id": policy_id,
                "policy_version": template.version,
                "status": outcome.status,
                "filled_legs": len(outcome.filled_legs),
                "filled_allocation": round(filled_allocation, 4),
                "average_entry": outcome.average_entry,
                "target_price": outcome.target_price,
                "stop_price": outcome.stop_price,
                "gross_return_filled": round(gross_filled, 8),
                "gross_return_planned": round(gross_planned, 8),
                "trading_cost_planned": round(trading_cost, 8),
                "funding_return_planned": round(funding_planned, 8),
                "net_return_planned": round(net_planned, 8),
                "mae": outcome.max_adverse_excursion,
                "mfe": outcome.max_favorable_excursion,
                **event_features,
            }
            output_rows.append(row)
            event_rows[policy_id] = row

        selected = dict(event_rows[decision.policy.policy_id])
        selected["evaluated_policy_id"] = "router_champion"
        router_rows.append(selected)

    summaries = {
        policy_id: _summary(
            [
                row
                for row in output_rows
                if row["evaluated_policy_id"] == policy_id
            ]
        )
        for policy_id in templates
    }
    summaries["router_champion"] = _summary(router_rows)
    summaries["router_champion_eligible"] = _summary(
        [row for row in router_rows if row["router_eligible"]]
    )

    report = {
        "backtest_version": BACKTEST_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "data": {
            "db_path": str(config.db_path),
            "model_id": config.model_id,
            "signal_start": min(event["signal_time"] for event in events).isoformat(),
            "signal_end": max(event["signal_time"] for event in events).isoformat(),
            "episode_count": len(events),
            "fold_days": config.fold_days,
            "fold_count": max(row["fold"] for row in output_rows),
            "market_cap_note": (
                "Point-in-time market cap is unavailable; liquidity tiers use "
                "trailing quote volume and are not market-cap substitutes."
            ),
        },
        "assumptions": {
            **asdict(config),
            "db_path": str(config.db_path),
            "output_json": str(config.output_json),
            "output_csv": str(config.output_csv),
            "intrabar_rule": "stop_first_if_target_and_stop_share_a_bar",
            "signal_episode_rule": (
                "rising edge at probability threshold or observation gap "
                f"greater than {config.reset_gap_minutes} minutes"
            ),
        },
        "policy_summaries": summaries,
        "policy_by_fold": {
            policy_id: _grouped_summary(
                [
                    row
                    for row in output_rows
                    if row["evaluated_policy_id"] == policy_id
                ],
                "fold",
            )
            for policy_id in templates
        },
        "policy_by_liquidity": {
            policy_id: _grouped_summary(
                [
                    row
                    for row in output_rows
                    if row["evaluated_policy_id"] == policy_id
                ],
                "liquidity_tier",
            )
            for policy_id in templates
        },
        "policy_by_volatility": {
            policy_id: _grouped_summary(
                [
                    row
                    for row in output_rows
                    if row["evaluated_policy_id"] == policy_id
                ],
                "volatility_tier",
            )
            for policy_id in templates
        },
        "router_by_fold": _grouped_summary(router_rows, "fold"),
        "router_by_liquidity": _grouped_summary(
            router_rows,
            "liquidity_tier",
        ),
        "router_by_volatility": _grouped_summary(
            router_rows,
            "volatility_tier",
        ),
        "router_policy_counts": {
            policy_id: sum(
                row["router_policy_id"] == policy_id for row in router_rows
            )
            for policy_id in templates
        },
        "router_eligible_count": sum(
            row["router_eligible"] for row in router_rows
        ),
    }

    config.output_json.parent.mkdir(parents=True, exist_ok=True)
    config.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    config.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with config.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(output_rows[0]))
        writer.writeheader()
        writer.writerows(output_rows)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data_live/live.duckdb"))
    parser.add_argument("--settings", type=Path, default=Path("configs/live.yaml"))
    parser.add_argument("--model-id")
    parser.add_argument("--threshold", type=float, default=0.41)
    parser.add_argument(
        "--output-json",
        type=Path,
        default=Path("artifacts/execution_policy_backtest_latest.json"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=Path("artifacts/execution_policy_backtest_events_latest.csv"),
    )
    args = parser.parse_args()
    settings = AppSettings.from_yaml(args.settings)
    report = run_policy_backtest(
        PolicyBacktestConfig(
            db_path=args.db,
            output_json=args.output_json,
            output_csv=args.output_csv,
            model_id=args.model_id,
            probability_threshold=args.threshold,
        ),
        policy_config=settings.execution_policy,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
