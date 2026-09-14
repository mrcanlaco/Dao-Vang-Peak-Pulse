"""Execution/risk alpha search on the frozen 48h timing challenger.

This runner never changes signal generation.  Folds 1-3 of the historical
timing OOS stream are development.  Exactly one execution candidate is locked
before fold-4 paths are loaded.  Fold 4 is therefore an execution-only
chronological holdout, not sealed end-to-end evidence (the timing policy was
previously selected on all historical folds).
"""

from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb
import numpy as np
import pandas as pd

try:
    from forward48_timing_backtest import TimingPolicy, select_signals
except ImportError:
    from scripts.forward48_timing_backtest import TimingPolicy, select_signals


TARGET = 0.20
HARD_STOP = 0.16
HORIZON_HOURS = 48
ROUND_TRIP_COST = 0.002
MIN_EXACT_COVERAGE = 0.95
BASELINE_ID = "compact_0_3_6_20_30_50_w6"


@dataclass(frozen=True)
class Config:
    timing_oos_csv: Path = Path(
        "artifacts/forward48_timing_20260913/forward48_timing_historical_oos.csv"
    )
    candidate_db: Path = Path("artifacts/universe_policy_v2_48h.duckdb")
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    output_dir: Path = Path("artifacts/forward48_execution_risk_20260914")
    development_folds: tuple[int, ...] = (1, 2, 3)
    holdout_fold: int = 4
    min_exact_coverage: float = MIN_EXACT_COVERAGE


@dataclass(frozen=True)
class Variant:
    variant_id: str
    family: str
    window_hours: int = 6
    allocations: tuple[float, float, float] = (0.20, 0.30, 0.50)
    allocation_mode: str = "fixed"
    offset_mode: str = "fixed"
    add_gate: str = "none"
    time_stop_hours: int = 48
    partial_at_10_fraction: float = 0.0
    breakeven_after_10: bool = False
    risk_normalized: bool = False


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    raise TypeError(type(value).__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def frozen_timing_policy() -> TimingPolicy:
    return TimingPolicy(
        min_peak_pump_24h=0.30,
        confirmations=2,
        min_episode_age_hours=4,
        probability_tolerance=0.10,
    )


def variants() -> list[Variant]:
    """Small predeclared hypothesis set; no Cartesian parameter grid."""
    return [
        Variant(BASELINE_ID, "baseline"),
        Variant("entry_window_3h", "entry_window", window_hours=3),
        Variant("entry_window_12h", "entry_window", window_hours=12),
        Variant("entry_window_24h", "entry_window", window_hours=24),
        Variant(
            "overshoot_backload", "dynamic_allocation", allocation_mode="overshoot"
        ),
        Variant(
            "high_vol_backload", "dynamic_allocation", allocation_mode="volatility"
        ),
        Variant("vol_scaled_offsets", "dynamic_offsets", offset_mode="volatility"),
        Variant("reversal_adds", "conditional_add", add_gate="reversal"),
        Variant(
            "exhaustion_reversal_adds",
            "conditional_add",
            add_gate="exhaustion_reversal",
        ),
        Variant(
            "vol_offsets_exhaustion_adds",
            "conditional_add",
            offset_mode="volatility",
            add_gate="exhaustion_reversal",
        ),
        Variant("time_stop_12h", "time_stop", time_stop_hours=12),
        Variant("time_stop_24h", "time_stop", time_stop_hours=24),
        Variant("time_stop_36h", "time_stop", time_stop_hours=36),
        Variant("partial_50_at_10", "exit_management", partial_at_10_fraction=0.50),
        Variant("breakeven_after_10", "exit_management", breakeven_after_10=True),
        Variant("vol_risk_normalized", "risk_sizing", risk_normalized=True),
    ]


def load_frozen_signals(config: Config) -> pd.DataFrame:
    stream = pd.read_csv(config.timing_oos_csv)
    stream["feature_time"] = pd.to_datetime(stream["feature_time"], utc=True)
    selected = select_signals(stream, frozen_timing_policy()).copy()
    selected["symbol_raw"] = selected["symbol"].astype(str)
    selected["symbol"] = selected["symbol_raw"].str.strip().str.upper()
    selected["signal_id"] = [f"hist-timing-{i:04d}" for i in range(len(selected))]

    conn = duckdb.connect(str(config.candidate_db), read_only=True)
    conn.register("locked", selected[["signal_id", "symbol", "feature_time"]])
    try:
        enriched = conn.execute(
            """
            SELECT l.signal_id, c.entry_price, c.price_volatility_24h,
                   c.funding_rate_raw, c.funding_change_8h,
                   c.funding_persistence_7d, c.momentum_deceleration_4h,
                   c.quote_volume_24h
            FROM locked l
            LEFT JOIN universe_policy_candidates_v2 c
              ON upper(trim(c.symbol))=l.symbol AND c.feature_time=l.feature_time
            QUALIFY row_number() OVER (PARTITION BY l.signal_id ORDER BY c.feature_time)=1
            """
        ).fetchdf()
    finally:
        conn.close()
    selected = selected.merge(
        enriched, on="signal_id", how="left", validate="one_to_one"
    )
    if selected["entry_price"].isna().any():
        missing = selected.loc[selected["entry_price"].isna(), "signal_id"].tolist()
        raise RuntimeError(
            f"same-lineage entry price missing for {len(missing)} signals"
        )
    return selected.sort_values(["feature_time", "symbol"]).reset_index(drop=True)


def _load_paths(
    config: Config, signals: pd.DataFrame
) -> tuple[dict[str, list[tuple]], dict[str, list[tuple]], dict[str, Any]]:
    relation = signals[["signal_id", "symbol", "feature_time", "entry_price"]].copy()
    conn = duckdb.connect(str(config.market_db), read_only=True)
    conn.register("locked", relation)
    try:
        exact = conn.execute(
            """
            SELECT l.signal_id, k.close_time, CAST(k.close AS DOUBLE) market_close
            FROM locked l LEFT JOIN klines_5m k
              ON upper(trim(k.symbol))=l.symbol AND k.close_time=l.feature_time
            """
        ).fetchdf()
        path_rows = conn.execute(
            """
            SELECT l.signal_id, k.close_time, CAST(k.high AS DOUBLE),
                   CAST(k.low AS DOUBLE), CAST(k.close AS DOUBLE)
            FROM locked l INNER JOIN klines_5m k
              ON upper(trim(k.symbol))=l.symbol
             AND k.close_time > l.feature_time
             AND k.close_time <= l.feature_time + INTERVAL '48' HOUR
            ORDER BY l.signal_id, k.close_time
            """
        ).fetchall()
        funding_rows = conn.execute(
            """
            SELECT l.signal_id, f.funding_time, CAST(f.funding_rate AS DOUBLE)
            FROM locked l INNER JOIN funding_history f
              ON upper(trim(f.symbol))=l.symbol
             AND f.funding_time > l.feature_time
             AND f.funding_time <= l.feature_time + INTERVAL '48' HOUR
            ORDER BY l.signal_id, f.funding_time
            """
        ).fetchall()
    finally:
        conn.close()

    exact = relation.merge(exact, on="signal_id", how="left", validate="one_to_one")
    exact_matches = int(exact["close_time"].notna().sum())
    exact_coverage = exact_matches / len(relation) if len(relation) else 0.0
    price_aligned = int(
        (
            (exact["market_close"] - exact["entry_price"]).abs()
            / exact["entry_price"].abs().replace(0, np.nan)
            <= 1e-6
        )
        .fillna(False)
        .sum()
    )
    if exact_coverage < config.min_exact_coverage:
        raise RuntimeError(
            f"exact market coverage {exact_matches}/{len(relation)}="
            f"{exact_coverage:.2%} below {config.min_exact_coverage:.0%}; "
            "refusing biased execution optimization"
        )

    paths: dict[str, list[tuple]] = {str(i): [] for i in relation["signal_id"]}
    funding: dict[str, list[tuple]] = {}
    for signal_id, *row in path_rows:
        paths[str(signal_id)].append(tuple(row))
    for signal_id, *row in funding_rows:
        funding.setdefault(str(signal_id), []).append(tuple(row))
    complete = 0
    for row in relation.itertuples(index=False):
        bars = paths[str(row.signal_id)]
        if bars and pd.Timestamp(bars[-1][0]).tz_convert("UTC") >= pd.Timestamp(
            row.feature_time
        ) + pd.Timedelta(hours=48) - pd.Timedelta(minutes=5):
            complete += 1
    raw_unique = int(signals["symbol_raw"].nunique())
    canonical_unique = int(signals["symbol"].nunique())
    return (
        paths,
        funding,
        {
            "signals": len(relation),
            "exact_timestamp_symbol_matches": exact_matches,
            "exact_coverage": exact_coverage,
            "entry_price_aligned_within_1e_6": price_aligned,
            "complete_48h_paths": complete,
            "complete_48h_coverage": complete / len(relation) if len(relation) else 0.0,
            "signals_with_funding_rows": len(funding),
            "raw_unique_symbols": raw_unique,
            "canonical_unique_symbols": canonical_unique,
            "canonical_collision_detected": raw_unique != canonical_unique,
            "symbol_normalization": "upper(trim(symbol)) on both sides",
            "entry_price_source": "universe_policy_candidates_v2 (same candidate lineage)",
            "path_source": str(config.market_db) + "::klines_5m",
            "funding_source": str(config.market_db) + "::funding_history",
        },
    )


def _effective_parameters(
    variant: Variant, signal: Any, dev_stats: dict[str, float]
) -> tuple[tuple[float, float, float], tuple[float, float, float], float]:
    vol = float(signal.price_volatility_24h)
    median_vol = dev_stats["median_volatility"]
    scale = float(np.clip(vol / median_vol, 0.75, 1.50)) if median_vol > 0 else 1.0
    offsets = (0.0, 0.03, 0.06)
    if variant.offset_mode == "volatility":
        offsets = (0.0, 0.03 * scale, 0.06 * scale)
    allocations = variant.allocations
    if variant.allocation_mode == "overshoot":
        allocations = (
            (0.10, 0.25, 0.65)
            if float(signal.price_ret_24h) >= 0.40
            else (0.25, 0.35, 0.40)
        )
    elif variant.allocation_mode == "volatility":
        allocations = (
            (0.10, 0.30, 0.60)
            if vol >= dev_stats["volatility_q75"]
            else (0.25, 0.35, 0.40)
        )
    risk_multiplier = 1.0
    if variant.risk_normalized and vol > 0:
        risk_multiplier = float(np.clip(median_vol / vol, 0.50, 1.0))
    return offsets, tuple(a * risk_multiplier for a in allocations), risk_multiplier


def _funding_return(
    fills: list[tuple[pd.Timestamp, float]],
    reductions: list[tuple[pd.Timestamp, float]],
    funding_points: Iterable[tuple],
    exit_time: pd.Timestamp,
) -> float:
    value = 0.0
    for timestamp, rate in funding_points:
        when = pd.Timestamp(timestamp).tz_convert("UTC")
        if when > exit_time:
            break
        active = sum(size for fill_time, size in fills if fill_time < when)
        active -= sum(size for close_time, size in reductions if close_time < when)
        value += float(rate) * max(0.0, active)
    return value


def simulate(
    variant: Variant,
    signal: Any,
    bars: list[tuple],
    funding_points: list[tuple],
    dev_stats: dict[str, float],
) -> dict[str, Any]:
    signal_time = pd.Timestamp(signal.feature_time).tz_convert("UTC")
    offsets, allocations, risk_multiplier = _effective_parameters(
        variant, signal, dev_stats
    )
    triggers = [float(signal.entry_price) * (1.0 + offset) for offset in offsets]
    fills: list[tuple[int, pd.Timestamp, float, float]] = [
        (1, signal_time, float(signal.entry_price), allocations[0])
    ]
    funding_fills = [(signal_time, allocations[0])]
    reductions: list[tuple[pd.Timestamp, float]] = []
    touched: set[int] = set()
    entry_end = signal_time + pd.Timedelta(hours=variant.window_hours)
    exit_deadline = signal_time + pd.Timedelta(
        hours=min(HORIZON_HOURS, variant.time_stop_hours)
    )
    status = "timeout"
    exit_time = exit_deadline
    last_close = float(signal.entry_price)
    realized_gross = 0.0
    partial_done = False
    partial_size = 0.0
    breakeven_armed = False
    previous_close = float(signal.entry_price)
    ambiguous = False
    max_high = float(signal.entry_price)
    min_low = float(signal.entry_price)

    exhaustion = (
        float(signal.funding_change_8h) <= 0.0
        and float(signal.momentum_deceleration_4h) <= 0.0
    )
    for timestamp, high, low, close in bars:
        when = pd.Timestamp(timestamp).tz_convert("UTC")
        if when > exit_deadline:
            break
        high, low, close = float(high), float(low), float(close)
        last_close = close
        max_high = max(max_high, high)
        min_low = min(min_low, low)

        if when <= entry_end and not partial_done:
            for leg in (1, 2):
                if any(item[0] == leg + 1 for item in fills):
                    continue
                if high >= triggers[leg]:
                    touched.add(leg)
                gate_ok = variant.add_gate == "none"
                if variant.add_gate in {
                    "reversal",
                    "exhaustion_reversal",
                    "true_transition",
                }:
                    gate_ok = (
                        leg in touched
                        and close <= triggers[leg] * 0.995
                        and close < previous_close
                    )
                    if variant.add_gate == "exhaustion_reversal":
                        gate_ok = gate_ok and exhaustion
                    elif variant.add_gate == "true_transition":
                        transition_time = getattr(signal, "transition_time", None)
                        gate_ok = (
                            gate_ok
                            and transition_time is not None
                            and when >= pd.Timestamp(transition_time).tz_convert("UTC")
                        )
                if gate_ok and leg in touched:
                    fill_price = triggers[leg] if variant.add_gate == "none" else close
                    fills.append((leg + 1, when, fill_price, allocations[leg]))
                    funding_fills.append((when, allocations[leg]))

        filled_size = sum(item[3] for item in fills)
        average = sum(item[2] * item[3] for item in fills) / filled_size
        target_price = average * (1.0 - TARGET)
        hard_stop_price = average * (1.0 + HARD_STOP)
        stop_price = (
            min(hard_stop_price, average) if breakeven_armed else hard_stop_price
        )
        stop_touched = high >= stop_price
        target_touched = low <= target_price
        if stop_touched and target_touched:
            status = "stop_ambiguous"
            ambiguous = True
            exit_time = when
            break
        if stop_touched:
            status = "breakeven_stop" if breakeven_armed else "stop"
            exit_time = when
            break
        if target_touched:
            status = "target"
            exit_time = when
            break
        # Newly observed favourable excursion only arms management for the
        # next bar. This keeps unknown intrabar order conservatively stop-first.
        partial_price = average * 0.90
        if low <= partial_price:
            breakeven_armed = variant.breakeven_after_10 or breakeven_armed
            if variant.partial_at_10_fraction and not partial_done:
                partial_size = filled_size * variant.partial_at_10_fraction
                realized_gross += 0.10 * partial_size
                reductions.append((when, partial_size))
                partial_done = True
        previous_close = close

    filled_size = sum(item[3] for item in fills)
    average = sum(item[2] * item[3] for item in fills) / filled_size
    remaining = max(0.0, filled_size - partial_size)
    if status == "target":
        realized_gross += TARGET * remaining
    elif status in {"stop", "stop_ambiguous"}:
        realized_gross -= HARD_STOP * remaining
    elif status == "breakeven_stop":
        realized_gross += 0.0
    else:
        realized_gross += ((average - last_close) / average) * remaining
    trading_cost = ROUND_TRIP_COST * filled_size
    funding_return = _funding_return(
        funding_fills, reductions, funding_points, exit_time
    )
    actual_return = realized_gross - trading_cost + funding_return
    conservative_return = (
        (TARGET if status == "target" else -HARD_STOP) * filled_size
        - trading_cost
        + funding_return
    )
    complete_path = bool(bars) and pd.Timestamp(bars[-1][0]).tz_convert("UTC") >= (
        signal_time + pd.Timedelta(hours=HORIZON_HOURS) - pd.Timedelta(minutes=5)
    )
    return {
        "variant_id": variant.variant_id,
        "family": variant.family,
        "signal_id": signal.signal_id,
        "symbol": signal.symbol,
        "signal_time": signal_time,
        "exit_time": exit_time,
        "fold": int(signal.fold),
        "status": status,
        "target_hit": status == "target",
        "filled_legs": len(fills),
        "capital_deployed": filled_size,
        "risk_multiplier": risk_multiplier,
        "average_entry": average,
        "actual_return": actual_return,
        "conservative_return": conservative_return,
        "funding_return": funding_return,
        "complete_path": complete_path,
        "ambiguous": ambiguous,
        "mae": (max_high - average) / average,
        "mfe": (average - min_low) / average,
    }


def evaluate(
    signals: pd.DataFrame,
    selected_variants: Iterable[Variant],
    paths: dict[str, list[tuple]],
    funding: dict[str, list[tuple]],
    dev_stats: dict[str, float],
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for signal in signals.itertuples(index=False):
        for variant in selected_variants:
            rows.append(
                simulate(
                    variant,
                    signal,
                    paths.get(str(signal.signal_id), []),
                    funding.get(str(signal.signal_id), []),
                    dev_stats,
                )
            )
    return pd.DataFrame(rows)


def max_drawdown(returns: Iterable[float]) -> float:
    equity = peak = 1.0
    result = 0.0
    for value in returns:
        equity *= max(0.0, 1.0 + float(value))
        peak = max(peak, equity)
        result = max(result, (peak - equity) / peak)
    return result


def summarize(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {"signals": 0}
    ordered = frame.sort_values("signal_time")
    return {
        "signals": len(frame),
        "complete_paths": int(frame["complete_path"].sum()),
        "target_rate": float(frame["target_hit"].mean()),
        "stop_rate": float(frame["status"].isin(["stop", "stop_ambiguous"]).mean()),
        "timeout_rate": float(frame["status"].eq("timeout").mean()),
        "ambiguous_rate": float(frame["ambiguous"].mean()),
        "entry2_fill_rate": float(frame["filled_legs"].ge(2).mean()),
        "entry3_fill_rate": float(frame["filled_legs"].ge(3).mean()),
        "mean_capital_deployed": float(frame["capital_deployed"].mean()),
        "total_capital_deployed": float(frame["capital_deployed"].sum()),
        "actual_ev_per_signal": float(frame["actual_return"].mean()),
        "actual_return_per_deployed_capital": float(
            frame["actual_return"].sum() / frame["capital_deployed"].sum()
        ),
        "conservative_ev_per_signal": float(frame["conservative_return"].mean()),
        "sequential_compounded_mdd": max_drawdown(ordered["actual_return"]),
        "funding_ev": float(frame["funding_return"].mean()),
    }


def _exact_sign_flip_p(values: np.ndarray) -> float:
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return 1.0
    observed = float(values.mean())
    if observed <= 0:
        return 1.0
    if len(values) <= 18:
        means = []
        for signs in itertools.product((-1.0, 1.0), repeat=len(values)):
            means.append(float(np.mean(values * np.asarray(signs))))
        return (sum(item >= observed - 1e-15 for item in means) + 1) / (len(means) + 1)
    rng = np.random.default_rng(20260914)
    draws = rng.choice((-1.0, 1.0), size=(50_000, len(values)))
    means = (draws * values).mean(axis=1)
    return float((np.sum(means >= observed) + 1) / (len(means) + 1))


def _holm_adjust(pairs: list[tuple[str, float]]) -> dict[str, float]:
    ordered = sorted(pairs, key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for rank, (name, p_value) in enumerate(ordered):
        running = max(running, min(1.0, (total - rank) * p_value))
        adjusted[name] = running
    return adjusted


def development_table(events: pd.DataFrame) -> pd.DataFrame:
    baseline = events[events["variant_id"].eq(BASELINE_ID)][
        ["signal_id", "actual_return"]
    ].rename(columns={"actual_return": "baseline_return"})
    rows: list[dict[str, Any]] = []
    p_values: list[tuple[str, float]] = []
    for variant_id, frame in events.groupby("variant_id"):
        merged = frame.merge(baseline, on="signal_id", validate="one_to_one")
        merged["delta"] = merged["actual_return"] - merged["baseline_return"]
        fold_deltas = merged.groupby("fold")["delta"].mean()
        weekly = (
            merged.assign(week=merged["signal_time"].dt.strftime("%G-W%V"))
            .groupby("week")["delta"]
            .mean()
        )
        p_value = (
            1.0 if variant_id == BASELINE_ID else _exact_sign_flip_p(weekly.to_numpy())
        )
        p_values.append((variant_id, p_value))
        summary = summarize(frame)
        rows.append(
            {
                "variant_id": variant_id,
                "family": str(frame["family"].iloc[0]),
                **summary,
                "mean_delta_vs_baseline": float(merged["delta"].mean()),
                "mean_fold_delta": float(fold_deltas.mean()),
                "worst_fold_delta": float(fold_deltas.min()),
                "positive_delta_folds": int((fold_deltas > 0).sum()),
                "fold_deltas": json.dumps(fold_deltas.to_dict()),
                "weekly_signflip_p_one_sided": p_value,
            }
        )
    adjusted = _holm_adjust([item for item in p_values if item[0] != BASELINE_ID])
    table = pd.DataFrame(rows)
    table["holm_adjusted_p"] = table["variant_id"].map(adjusted).fillna(1.0)
    table["coverage_eligible"] = (
        table["complete_paths"].ge(int(events["signal_id"].nunique() * 0.95))
        & table["signals"].ge(100)
        & table["mean_capital_deployed"].ge(0.15)
    )
    table["robust_score"] = (
        table["mean_delta_vs_baseline"]
        + 0.50 * table["worst_fold_delta"]
        - 0.20 * table["sequential_compounded_mdd"]
    )
    table["multiplicity_pass_10pct"] = table["holm_adjusted_p"].le(0.10)
    return table.sort_values(
        ["coverage_eligible", "robust_score", "mean_delta_vs_baseline"],
        ascending=False,
    ).reset_index(drop=True)


def paired_holdout(frame: pd.DataFrame, candidate_id: str) -> dict[str, Any]:
    base = frame[frame["variant_id"].eq(BASELINE_ID)][
        ["signal_id", "actual_return"]
    ].rename(columns={"actual_return": "baseline"})
    candidate = frame[frame["variant_id"].eq(candidate_id)][
        ["signal_id", "actual_return"]
    ].rename(columns={"actual_return": "candidate"})
    paired = candidate.merge(base, on="signal_id", validate="one_to_one")
    delta = (paired["candidate"] - paired["baseline"]).to_numpy()
    rng = np.random.default_rng(20260914)
    boot = rng.choice(delta, size=(20_000, len(delta)), replace=True).mean(axis=1)
    return {
        "signals": len(delta),
        "mean_actual_ev_delta": float(delta.mean()),
        "median_delta": float(np.median(delta)),
        "positive_delta_rate": float((delta > 0).mean()),
        "paired_bootstrap_95": [
            float(np.quantile(boot, 0.025)),
            float(np.quantile(boot, 0.975)),
        ],
        "one_sided_sign_flip_p": _exact_sign_flip_p(delta),
    }


def run(config: Config) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    signals = load_frozen_signals(config)
    development = signals[signals["fold"].isin(config.development_folds)].copy()
    holdout = signals[signals["fold"].eq(config.holdout_fold)].copy()
    if len(development) < 100 or len(holdout) < 25:
        raise RuntimeError("development/holdout coverage floor not met")
    dev_stats = {
        "median_volatility": float(development["price_volatility_24h"].median()),
        "volatility_q75": float(development["price_volatility_24h"].quantile(0.75)),
    }

    dev_paths, dev_funding, dev_coverage = _load_paths(config, development)
    all_variants = variants()
    dev_events = evaluate(development, all_variants, dev_paths, dev_funding, dev_stats)
    dev_table = development_table(dev_events)
    candidates = dev_table[
        dev_table["coverage_eligible"] & dev_table["variant_id"].ne(BASELINE_ID)
    ]
    if candidates.empty:
        raise RuntimeError("no execution candidate met development coverage floors")
    winner_id = str(candidates.iloc[0]["variant_id"])
    winner = next(item for item in all_variants if item.variant_id == winner_id)
    lock_payload = {
        "artifact": "forward48_execution_risk_selection_lock_v1",
        "written_before_holdout_paths_loaded": True,
        "generated_at": datetime.now(timezone.utc),
        "timing_source_sha256": _sha256(config.timing_oos_csv),
        "baseline": asdict(all_variants[0]),
        "selected_candidate": asdict(winner),
        "variants_tested": len(all_variants),
        "development_folds": list(config.development_folds),
        "holdout_fold": config.holdout_fold,
        "development_rows": len(development),
        "selection_rule": (
            "highest robust_score among non-baseline coverage-eligible variants; "
            "Holm p is a gate report, not silently optimized"
        ),
        "development_winner": candidates.iloc[0].to_dict(),
        "dev_stats_frozen_for_holdout": dev_stats,
    }
    lock_path = config.output_dir / "selection_lock.json"
    lock_path.write_text(
        json.dumps(lock_payload, default=_json_default, indent=2), encoding="utf-8"
    )
    lock_sha = _sha256(lock_path)

    # Holdout outcomes are accessed only after the selection lock is durable.
    holdout_paths, holdout_funding, holdout_coverage = _load_paths(config, holdout)
    holdout_events = evaluate(
        holdout, [all_variants[0], winner], holdout_paths, holdout_funding, dev_stats
    )
    dev_summaries = {
        variant_id: summarize(frame)
        for variant_id, frame in dev_events.groupby("variant_id")
    }
    holdout_summaries = {
        variant_id: summarize(frame)
        for variant_id, frame in holdout_events.groupby("variant_id")
    }
    fold_stability = {
        variant_id: {
            str(int(fold)): summarize(part) for fold, part in frame.groupby("fold")
        }
        for variant_id, frame in dev_events.groupby("variant_id")
        if variant_id in {BASELINE_ID, winner_id}
    }
    paired = paired_holdout(holdout_events, winner_id)
    winner_dev_row = dev_table[dev_table["variant_id"].eq(winner_id)].iloc[0]
    promotion = bool(
        winner_dev_row["multiplicity_pass_10pct"]
        and paired["paired_bootstrap_95"][0] > 0
        and holdout_summaries[winner_id]["actual_ev_per_signal"] > 0
        and holdout_summaries[winner_id]["conservative_ev_per_signal"] > 0
    )
    report = {
        "artifact": "forward48_execution_risk_search_v1",
        "generated_at": datetime.now(timezone.utc),
        "status": "research_only_not_live",
        "live_configuration_changed": False,
        "contract": {
            "signal_and_timing": "frozen distribution_v2_3 timing challenger",
            "target_from_current_weighted_average": TARGET,
            "hard_stop_from_current_weighted_average": HARD_STOP,
            "maximum_horizon_hours": HORIZON_HOURS,
            "same_bar": "stop_first",
            "round_trip_fee_slippage": ROUND_TRIP_COST,
            "funding": "realized funding while remaining filled capital is active",
        },
        "protocol": {
            "development_folds": list(config.development_folds),
            "chronological_execution_holdout_fold": config.holdout_fold,
            "holdout_unused_for_execution_selection": True,
            "not_sealed_end_to_end": True,
            "reason": "timing policy had previously been selected using all historical OOS folds",
            "august_used_for_selection": False,
            "variant_count_including_baseline": len(all_variants),
            "multiplicity_control": "one-sided weekly paired sign-flip, Holm across 15 alternatives",
            "coverage_floor": config.min_exact_coverage,
        },
        "coverage": {"development": dev_coverage, "holdout": holdout_coverage},
        "selection_lock_sha256": lock_sha,
        "selected_candidate": asdict(winner),
        "development_winner_multiplicity_pass": bool(
            winner_dev_row["multiplicity_pass_10pct"]
        ),
        "development": dev_summaries,
        "development_fold_stability": fold_stability,
        "holdout": holdout_summaries,
        "holdout_paired": paired,
        "decision": {
            "promote": promotion,
            "reason": (
                "requires development Holm pass and positive lower paired holdout CI, "
                "actual EV and conservative EV"
            ),
        },
        "research_mapping": {
            "01": "funding high alone can precede squeeze; add only after reversal/exhaustion confirmation",
            "05": "multi-horizon decay motivates 12/24/36h time-stop variants while retaining main -20% target",
            "06": "TP8/SL4/leverage ROI is a different contract and is excluded; negative caution only",
            "07": "funding exhaustion plus volatility/momentum transition motivates conditional adds and vol-scaled offsets",
        },
    }
    dev_events.to_csv(config.output_dir / "development_events.csv", index=False)
    holdout_events.to_csv(config.output_dir / "holdout_events.csv", index=False)
    dev_table.to_csv(config.output_dir / "development_variant_table.csv", index=False)
    (config.output_dir / "report.json").write_text(
        json.dumps(report, default=_json_default, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    report = run(Config())
    print(
        json.dumps(
            {
                "selected_candidate": report["selected_candidate"],
                "coverage": report["coverage"],
                "holdout": report["holdout"],
                "paired": report["holdout_paired"],
                "decision": report["decision"],
            },
            default=_json_default,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
