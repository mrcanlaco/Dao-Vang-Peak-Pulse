"""Locked August-2026 forward backtest for the 48h distribution challenger.

The signal model, probability threshold, and optional execution template are
locked using only observations whose complete 48-hour labels end before the
August cutoff.  August OHLC/funding outcomes are loaded only after the policy
lock is written.  This is a research runner and never changes live config.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd

from dao_vang.experiments.train_distribution_v2 import (
    SERVING_FEATURE_COLS,
    _build_estimator,
    _calibrator,
    _partition_history,
    _predict_calibrated,
)


@dataclass(frozen=True)
class Template:
    template_id: str
    offsets: tuple[float, float, float]
    allocations: tuple[float, float, float]
    entry_window_hours: int
    hard_stop_pct: float = 0.16
    horizon_hours: int = 48


@dataclass(frozen=True)
class Config:
    historical_dataset: Path = Path("artifacts/universe_policy_v2_48h.duckdb")
    live_feature_db: Path = Path("data_live/live.duckdb")
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    cutoff: str = "2026-08-01T00:00:00+07:00"
    forward_end: str = "2026-08-26T02:00:00+07:00"
    pump_threshold: float = 0.15
    probability_threshold: float = 0.30
    cooldown_hours: int = 24
    sample_minute: int = 4
    target_drawdown: float = 0.20
    hard_stop_pct: float = 0.16
    fee_bps_per_side: float = 5.0
    slippage_bps_per_side: float = 5.0
    historical_oos_folds: int = 4
    warmup_days: int = 90
    random_state: int = 42
    lock_json: Path = Path("artifacts/forward48_scalein_policy_lock_20260913.json")
    output_json: Path = Path("artifacts/forward48_scalein_backtest_20260913.json")
    output_csv: Path = Path("artifacts/forward48_scalein_events_20260913.csv")


BUILT_INS: tuple[Template, ...] = (
    Template("compact_0_3_6", (0.0, 0.03, 0.06), (0.20, 0.30, 0.50), 6),
    Template("balanced_0_5_10", (0.0, 0.05, 0.10), (0.20, 0.30, 0.50), 6),
    Template("deep_0_8_14", (0.0, 0.08, 0.14), (0.10, 0.30, 0.60), 12),
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _load_historical(config: Config) -> pd.DataFrame:
    cutoff = pd.Timestamp(config.cutoff).tz_convert("UTC")
    label_safe_end = cutoff - pd.Timedelta(hours=48)
    conn = duckdb.connect(str(config.historical_dataset), read_only=True)
    try:
        frame = conn.execute(
            """
            SELECT * FROM universe_policy_candidates_v2
            WHERE label_value IS NOT NULL
              AND price_ret_24h >= ?
              AND feature_time < ?
            ORDER BY feature_time, symbol
            """,
            [config.pump_threshold, label_safe_end.to_pydatetime()],
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["label_value"] = frame["label_value"].astype("int8")
    if frame.empty:
        raise RuntimeError("historical label-safe frame is empty")
    return frame


def _fold_boundaries(
    frame: pd.DataFrame, warmup_days: int, folds: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start = frame["feature_time"].min()
    end = frame["feature_time"].max() + pd.Timedelta(microseconds=1)
    first = start + pd.Timedelta(days=warmup_days)
    step = (end - first) / folds
    return [(first + i * step, first + (i + 1) * step) for i in range(folds)]


def _dedupe_signals(
    frame: pd.DataFrame,
    probabilities: np.ndarray,
    threshold: float,
    cooldown_hours: int,
    *,
    seed_since: pd.Timestamp | None = None,
) -> pd.DataFrame:
    scored = frame[["symbol", "feature_time", "entry_price"]].copy()
    scored["probability"] = probabilities
    scored = scored.sort_values(["feature_time", "symbol"]).reset_index(drop=True)
    last: dict[str, pd.Timestamp] = {}
    selected: list[int] = []
    cooldown = pd.Timedelta(hours=cooldown_hours)
    for index, row in scored.iterrows():
        if float(row["probability"]) < threshold:
            continue
        symbol = str(row["symbol"])
        when = pd.Timestamp(row["feature_time"])
        previous = last.get(symbol)
        if previous is not None and when < previous + cooldown:
            continue
        last[symbol] = when
        if seed_since is None or when >= seed_since:
            selected.append(index)
    return scored.loc[selected].reset_index(drop=True)


def _historical_oos_signals(config: Config, frame: pd.DataFrame) -> pd.DataFrame:
    embargo = pd.Timedelta(hours=48)
    records: list[pd.DataFrame] = []
    for fold, (test_start, test_end) in enumerate(
        _fold_boundaries(frame, config.warmup_days, config.historical_oos_folds), 1
    ):
        history = frame[frame["feature_time"] < test_start - embargo]
        fit, calibration, _policy = _partition_history(history, embargo)
        test = frame[
            (frame["feature_time"] >= test_start)
            & (frame["feature_time"] < test_end)
        ]
        if any(
            len(part) < 50 or part["label_value"].nunique() < 2
            for part in (fit, calibration, test)
        ):
            continue
        model = _build_estimator("lightgbm", config.random_state + fold)
        model.fit(fit[list(SERVING_FEATURE_COLS)], fit["label_value"])
        calibrator = _calibrator(
            model, calibration, SERVING_FEATURE_COLS, "isotonic"
        )
        _, probability = _predict_calibrated(
            model, calibrator, test, SERVING_FEATURE_COLS
        )
        selected = _dedupe_signals(
            test,
            probability,
            config.probability_threshold,
            config.cooldown_hours,
        )
        selected["fold"] = fold
        records.append(selected)
    if not records:
        raise RuntimeError("no historical OOS signals were generated")
    return pd.concat(records, ignore_index=True).sort_values("feature_time")


def _fit_locked_model(config: Config, frame: pd.DataFrame) -> tuple[Any, Any, dict]:
    embargo = pd.Timedelta(hours=48)
    fit, calibration, policy = _partition_history(frame, embargo)
    if any(len(part) < 50 or part["label_value"].nunique() < 2 for part in (fit, calibration, policy)):
        raise RuntimeError("insufficient fit/calibration/policy history")
    model = _build_estimator("lightgbm", config.random_state + 1000)
    model.fit(fit[list(SERVING_FEATURE_COLS)], fit["label_value"])
    calibrator = _calibrator(model, calibration, SERVING_FEATURE_COLS, "isotonic")
    _, policy_probability = _predict_calibrated(
        model, calibrator, policy, SERVING_FEATURE_COLS
    )
    policy_signal = policy_probability >= config.probability_threshold
    policy_precision = (
        float(policy.loc[policy_signal, "label_value"].mean())
        if policy_signal.any()
        else 0.0
    )
    metadata = {
        "fit_start": fit["feature_time"].min(),
        "fit_end": fit["feature_time"].max(),
        "fit_rows": len(fit),
        "calibration_start": calibration["feature_time"].min(),
        "calibration_end": calibration["feature_time"].max(),
        "calibration_rows": len(calibration),
        "policy_start": policy["feature_time"].min(),
        "policy_end": policy["feature_time"].max(),
        "policy_rows": len(policy),
        "policy_raw_signals": int(policy_signal.sum()),
        "policy_row_precision": policy_precision,
    }
    return model, calibrator, metadata


def _load_forward_candidates(config: Config) -> pd.DataFrame:
    cutoff = pd.Timestamp(config.cutoff).tz_convert("UTC")
    start = cutoff - pd.Timedelta(hours=config.cooldown_hours)
    end = pd.Timestamp(config.forward_end).tz_convert("UTC")
    feature_cols = ", ".join(f"f.{column}" for column in SERVING_FEATURE_COLS)
    conn = duckdb.connect()
    conn.execute(
        f"ATTACH '{str(config.live_feature_db.resolve()).replace(chr(92), '/')}' AS live (READ_ONLY)"
    )
    conn.execute(
        f"ATTACH '{str(config.market_db.resolve()).replace(chr(92), '/')}' AS market (READ_ONLY)"
    )
    try:
        frame = conn.execute(
            f"""
            SELECT f.feature_time, f.symbol, k.close AS entry_price, {feature_cols}
            FROM live.main.feature_results f
            INNER JOIN market.main.klines_5m k
              ON k.symbol=f.symbol AND k.close_time=f.feature_time
            WHERE f.feature_time >= ? AND f.feature_time < ?
              AND f.price_ret_24h >= ?
              AND EXTRACT(MINUTE FROM f.feature_time)=?
            ORDER BY f.feature_time, f.symbol
            """,
            [start.to_pydatetime(), end.to_pydatetime(), config.pump_threshold, config.sample_minute],
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    return frame


def _load_market_paths(
    config: Config, signals: pd.DataFrame
) -> tuple[dict[str, list[tuple]], dict[str, list[tuple]]]:
    ids = signals[["signal_id", "symbol", "feature_time"]].copy()
    conn = duckdb.connect(str(config.market_db), read_only=True)
    conn.register("signal_input", ids)
    try:
        path_rows = conn.execute(
            """
            SELECT s.signal_id, k.close_time, CAST(k.high AS DOUBLE),
                   CAST(k.low AS DOUBLE), CAST(k.close AS DOUBLE)
            FROM signal_input s
            INNER JOIN klines_5m k ON k.symbol=s.symbol
              AND k.close_time > s.feature_time
              AND k.close_time <= s.feature_time + INTERVAL '48' HOUR
            ORDER BY s.signal_id, k.close_time
            """
        ).fetchall()
        funding_rows = conn.execute(
            """
            SELECT s.signal_id, f.funding_time, CAST(f.funding_rate AS DOUBLE)
            FROM signal_input s
            INNER JOIN funding_history f ON f.symbol=s.symbol
              AND f.funding_time > s.feature_time
              AND f.funding_time <= s.feature_time + INTERVAL '48' HOUR
            ORDER BY s.signal_id, f.funding_time
            """
        ).fetchall()
    finally:
        conn.close()
    paths: dict[str, list[tuple]] = {}
    funding: dict[str, list[tuple]] = {}
    for signal_id, *row in path_rows:
        paths.setdefault(str(signal_id), []).append(tuple(row))
    for signal_id, *row in funding_rows:
        funding.setdefault(str(signal_id), []).append(tuple(row))
    return paths, funding


def _evaluate_path(
    template: Template,
    signal_time: pd.Timestamp,
    signal_price: float,
    bars: Iterable[tuple],
    funding_points: Iterable[tuple],
    round_trip_cost: float,
    target_drawdown: float,
) -> dict[str, Any]:
    prices = [signal_price * (1.0 + offset) for offset in template.offsets]
    entry_end = signal_time + pd.Timedelta(hours=template.entry_window_hours)
    horizon_end = signal_time + pd.Timedelta(hours=template.horizon_hours)
    fills: list[tuple[int, pd.Timestamp, float, float]] = []
    filled: set[int] = set()
    status = "not_filled"
    exit_time: pd.Timestamp | None = None
    last_close: float | None = None
    max_high: float | None = None
    min_low: float | None = None
    ambiguous = False

    for timestamp, high, low, close in bars:
        when = pd.Timestamp(timestamp).tz_convert("UTC")
        if when > horizon_end:
            break
        last_close = float(close)
        if when <= entry_end:
            for index, (price, allocation) in enumerate(
                zip(prices, template.allocations, strict=True)
            ):
                if index not in filled and float(high) >= price:
                    fills.append((index + 1, when, price, allocation))
                    filled.add(index)
        if not fills:
            continue
        allocation = sum(item[3] for item in fills)
        average = sum(item[2] * item[3] for item in fills) / allocation
        stop_price = average * (1.0 + template.hard_stop_pct)
        target_price = average * (1.0 - target_drawdown)
        max_high = float(high) if max_high is None else max(max_high, float(high))
        min_low = float(low) if min_low is None else min(min_low, float(low))
        stop_touched = float(high) >= stop_price
        target_touched = float(low) <= target_price
        if stop_touched and target_touched:
            status = "stop_ambiguous"
            ambiguous = True
            exit_time = when
            break
        if stop_touched:
            status = "stop"
            exit_time = when
            break
        if target_touched:
            status = "target"
            exit_time = when
            break
        status = "timeout"

    if not fills:
        return {
            "status": "not_filled", "filled_legs": 0, "filled_allocation": 0.0,
            "average_entry": None, "target_price": None, "stop_price": None,
            "exit_time": None, "gross_return_filled": 0.0,
            "gross_return_filled_target_first": 0.0, "trading_cost_planned": 0.0,
            "funding_return_planned": 0.0, "net_return_planned": 0.0,
            "net_return_planned_target_first": 0.0, "mae": None, "mfe": None,
            "complete_path": False,
        }

    allocation = sum(item[3] for item in fills)
    average = sum(item[2] * item[3] for item in fills) / allocation
    stop_price = average * (1.0 + template.hard_stop_pct)
    target_price = average * (1.0 - target_drawdown)
    if status == "target":
        gross = target_drawdown
    elif status in {"stop", "stop_ambiguous"}:
        gross = -template.hard_stop_pct
    elif last_close is not None:
        gross = (average - last_close) / average
    else:
        gross = 0.0
    gross_target_first = target_drawdown if ambiguous else gross
    actual_exit = exit_time or horizon_end
    funding_return = 0.0
    for timestamp, rate in funding_points:
        when = pd.Timestamp(timestamp).tz_convert("UTC")
        if when > actual_exit:
            break
        active = sum(item[3] for item in fills if item[1] < when)
        funding_return += float(rate) * active
    trading_cost = round_trip_cost * allocation
    return {
        "status": status,
        "filled_legs": len(fills),
        "filled_allocation": allocation,
        "average_entry": average,
        "target_price": target_price,
        "stop_price": stop_price,
        "exit_time": actual_exit,
        "gross_return_filled": gross,
        "gross_return_filled_target_first": gross_target_first,
        "trading_cost_planned": trading_cost,
        "funding_return_planned": funding_return,
        "net_return_planned": gross * allocation - trading_cost + funding_return,
        "net_return_planned_target_first": (
            gross_target_first * allocation - trading_cost + funding_return
        ),
        "mae": None if max_high is None else (max_high - average) / average,
        "mfe": None if min_low is None else (average - min_low) / average,
        "complete_path": bool(bars) and pd.Timestamp(list(bars)[-1][0]).tz_convert("UTC") >= horizon_end - pd.Timedelta(minutes=5),
    }


def _max_drawdown(returns: Iterable[float]) -> float:
    equity = peak = 1.0
    maximum = 0.0
    for value in returns:
        equity *= max(0.0, 1.0 + float(value))
        peak = max(peak, equity)
        maximum = max(maximum, (peak - equity) / peak)
    return maximum


def _summarize(rows: pd.DataFrame) -> dict[str, Any]:
    if rows.empty:
        return {"signals": 0}
    complete = rows[rows["complete_path"]].copy()
    source = complete if not complete.empty else rows
    statuses = source["status"]
    returns = source["net_return_planned"].astype(float)
    optimistic = source["net_return_planned_target_first"].astype(float)
    return {
        "signals": len(rows),
        "complete_signals": len(complete),
        "target_rate": float((statuses == "target").mean()),
        "stop_rate": float(statuses.isin(["stop", "stop_ambiguous"]).mean()),
        "timeout_rate": float((statuses == "timeout").mean()),
        "not_filled_rate": float((statuses == "not_filled").mean()),
        "ambiguous_rate": float((statuses == "stop_ambiguous").mean()),
        "entry1_fill_rate": float((source["filled_legs"] >= 1).mean()),
        "entry2_fill_rate": float((source["filled_legs"] >= 2).mean()),
        "entry3_fill_rate": float((source["filled_legs"] >= 3).mean()),
        "average_filled_allocation": float(source["filled_allocation"].mean()),
        "net_ev_stop_first": float(returns.mean()),
        "net_ev_target_first_sensitivity": float(optimistic.mean()),
        "median_net_return": float(returns.median()),
        "sequential_compounded_max_drawdown": _max_drawdown(returns),
        "funding_return_mean": float(source["funding_return_planned"].mean()),
        "mae_p90": float(source["mae"].dropna().quantile(0.90)) if source["mae"].notna().any() else None,
        "mfe_p90": float(source["mfe"].dropna().quantile(0.90)) if source["mfe"].notna().any() else None,
    }


def _evaluate_templates(
    signals: pd.DataFrame,
    templates: Iterable[Template],
    paths: dict[str, list[tuple]],
    funding: dict[str, list[tuple]],
    config: Config,
    period: str,
) -> pd.DataFrame:
    cost = 2.0 * (config.fee_bps_per_side + config.slippage_bps_per_side) / 10_000.0
    output: list[dict[str, Any]] = []
    for signal in signals.itertuples(index=False):
        signal_id = str(signal.signal_id)
        for template in templates:
            outcome = _evaluate_path(
                template,
                pd.Timestamp(signal.feature_time),
                float(signal.entry_price),
                paths.get(signal_id, []),
                funding.get(signal_id, []),
                cost,
                config.target_drawdown,
            )
            output.append(
                {
                    "period": period,
                    "signal_id": signal_id,
                    "symbol": signal.symbol,
                    "signal_time": pd.Timestamp(signal.feature_time),
                    "probability": float(signal.probability),
                    "fold": getattr(signal, "fold", None),
                    "template_id": template.template_id,
                    **outcome,
                }
            )
    return pd.DataFrame(output)


def _grid() -> list[Template]:
    allocations = (
        (0.10, 0.30, 0.60),
        (0.20, 0.30, 0.50),
        (1 / 3, 1 / 3, 1 / 3),
    )
    templates: list[Template] = []
    for e2 in (0.03, 0.05, 0.08, 0.10):
        for e3 in (0.06, 0.10, 0.14, 0.18):
            if e3 <= e2:
                continue
            for alloc_index, allocation in enumerate(allocations, 1):
                for window in (6, 12, 24):
                    templates.append(
                        Template(
                            f"opt_e{int(e2*100)}_{int(e3*100)}_a{alloc_index}_w{window}",
                            (0.0, e2, e3), allocation, window,
                        )
                    )
    return templates


def _choose_optimized(events: pd.DataFrame, templates: list[Template]) -> tuple[Template, dict]:
    candidates: list[dict[str, Any]] = []
    for template in templates:
        rows = events[events["template_id"] == template.template_id].sort_values("signal_time")
        summary = _summarize(rows)
        weekly = rows.assign(
            week=rows["signal_time"].dt.strftime("%G-W%V")
        ).groupby("week")["net_return_planned"].mean()
        weekly_std = float(weekly.std(ddof=0)) if len(weekly) else 0.0
        objective = (
            summary["net_ev_stop_first"]
            - 0.50 * weekly_std
            - 0.10 * summary["sequential_compounded_max_drawdown"] / max(1, len(rows))
        )
        candidates.append(
            {
                "template_id": template.template_id,
                "objective": objective,
                "weekly_ev_std": weekly_std,
                "summary": summary,
            }
        )
    best = max(candidates, key=lambda row: (row["objective"], row["summary"]["net_ev_stop_first"]))
    selected = next(item for item in templates if item.template_id == best["template_id"])
    return selected, {"selected": best, "candidate_count": len(candidates), "top10": sorted(candidates, key=lambda row: row["objective"], reverse=True)[:10]}


def _with_ids(signals: pd.DataFrame, prefix: str) -> pd.DataFrame:
    result = signals.copy().reset_index(drop=True)
    result["signal_id"] = [f"{prefix}-{index:05d}" for index in range(len(result))]
    return result


def _weekly(events: pd.DataFrame, template_id: str) -> dict[str, Any]:
    rows = events[events["template_id"] == template_id].copy()
    rows["week"] = rows["signal_time"].dt.strftime("%G-W%V")
    return {
        str(week): _summarize(group.sort_values("signal_time"))
        for week, group in rows.groupby("week", sort=True)
    }


def run(config: Config) -> dict[str, Any]:
    historical = _load_historical(config)
    historical_signals = _with_ids(_historical_oos_signals(config, historical), "hist")
    historical_paths, historical_funding = _load_market_paths(config, historical_signals)
    grid = _grid()
    historical_grid_events = _evaluate_templates(
        historical_signals, grid, historical_paths, historical_funding, config, "historical_oos"
    )
    optimized, optimization = _choose_optimized(historical_grid_events, grid)

    model, calibrator, model_metadata = _fit_locked_model(config, historical)
    forward_candidates = _load_forward_candidates(config)
    _, probabilities = _predict_calibrated(
        model, calibrator, forward_candidates, SERVING_FEATURE_COLS
    )
    cutoff = pd.Timestamp(config.cutoff).tz_convert("UTC")
    forward_signals = _with_ids(
        _dedupe_signals(
            forward_candidates,
            probabilities,
            config.probability_threshold,
            config.cooldown_hours,
            seed_since=cutoff,
        ),
        "aug",
    )

    lock_payload = {
        "lock_version": "forward48_scalein_policy_lock_v1",
        "locked_before_outcome_load": True,
        "cutoff": cutoff,
        "label_safe_training_end_exclusive": cutoff - pd.Timedelta(hours=48),
        "label_contract": {
            "target_drawdown": config.target_drawdown,
            "hard_stop_from_weighted_average": config.hard_stop_pct,
            "horizon_hours": 48,
            "same_bar_rule": "stop_first_with_target_first_sensitivity",
        },
        "signal_policy": {
            "pump_threshold": config.pump_threshold,
            "probability_threshold": config.probability_threshold,
            "cooldown_hours": config.cooldown_hours,
            "sample_minute": config.sample_minute,
            "features": list(SERVING_FEATURE_COLS),
            "model": "lightgbm_existing_25_feature_spec_isotonic",
        },
        "model_training": model_metadata,
        "historical_oos_signal_count": len(historical_signals),
        "execution_optimization": optimization,
        "locked_optimized_template": asdict(optimized),
        "forward_signal_count_before_outcome_load": len(forward_signals),
        "forward_signal_fingerprint": hashlib.sha256(
            forward_signals[["signal_id", "symbol", "feature_time", "probability"]]
            .to_csv(index=False).encode()
        ).hexdigest(),
        "live_configuration_changed": False,
    }
    encoded = json.dumps(lock_payload, default=_jsonable, ensure_ascii=False, sort_keys=True).encode()
    lock_payload["policy_lock_sha256"] = hashlib.sha256(encoded).hexdigest()
    config.lock_json.parent.mkdir(parents=True, exist_ok=True)
    config.lock_json.write_text(
        json.dumps(lock_payload, default=_jsonable, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Forward outcomes are intentionally loaded only after the immutable lock above.
    forward_paths, forward_funding = _load_market_paths(config, forward_signals)
    templates = [*BUILT_INS, optimized]
    forward_events = _evaluate_templates(
        forward_signals, templates, forward_paths, forward_funding, config, "august_forward"
    )
    historical_builtin_events = _evaluate_templates(
        historical_signals, templates, historical_paths, historical_funding, config, "historical_oos"
    )
    summaries = {
        template.template_id: _summarize(
            forward_events[forward_events["template_id"] == template.template_id].sort_values("signal_time")
        )
        for template in templates
    }
    report = {
        "experiment": "forward48_scalein_august_v1",
        "research_only": True,
        "live_configuration_changed": False,
        "generated_at": datetime.now(timezone.utc),
        "config": asdict(config),
        "policy_lock": str(config.lock_json),
        "policy_lock_sha256": lock_payload["policy_lock_sha256"],
        "cutoffs": {
            "forward_start": cutoff,
            "forward_end_exclusive": pd.Timestamp(config.forward_end).tz_convert("UTC"),
            "historical_label_safe_end_exclusive": cutoff - pd.Timedelta(hours=48),
        },
        "assumptions": {
            "entry_order": "limit short; eligible on future 5m bars through entry window",
            "target": "20% below current weighted-average fill after each leg",
            "stop": "16% above current weighted-average fill after each leg",
            "same_bar": "stop-first; target-first EV also reported",
            "costs": "5 bps fee + 5 bps slippage per side (20 bps round trip)",
            "funding": "actual funding while each leg is active; positive funding benefits short",
            "drawdown": "sequential compounded signal returns, not an overlapping portfolio simulation",
        },
        "sample": {
            "historical_oos_signals": len(historical_signals),
            "forward_candidates_including_cooldown_seed": len(forward_candidates),
            "forward_raw_rows_above_threshold_including_seed": int(
                (probabilities >= config.probability_threshold).sum()
            ),
            "forward_probability_quantiles": {
                str(quantile): float(np.quantile(probabilities, quantile))
                for quantile in (0.50, 0.75, 0.90, 0.95, 0.99)
            } if len(probabilities) else {},
            "august_forward_signals": len(forward_signals),
            "symbols": int(forward_signals["symbol"].nunique()) if len(forward_signals) else 0,
            "signal_start": forward_signals["feature_time"].min() if len(forward_signals) else None,
            "signal_end": forward_signals["feature_time"].max() if len(forward_signals) else None,
        },
        "templates": [asdict(item) for item in templates],
        "optimization_historical_only": optimization,
        "historical_oos_template_summaries": {
            template.template_id: _summarize(
                historical_builtin_events[historical_builtin_events["template_id"] == template.template_id].sort_values("signal_time")
            )
            for template in templates
        },
        "historical_oos_by_fold": {
            template.template_id: {
                str(int(fold)): _summarize(group.sort_values("signal_time"))
                for fold, group in historical_builtin_events[
                    historical_builtin_events["template_id"] == template.template_id
                ].groupby("fold", sort=True)
            }
            for template in templates
        },
        "august_forward_summaries": summaries,
        "august_by_week": {template.template_id: _weekly(forward_events, template.template_id) for template in templates},
        "winner_by_forward_net_ev_for_description_only": max(
            summaries, key=lambda item: summaries[item].get("net_ev_stop_first", -math.inf)
        ) if summaries else None,
        "promotion_decision": {
            "eligible": False,
            "reason": "research-only forward sample; live remains unchanged",
        },
    }
    config.output_json.write_text(
        json.dumps(report, default=_jsonable, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    forward_events.to_csv(config.output_csv, index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=Config.output_json)
    parser.add_argument("--output-csv", type=Path, default=Config.output_csv)
    parser.add_argument("--lock-json", type=Path, default=Config.lock_json)
    args = parser.parse_args()
    config = Config(output_json=args.output_json, output_csv=args.output_csv, lock_json=args.lock_json)
    report = run(config)
    print(json.dumps({
        "sample": report["sample"],
        "summaries": report["august_forward_summaries"],
        "optimized": report["optimization_historical_only"]["selected"],
    }, default=_jsonable, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
