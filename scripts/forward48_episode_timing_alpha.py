"""Causal episode-timing alpha search around the frozen 48h challenger.

The model probabilities and candidate universe are immutable inputs.  Folds
1-3 of the already walk-forward historical OOS stream are development data.
The selected rule is written to a lock before fold 4 is loaded and evaluated.
August is recycled data and is used only as a rejection/audit set.

This runner is research-only and never edits live or frozen configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterable

import duckdb
import joblib
import numpy as np
import pandas as pd

from dao_vang.experiments.train_distribution_v2 import (
    SERVING_FEATURE_COLS,
    _predict_calibrated,
)

try:
    from forward48_scalein_backtest import (
        BUILT_INS,
        _evaluate_templates,
        _load_market_paths,
        _summarize,
    )
    from forward48_scalein_backtest import Config as ExecutionConfig
except ImportError:  # pragma: no cover - package import in tests
    from scripts.forward48_scalein_backtest import (
        BUILT_INS,
        _evaluate_templates,
        _load_market_paths,
        _summarize,
    )
    from scripts.forward48_scalein_backtest import Config as ExecutionConfig


TARGET = 0.20
STOP = 0.16
COST = 0.002
BREAK_EVEN = (STOP + COST) / (TARGET + STOP)
EXPECTED_FROZEN_LOCK = (
    "ba8ccac68fb824a952b60c998d5b0ff86977119d85692626adde7fb9f7371305"
)
EXTRA_COLUMNS = (
    "price_ret_4h",
    "price_volatility_24h",
    "volume_percentile_24h",
    "momentum_deceleration_4h",
    "funding_rate_raw",
    "funding_percentile_30d",
    "funding_change_8h",
    "funding_persistence_7d",
    "global_ls_ratio",
    "top_ls_ratio",
)


@dataclass(frozen=True)
class TimingRule:
    rule_id: str
    family: str
    rationale: str
    min_age_hours: float = 4.0
    confirmations: int = 2
    min_peak_pump: float = 0.30
    probability_tolerance: float = 0.10
    min_distance_from_high: float = 0.0
    min_pump_return_pullback: float = 0.0
    max_pump_velocity: float | None = None
    max_pump_acceleration: float | None = None
    min_probability_peak_drop: float = 0.0
    max_probability_velocity: float | None = None
    max_momentum_deceleration_4h: float | None = None
    min_funding_percentile_30d: float | None = None
    min_funding_persistence_7d: float | None = None
    max_funding_change_8h: float | None = None
    require_funding_change_decelerating: bool = False
    min_funding_rate_raw: float | None = None
    max_ls_spread: float | None = None
    episode_gap_hours: int = 6
    cooldown_hours: int = 24
    selection_eligible: bool = True


@dataclass(frozen=True)
class Config:
    frozen_config: Path = Path(
        "configs/distribution_v2_3_research_48h_timing_compact.yaml"
    )
    source_lock: Path = Path(
        "artifacts/forward48_timing_20260913/forward48_timing_lock.json"
    )
    historical_oos: Path = Path(
        "artifacts/forward48_timing_20260913/forward48_timing_historical_oos.csv"
    )
    historical_db: Path = Path("artifacts/universe_policy_v2_48h.duckdb")
    model_path: Path = Path(
        "artifacts/forward48_timing_20260913/forward48_timing_research_model.joblib"
    )
    live_db: Path = Path("data_live/live.duckdb")
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    output_dir: Path = Path("artifacts/forward48_episode_timing_alpha_20260914")
    dev_folds: tuple[int, ...] = (1, 2, 3)
    holdout_fold: int = 4
    min_dev_signals: int = 60
    min_dev_signals_per_fold: int = 12
    min_dev_episode_recall: float = 0.08
    min_coverage_vs_baseline: float = 0.50
    familywise_alpha: float = 0.05
    august_start: str = "2026-08-01T00:00:00+07:00"
    august_end: str = "2026-08-27T00:00:00+07:00"
    min_future_bars: int = 552


def _default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    raise TypeError(type(value).__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _wilson(successes: int, trials: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if trials <= 0:
        return 0.0, 0.0
    p = successes / trials
    denominator = 1.0 + z * z / trials
    centre = p + z * z / (2.0 * trials)
    radius = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * trials)) / trials)
    return (centre - radius) / denominator, (centre + radius) / denominator


def _episode_ids(frame: pd.DataFrame, gap_hours: int) -> pd.Series:
    result = pd.Series(index=frame.index, dtype="object")
    group_columns = ["fold", "symbol"] if "fold" in frame.columns else ["symbol"]
    for key, indices in frame.groupby(group_columns, sort=False).groups.items():
        ordered = frame.loc[indices].sort_values("feature_time")
        reset = ordered["feature_time"].diff().gt(pd.Timedelta(hours=gap_hours))
        local = reset.fillna(True).cumsum().astype(int)
        prefix = key if isinstance(key, tuple) else (key,)
        result.loc[ordered.index] = [
            ":".join([*(str(item) for item in prefix), str(number)])
            for number in local
        ]
    return result


def _load_historical_partition(config: Config, folds: Iterable[int]) -> tuple[pd.DataFrame, dict[str, Any]]:
    folds = tuple(int(item) for item in folds)
    csv_path = str(config.historical_oos.resolve()).replace("\\", "/").replace("'", "''")
    db_path = str(config.historical_db.resolve()).replace("\\", "/").replace("'", "''")
    placeholders = ",".join("?" for _ in folds)
    extra = ", ".join(f"h.{column}" for column in EXTRA_COLUMNS)
    conn = duckdb.connect()
    conn.execute(f"ATTACH '{db_path}' AS hist (READ_ONLY)")
    try:
        frame = conn.execute(
            f"""
            SELECT o.*, {extra}, h.entry_price
            FROM read_csv_auto('{csv_path}', header=true) o
            LEFT JOIN hist.main.universe_policy_candidates_v2 h
              ON h.symbol=o.symbol AND h.feature_time=o.feature_time
            WHERE CAST(o.fold AS INTEGER) IN ({placeholders})
            ORDER BY o.feature_time, o.symbol
            """,
            list(folds),
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["fold"] = frame["fold"].astype(int)
    frame["label_value"] = frame["label_value"].astype("int8")
    duplicates = int(frame.duplicated(["symbol", "feature_time", "fold"]).sum())
    coverage = float(frame["entry_price"].notna().mean()) if len(frame) else 0.0
    if duplicates:
        raise RuntimeError(f"historical enrichment created {duplicates} duplicate keys")
    if coverage < 0.999:
        raise RuntimeError(f"historical PIT enrichment coverage is only {coverage:.2%}")
    return frame, {
        "rows": len(frame),
        "folds": list(folds),
        "unique_keys": len(frame),
        "join_coverage": coverage,
        "null_rates": {
            column: float(frame[column].isna().mean()) for column in EXTRA_COLUMNS
        },
    }


def rule_catalog() -> list[TimingRule]:
    baseline = TimingRule(
        "frozen_baseline", "baseline", "Frozen timing: age4 + 2 confirmations + pump peak30%."
    )
    rules = [baseline]
    for age in (2.0, 6.0, 8.0, 12.0):
        rules.append(replace(baseline, rule_id=f"age_{int(age)}h", family="age", min_age_hours=age, rationale="Pump-age bin; wait for a more mature episode."))
    for value in (0.02, 0.04, 0.06):
        rules.append(replace(baseline, rule_id=f"high_drawdown_{int(value*100)}", family="price_reversal", min_distance_from_high=value, rationale="Require a causal pullback from the rolling 24h high."))
        rules.append(replace(baseline, rule_id=f"pump_pullback_{int(value*100)}", family="price_reversal", min_pump_return_pullback=value, rationale="Require current 24h return to fade from its episode peak."))
    for value in (0.0, -0.01, -0.02):
        tag = str(abs(int(value * 100))).replace("-", "")
        rules.append(replace(baseline, rule_id=f"pump_velocity_le_m{tag}", family="price_transition", max_pump_velocity=value, rationale="Require 24h-return velocity to stop or turn negative."))
    for value in (0.0, -0.01):
        tag = str(abs(int(value * 100)))
        rules.append(replace(baseline, rule_id=f"pump_acceleration_le_m{tag}", family="price_transition", max_pump_acceleration=value, rationale="Require pump velocity to decelerate versus the prior observation."))
    for value in (0.03, 0.06, 0.10):
        rules.append(replace(baseline, rule_id=f"prob_peak_drop_{int(value*100)}", family="probability_transition", min_probability_peak_drop=value, rationale="Wait for calibrated probability to retreat from its causal episode peak."))
    for value in (0.0, -0.03):
        tag = str(abs(int(value * 100)))
        rules.append(replace(baseline, rule_id=f"prob_velocity_le_m{tag}", family="probability_transition", max_probability_velocity=value, rationale="Require calibrated probability to stop rising."))
    for value in (0.0, -0.02, -0.05):
        tag = str(abs(int(value * 100)))
        rules.append(replace(baseline, rule_id=f"momentum4h_le_m{tag}", family="multi_tf_exhaustion", max_momentum_deceleration_4h=value, rationale="Report05: use the available PIT 4h momentum-deceleration feature."))
    rules.extend(
        [
            replace(baseline, rule_id="confirmations_3", family="confirmation", confirmations=3, rationale="Require a third contiguous model confirmation."),
            replace(baseline, rule_id="gap_3h", family="reset", episode_gap_hours=3, rationale="Reset episode state after a shorter observation gap."),
            replace(baseline, rule_id="gap_12h", family="reset", episode_gap_hours=12, rationale="Preserve episode state across longer sparse stretches."),
            replace(baseline, rule_id="cooldown_36h", family="cooldown", cooldown_hours=36, rationale="Reduce symbol-level clustering."),
            replace(baseline, rule_id="cooldown_48h", family="cooldown", cooldown_hours=48, rationale="Allow at most one entry per label horizon per symbol."),
            replace(baseline, rule_id="drawdown2_momentum0", family="combined_exhaustion", min_distance_from_high=0.02, max_momentum_deceleration_4h=0.0, rationale="Report01/05: pullback plus momentum exhaustion."),
            replace(baseline, rule_id="pumpfade2_momentum0", family="combined_exhaustion", min_pump_return_pullback=0.02, max_momentum_deceleration_4h=0.0, rationale="Episode fade plus the available multi-TF exhaustion confirmation."),
            replace(baseline, rule_id="probdrop3_momentum0", family="combined_exhaustion", min_probability_peak_drop=0.03, max_momentum_deceleration_4h=0.0, rationale="Model confidence fade plus price-momentum exhaustion."),
            replace(baseline, rule_id="funding_high_only_control", family="negative_control", min_funding_percentile_30d=0.80, selection_eligible=False, rationale="Report01 negative control: high funding alone can be continued squeeze."),
            replace(baseline, rule_id="funding_raw_high_control", family="negative_control", min_funding_rate_raw=0.0005, selection_eligible=False, rationale="Report01 negative control: never select raw funding spike alone."),
            replace(baseline, rule_id="funding_exhaustion_reversal", family="funding_transition", min_funding_percentile_30d=0.80, min_funding_persistence_7d=0.0, max_funding_change_8h=0.0, rationale="Report07 revised hypothesis: funding was high/persistent and 8h change has reversed."),
            replace(baseline, rule_id="funding_exhaustion_decelerating", family="funding_transition", min_funding_percentile_30d=0.80, min_funding_persistence_7d=0.0, require_funding_change_decelerating=True, rationale="Funding is elevated/persistent and its 8h change has stopped accelerating."),
            replace(baseline, rule_id="ls_spread_control", family="negative_control", max_ls_spread=0.0, selection_eligible=False, rationale="Report07 negative control for long/short positioning."),
        ]
    )
    ids = [rule.rule_id for rule in rules]
    if len(ids) != len(set(ids)):
        raise AssertionError("duplicate timing rule ids")
    return rules


def select_signals(frame: pd.DataFrame, rule: TimingRule) -> pd.DataFrame:
    work = frame.copy()
    work["search_episode_id"] = _episode_ids(work, rule.episode_gap_hours)
    selected: list[int] = []
    for _, episode in work.groupby("search_episode_id", sort=False):
        episode = episode.sort_values("feature_time")
        start = pd.Timestamp(episode["feature_time"].iloc[0])
        armed = False
        confirmations = 0
        confirmed = False
        probability_peak = -math.inf
        pump_peak = -math.inf
        previous_time: pd.Timestamp | None = None
        previous_pump: float | None = None
        previous_pump_velocity: float | None = None
        previous_probability: float | None = None
        previous_funding_change: float | None = None
        for index, row in episode.iterrows():
            when = pd.Timestamp(row["feature_time"])
            probability = float(row["probability"])
            threshold = float(row["threshold"])
            pump = float(row["price_ret_24h"])
            dt = None if previous_time is None else (when - previous_time).total_seconds() / 3600.0
            contiguous = dt is None or dt <= 1.5
            above = probability >= threshold
            confirmations = confirmations + 1 if above and contiguous else int(above)
            confirmed = confirmed or confirmations >= rule.confirmations
            armed = armed or above
            if armed:
                probability_peak = max(probability_peak, probability)
                pump_peak = max(pump_peak, pump)
            pump_velocity = None if not dt or previous_pump is None else (pump - previous_pump) / dt
            probability_velocity = None if not dt or previous_probability is None else (probability - previous_probability) / dt
            pump_acceleration = None
            if pump_velocity is not None and previous_pump_velocity is not None:
                pump_acceleration = (pump_velocity - previous_pump_velocity) / max(dt or 1.0, 1e-9)
            funding_change = row.get("funding_change_8h")
            funding_decelerating = (
                pd.notna(funding_change)
                and previous_funding_change is not None
                and float(funding_change) <= previous_funding_change
            )
            age = (when - start).total_seconds() / 3600.0
            checks = [
                armed,
                confirmed,
                pump_peak >= rule.min_peak_pump,
                age >= rule.min_age_hours,
                probability >= max(0.0, threshold - rule.probability_tolerance),
                float(row["distance_from_high_24h"]) <= -rule.min_distance_from_high,
                pump_peak - pump >= rule.min_pump_return_pullback,
                rule.max_pump_velocity is None or (pump_velocity is not None and pump_velocity <= rule.max_pump_velocity),
                rule.max_pump_acceleration is None or (pump_acceleration is not None and pump_acceleration <= rule.max_pump_acceleration),
                probability_peak - probability >= rule.min_probability_peak_drop,
                rule.max_probability_velocity is None or (probability_velocity is not None and probability_velocity <= rule.max_probability_velocity),
                rule.max_momentum_deceleration_4h is None or (pd.notna(row.get("momentum_deceleration_4h")) and float(row["momentum_deceleration_4h"]) <= rule.max_momentum_deceleration_4h),
                rule.min_funding_percentile_30d is None or (pd.notna(row.get("funding_percentile_30d")) and float(row["funding_percentile_30d"]) >= rule.min_funding_percentile_30d),
                rule.min_funding_persistence_7d is None or (pd.notna(row.get("funding_persistence_7d")) and float(row["funding_persistence_7d"]) >= rule.min_funding_persistence_7d),
                rule.max_funding_change_8h is None or (pd.notna(funding_change) and float(funding_change) <= rule.max_funding_change_8h),
                not rule.require_funding_change_decelerating or funding_decelerating,
                rule.min_funding_rate_raw is None or (pd.notna(row.get("funding_rate_raw")) and float(row["funding_rate_raw"]) >= rule.min_funding_rate_raw),
                rule.max_ls_spread is None or (pd.notna(row.get("top_ls_ratio")) and pd.notna(row.get("global_ls_ratio")) and float(row["top_ls_ratio"] - row["global_ls_ratio"]) <= rule.max_ls_spread),
            ]
            if all(checks):
                selected.append(int(index))
                break
            previous_time = when
            previous_pump = pump
            previous_probability = probability
            if pump_velocity is not None:
                previous_pump_velocity = pump_velocity
            if pd.notna(funding_change):
                previous_funding_change = float(funding_change)
    signals = work.loc[selected].sort_values(["feature_time", "symbol"]).copy()
    keep: list[int] = []
    last: dict[str, pd.Timestamp] = {}
    for index, row in signals.iterrows():
        symbol = str(row["symbol"])
        when = pd.Timestamp(row["feature_time"])
        if symbol not in last or when >= last[symbol] + pd.Timedelta(hours=rule.cooldown_hours):
            keep.append(int(index))
            last[symbol] = when
    return signals.loc[keep]


def metrics(frame: pd.DataFrame, rule: TimingRule, z: float = 1.959963984540054) -> dict[str, Any]:
    signals = select_signals(frame, rule)
    evaluable = signals[signals["label_value"].notna()]
    n = len(evaluable)
    tp = int(evaluable["label_value"].eq(1).sum())
    precision = tp / n if n else 0.0
    canonical = frame.copy()
    canonical["canonical_episode_id"] = _episode_ids(canonical, 6)
    positive = set(canonical.loc[canonical["label_value"].eq(1), "canonical_episode_id"])
    caught_keys = set(zip(evaluable.loc[evaluable["label_value"].eq(1), "symbol"], evaluable.loc[evaluable["label_value"].eq(1), "feature_time"]))
    lookup = dict(zip(zip(canonical["symbol"], canonical["feature_time"]), canonical["canonical_episode_id"]))
    caught = {lookup[key] for key in caught_keys if key in lookup}
    lower, upper = _wilson(tp, n, z)
    return {
        "signals": n,
        "true_positives": tp,
        "precision": precision,
        "wilson_lower": lower,
        "wilson_upper": upper,
        "positive_episodes": len(positive),
        "caught_positive_episodes": len(caught & positive),
        "episode_recall": len(caught & positive) / len(positive) if positive else 0.0,
        "conservative_ev": precision * TARGET - (1.0 - precision) * STOP - COST if n else None,
    }


def _evaluate_grid(dev: pd.DataFrame, rules: list[TimingRule], config: Config) -> tuple[TimingRule, pd.DataFrame, dict[str, Any]]:
    folds = sorted(config.dev_folds)
    tested = sum(rule.selection_eligible for rule in rules)
    adjusted_z = NormalDist().inv_cdf(1.0 - config.familywise_alpha / (2.0 * tested))
    baseline = next(rule for rule in rules if rule.rule_id == "frozen_baseline")
    baseline_metrics = metrics(dev, baseline)
    rows: list[dict[str, Any]] = []
    for rule in rules:
        aggregate = metrics(dev, rule)
        adjusted = metrics(dev, rule, adjusted_z)
        per_fold = {fold: metrics(dev[dev["fold"].eq(fold)], rule) for fold in folds}
        fold_evs = np.asarray([
            per_fold[fold]["conservative_ev"] if per_fold[fold]["conservative_ev"] is not None else -(STOP + COST)
            for fold in folds
        ])
        fold_signals = [per_fold[fold]["signals"] for fold in folds]
        coverage_ratio = aggregate["signals"] / baseline_metrics["signals"] if baseline_metrics["signals"] else 0.0
        eligible = (
            rule.selection_eligible
            and aggregate["signals"] >= config.min_dev_signals
            and min(fold_signals, default=0) >= config.min_dev_signals_per_fold
            and aggregate["episode_recall"] >= config.min_dev_episode_recall
            and coverage_ratio >= config.min_coverage_vs_baseline
        )
        rows.append({
            "rule_id": rule.rule_id,
            "family": rule.family,
            "rule": json.dumps(asdict(rule), sort_keys=True),
            **aggregate,
            "bonferroni_wilson_lower": adjusted["wilson_lower"],
            "eligible": eligible,
            "coverage_vs_baseline": coverage_ratio,
            "mean_fold_ev": float(fold_evs.mean()),
            "worst_fold_ev": float(fold_evs.min()),
            "fold_ev_std": float(fold_evs.std()),
            "positive_ev_folds": int((fold_evs > 0).sum()),
            "fold_signals": json.dumps(fold_signals),
            "fold_precisions": json.dumps([per_fold[fold]["precision"] for fold in folds]),
            "fold_evs": json.dumps(fold_evs.tolist()),
        })
    grid = pd.DataFrame(rows)
    pool = grid[grid["eligible"]]
    if pool.empty:
        winner = baseline
        fallback = True
    else:
        selected = pool.sort_values(
            ["bonferroni_wilson_lower", "worst_fold_ev", "episode_recall", "signals"],
            ascending=False,
        ).iloc[0]
        winner = next(rule for rule in rules if rule.rule_id == selected["rule_id"])
        fallback = False
    audit = {
        "tested_selection_eligible_hypotheses": tested,
        "familywise_alpha": config.familywise_alpha,
        "bonferroni_two_sided_z": adjusted_z,
        "coverage_floor": {
            "minimum_total_signals": config.min_dev_signals,
            "minimum_signals_each_fold": config.min_dev_signals_per_fold,
            "minimum_episode_recall": config.min_dev_episode_recall,
            "minimum_coverage_vs_baseline": config.min_coverage_vs_baseline,
        },
        "fallback_to_baseline": fallback,
        "baseline": baseline_metrics,
    }
    return winner, grid, audit


def _compact_actual_path(signals: pd.DataFrame, config: Config, prefix: str) -> dict[str, Any]:
    if signals.empty:
        return {"available": False, "reason": "no signals", "signals": 0}
    work = signals[["symbol", "feature_time", "entry_price", "probability", "fold"]].copy().reset_index(drop=True)
    work["signal_id"] = [f"{prefix}-{index:04d}" for index in range(len(work))]
    execution = ExecutionConfig(market_db=config.market_db)
    try:
        paths, funding = _load_market_paths(execution, work)
        source_errors = 0
    except duckdb.Error:
        # One broken external per-symbol parquet must not invalidate every path.
        paths, funding = {}, {}
        source_errors = 0
        for index in work.index:
            try:
                local_paths, local_funding = _load_market_paths(
                    execution, work.loc[[index]]
                )
            except duckdb.Error:
                source_errors += 1
                continue
            paths.update(local_paths)
            funding.update(local_funding)
    compact = next(item for item in BUILT_INS if item.template_id == "compact_0_3_6")
    events = _evaluate_templates(work, [compact], paths, funding, execution, prefix)
    complete = int(events["complete_path"].sum()) if len(events) else 0
    coverage = complete / len(work) if len(work) else 0.0
    if coverage < 0.80:
        return {
            "available": False,
            "reason": "complete 5m path coverage below 80%; EV would be selection-biased",
            "signals": len(work),
            "complete_paths": complete,
            "coverage": coverage,
            "source_errors": source_errors,
        }
    summary = _summarize(events)
    return {
        "available": True,
        "coverage": coverage,
        "source_errors": source_errors,
        "summary": summary,
    }


def _score_august(config: Config, winner: TimingRule, baseline: TimingRule) -> dict[str, Any]:
    import sys

    scripts_dir = str(Path(__file__).resolve().parent)
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    from forward48_timing_evaluate_locked import _load_features, _load_outcomes

    source_lock = json.loads(config.source_lock.read_text(encoding="utf-8"))
    if _sha256(config.model_path) != source_lock["model_sha256"]:
        raise RuntimeError("research model hash does not match frozen timing lock")
    bundle = joblib.load(config.model_path)
    features, feature_coverage = _load_features(
        config.live_db, config.august_start, config.august_end
    )
    raw, probability = _predict_calibrated(
        bundle["model"], bundle["calibrator"], features, list(SERVING_FEATURE_COLS)
    )
    features["raw_probability"] = raw
    features["probability"] = probability
    features["threshold"] = float(bundle["threshold"])
    features["fold"] = 5
    outcomes = _load_outcomes(features, config.live_db, config.output_dir, config.min_future_bars)
    evaluated = features.merge(outcomes, on=["symbol", "feature_time"], how="left")
    return {
        "role": "recycled_rejection_audit_only",
        "used_for_selection": False,
        "feature_coverage": feature_coverage,
        "resolved_rows": int(evaluated["label_value"].notna().sum()),
        "winner": metrics(evaluated, winner),
        "frozen_baseline": metrics(evaluated, baseline),
    }


def _write_report(report: dict[str, Any], path: Path) -> None:
    selected = report["selected_rule"]["rule_id"]
    dev = report["development"]["selected"]
    holdout = report["chronological_holdout"]
    base = holdout["frozen_baseline"]
    win = holdout["selected"]
    actual = holdout["compact_actual_path"]
    august = report["august_audit"]
    if actual["selected"]["available"] and actual["frozen_baseline"]["available"]:
        actual_line = (
            f"- Holdout actual-path EV: baseline "
            f"{actual['frozen_baseline']['summary']['net_ev_stop_first']:.2%}; "
            f"selected {actual['selected']['summary']['net_ev_stop_first']:.2%}; "
            f"selected coverage {actual['selected']['coverage']:.0%}."
        )
    else:
        actual_line = (
            "- Holdout actual-path EV withheld: 5m path coverage was below 80% "
            "or an external source could not be read."
        )
    fold_rows = []
    for fold, selected_fold in report["development"]["selected_by_fold"].items():
        baseline_fold = report["development"]["frozen_baseline_by_fold"][fold]
        fold_rows.append(
            f"| {fold} | {baseline_fold['signals']} / {baseline_fold['precision']:.2%} / "
            f"{baseline_fold['conservative_ev']:.2%} | {selected_fold['signals']} / "
            f"{selected_fold['precision']:.2%} / {selected_fold['conservative_ev']:.2%} |"
        )
    lines = [
        "# Forward 48h — causal episode timing alpha search",
        "",
        "## Kết luận",
        "",
        f"Rule được chọn hoàn toàn trên folds 1–3 là **{selected}**. Fold 4 là chronological holdout riêng; August chỉ là recycled rejection audit, không phải promotion evidence.",
        "",
        "| Giai đoạn | Rule | Signals | Precision | Episode recall | Conservative EV | Wilson 95% |",
        "|---|---|---:|---:|---:|---:|---:|",
        f"| Development | Selected | {dev['signals']} | {dev['precision']:.2%} | {dev['episode_recall']:.2%} | {dev['conservative_ev']:.2%} | {dev['wilson_lower']:.2%}–{dev['wilson_upper']:.2%} |",
        f"| Holdout | Frozen baseline | {base['signals']} | {base['precision']:.2%} | {base['episode_recall']:.2%} | {base['conservative_ev']:.2%} | {base['wilson_lower']:.2%}–{base['wilson_upper']:.2%} |",
        f"| Holdout | Selected | {win['signals']} | {win['precision']:.2%} | {win['episode_recall']:.2%} | {win['conservative_ev']:.2%} | {win['wilson_lower']:.2%}–{win['wilson_upper']:.2%} |",
        "",
        "## Fold stability (signals / precision / conservative EV)",
        "",
        "| Fold | Frozen baseline | Selected |",
        "|---:|---:|---:|",
        *fold_rows,
        "",
        "## Compact execution and August audit",
        "",
        actual_line,
        f"- August recycled audit: baseline {august['frozen_baseline']['signals']} signals / {august['frozen_baseline']['precision']:.2%} precision / {august['frozen_baseline']['conservative_ev']:.2%} EV; selected {august['winner']['signals']} / {august['winner']['precision']:.2%} / {august['winner']['conservative_ev']:.2%}.",
        "",
        "## Protocol",
        "",
        "- Universe, LightGBM/isotonic probabilities, threshold, 48h target/stop contract and compact `0/+3/+6` execution remain unchanged.",
        "- Development: historical walk-forward OOS folds 1–3. Selection lock is written before fold 4 is loaded.",
        "- Multiple testing: Bonferroni-adjusted Wilson lower bound; minimum total/per-fold coverage, recall and coverage-vs-baseline gates.",
        "- Episode recall always uses canonical frozen 6h episodes, including when reset-gap variants are tested.",
        "- This fold 4 artifact existed before this search, so it is chronological pseudo-holdout, not never-seen sealed forward evidence.",
        "",
        "## Research-library mapping",
        "",
        "- Report01: raw/high funding variants are negative controls; no rule shorts only because funding is high.",
        "- Report05: `momentum_deceleration_4h` is tested because it exists point-in-time. `momentum_decel_15m`, `lower_high_4h`, and `volume_dry_up_1h` are absent from this 48h dataset and were not synthesized.",
        "- Report07: funding variants require high percentile/persistence plus reversal or deceleration of `funding_change_8h`; long/short spread remains a negative control.",
        "",
        "## Decision",
        "",
        report["decision"]["explanation"],
        "",
        "No live or frozen config was changed.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(config: Config) -> dict[str, Any]:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    source_lock = json.loads(config.source_lock.read_text(encoding="utf-8"))
    if source_lock.get("lock_sha256") != EXPECTED_FROZEN_LOCK:
        raise RuntimeError("unexpected frozen timing source lock")
    rules = rule_catalog()
    baseline = next(rule for rule in rules if rule.rule_id == "frozen_baseline")

    # Phase 1: only development folds are materialized.
    development, dev_coverage = _load_historical_partition(config, config.dev_folds)
    winner, grid, search_audit = _evaluate_grid(development, rules, config)
    grid_path = config.output_dir / "development_grid.csv"
    grid.to_csv(grid_path, index=False)
    lock_payload = {
        "artifact": "forward48_episode_timing_alpha_selection_lock",
        "created_at": datetime.now(timezone.utc),
        "research_only": True,
        "source_frozen_lock_sha256": EXPECTED_FROZEN_LOCK,
        "historical_oos_sha256": _sha256(config.historical_oos),
        "development_folds": list(config.dev_folds),
        "holdout_fold_not_loaded_during_selection": config.holdout_fold,
        "selected_rule": asdict(winner),
        "search_audit": search_audit,
        "live_configuration_changed": False,
    }
    canonical = json.dumps(lock_payload, sort_keys=True, default=_default, separators=(",", ":"))
    lock_payload["lock_sha256"] = hashlib.sha256(canonical.encode()).hexdigest()
    lock_path = config.output_dir / "selection_lock.json"
    lock_path.write_text(json.dumps(lock_payload, indent=2, default=_default), encoding="utf-8")

    # Phase 2: chronological holdout is loaded only after the selection lock exists.
    holdout, holdout_coverage = _load_historical_partition(config, (config.holdout_fold,))
    selected_dev = metrics(development, winner)
    baseline_dev = metrics(development, baseline)
    selected_by_fold = {
        str(fold): metrics(development[development["fold"].eq(fold)], winner)
        for fold in config.dev_folds
    }
    baseline_by_fold = {
        str(fold): metrics(development[development["fold"].eq(fold)], baseline)
        for fold in config.dev_folds
    }
    selected_holdout = metrics(holdout, winner)
    baseline_holdout = metrics(holdout, baseline)
    selected_signals_holdout = select_signals(holdout, winner)
    baseline_signals_holdout = select_signals(holdout, baseline)
    actual_path = {
        "selected": _compact_actual_path(selected_signals_holdout, config, "selected_holdout"),
        "frozen_baseline": _compact_actual_path(baseline_signals_holdout, config, "baseline_holdout"),
    }

    improvement = selected_holdout["conservative_ev"] - baseline_holdout["conservative_ev"]
    stable = selected_holdout["signals"] >= 20 and selected_holdout["episode_recall"] >= 0.08
    decision = {
        "new_alpha_found": bool(improvement > 0 and stable),
        "holdout_ev_delta": improvement,
        "promote_or_change_frozen": False,
        "explanation": (
            "Candidate improves holdout conservative EV with minimum holdout coverage, but remains research-only until a new sealed-forward window."
            if improvement > 0 and stable
            else "No robust new timing alpha: the development winner did not improve holdout EV with adequate coverage. Keep the frozen timing baseline."
        ),
    }
    report = {
        "artifact": "forward48_episode_timing_alpha_report",
        "generated_at": datetime.now(timezone.utc),
        "status": "research_only_not_live",
        "protocol": {
            "development_folds": list(config.dev_folds),
            "chronological_holdout_fold": config.holdout_fold,
            "selection_lock_written_before_holdout_load": True,
            "holdout_is_previously_opened_pseudo_holdout": True,
            "august_is_recycled_rejection_audit": True,
            "multiple_testing": search_audit,
            "unchanged": ["candidate universe", "LightGBM/isotonic model", "per-fold thresholds", "compact 0/+3/+6 execution", "target20-stop16-48h contract"],
        },
        "source": {
            "frozen_config": str(config.frozen_config),
            "frozen_lock_sha256": EXPECTED_FROZEN_LOCK,
            "historical_oos_sha256": _sha256(config.historical_oos),
            "selection_lock": str(lock_path),
            "selection_lock_sha256": lock_payload["lock_sha256"],
        },
        "data_quality": {"development": dev_coverage, "holdout": holdout_coverage},
        "hypotheses": [asdict(rule) for rule in rules],
        "selected_rule": asdict(winner),
        "development": {
            "selected": selected_dev,
            "frozen_baseline": baseline_dev,
            "selected_by_fold": selected_by_fold,
            "frozen_baseline_by_fold": baseline_by_fold,
        },
        "chronological_holdout": {"selected": selected_holdout, "frozen_baseline": baseline_holdout, "compact_actual_path": actual_path},
        "august_audit": _score_august(config, winner, baseline),
        "omitted_features": {
            "momentum_decel_15m": "not present in the historical 48h PIT table",
            "lower_high_4h": "not present in the historical 48h PIT table",
            "volume_dry_up_1h": "not present in the historical 48h PIT table; volume_percentile was not mislabeled as dry-up",
            "btc_context": "not present in this branch's frozen identical-row OOS stream; delegated to regime branch",
        },
        "decision": decision,
        "live_configuration_changed": False,
    }
    report_path = config.output_dir / "report.json"
    report_path.write_text(json.dumps(report, indent=2, default=_default), encoding="utf-8")
    _write_report(report, config.output_dir / "report.md")
    print(json.dumps({"selected_rule": asdict(winner), "development": selected_dev, "holdout": report["chronological_holdout"], "august_audit": report["august_audit"], "decision": decision, "report": str(report_path)}, indent=2, default=_default))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Config.output_dir)
    parser.add_argument("--skip-august", action="store_true")
    args = parser.parse_args()
    config = Config(output_dir=args.output_dir)
    if args.skip_august:
        original = _score_august
        globals()["_score_august"] = lambda *_args: {"skipped": True}
        try:
            run(config)
        finally:
            globals()["_score_august"] = original
    else:
        run(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
