"""Mechanism-feasibility audit for causal funding rollover after Entry 1.

The Entry-1 universe is the already opened ``funding_exhaustion_rising``
slice.  No variant is selected: compact, a predeclared 6h true-transition rule,
and a predeclared 12h true-transition rule are all reported side by side.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

try:
    from forward48_execution_risk_search import (
        BASELINE_ID,
        Variant,
        _load_paths,
        evaluate,
        load_frozen_signals,
        summarize,
    )
    from forward48_execution_risk_search import (
        Config as ExecutionConfig,
    )
    from forward48_funding_execution_compatibility import (
        funding_exhaustion_rising,
    )
    from forward48_scalein_timing_compatibility import (
        CompatibilityConfig,
        _load_inputs,
        _load_live_paths,
    )
except ImportError:
    from scripts.forward48_execution_risk_search import (
        BASELINE_ID,
        Variant,
        _load_paths,
        evaluate,
        load_frozen_signals,
        summarize,
    )
    from scripts.forward48_execution_risk_search import (
        Config as ExecutionConfig,
    )
    from scripts.forward48_funding_execution_compatibility import (
        funding_exhaustion_rising,
    )
    from scripts.forward48_scalein_timing_compatibility import (
        CompatibilityConfig,
        _load_inputs,
        _load_live_paths,
    )


WINDOWS = (6, 12)
EXPECTED_SLICE_COUNTS = {"development": 25, "fold4_recycled": 7, "august_opened": 10}


def _json_default(value: Any) -> Any:
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


def strict_transition_mask(frame: pd.DataFrame) -> pd.Series:
    """Predeclared later rollover: both 8h change and raw rate roll over."""
    return (
        frame["funding_change_8h"].le(0.0)
        & frame["funding_rate_raw"].lt(frame["entry_funding_rate"])
    )


def _canonical(frame: pd.DataFrame, time_column: str) -> pd.DataFrame:
    result = frame.copy()
    result["symbol"] = result["symbol"].astype(str).str.strip().str.upper()
    result[time_column] = pd.to_datetime(result[time_column], utc=True)
    return result


def _slice_keys(intersection_csv: Path) -> pd.DataFrame:
    frame = pd.read_csv(intersection_csv)
    frame = frame[
        frame["variant_id"].eq(BASELINE_ID) & frame["in_funding_slice"].astype(bool)
    ].copy()
    frame = _canonical(frame, "signal_time")
    if not funding_exhaustion_rising(frame).all():
        raise RuntimeError("intersection contains a non-scout signal")
    keys = frame[
        ["period", "fold", "signal_id", "symbol", "signal_time"]
    ].drop_duplicates()
    if keys.duplicated(["symbol", "signal_time"]).any():
        raise RuntimeError("duplicate slice signal keys")
    counts = keys.groupby("period").size().to_dict()
    if counts != EXPECTED_SLICE_COUNTS:
        raise RuntimeError(f"slice signal counts changed: {counts}")
    return keys


def _later_feature_updates(
    db_path: Path,
    table: str,
    signals: pd.DataFrame,
) -> pd.DataFrame:
    relation = signals[
        ["signal_id", "symbol", "feature_time", "funding_rate_raw"]
    ].rename(columns={"funding_rate_raw": "entry_funding_rate"})
    conn = duckdb.connect(str(db_path), read_only=True)
    conn.register("slice_signals", relation)
    try:
        updates = conn.execute(
            f"""
            SELECT s.signal_id, s.feature_time AS entry_time,
                   s.entry_funding_rate, f.feature_time AS update_time,
                   CAST(f.funding_rate_raw AS DOUBLE) funding_rate_raw,
                   CAST(f.funding_change_8h AS DOUBLE) funding_change_8h
            FROM slice_signals s
            LEFT JOIN {table} f
              ON upper(trim(f.symbol))=s.symbol
             AND f.feature_time > s.feature_time
             AND f.feature_time <= s.feature_time + INTERVAL '12' HOUR
            ORDER BY s.signal_id, f.feature_time
            """
        ).fetchdf()
    finally:
        conn.close()
    for column in ("entry_time", "update_time"):
        updates[column] = pd.to_datetime(updates[column], utc=True)
    return updates


def transition_table(
    signals: pd.DataFrame, updates: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    result = signals.copy()
    audit: dict[str, Any] = {}
    valid = updates[updates["update_time"].notna()].copy()
    valid["minutes_after_entry"] = (
        valid["update_time"] - valid["entry_time"]
    ).dt.total_seconds() / 60.0
    valid["is_transition"] = strict_transition_mask(valid)
    for hours in WINDOWS:
        window = valid[valid["minutes_after_entry"].le(hours * 60)]
        observed = set(window["signal_id"].astype(str))
        transitioned = (
            window[window["is_transition"]]
            .groupby("signal_id")["update_time"]
            .min()
        )
        column = f"transition_time_{hours}h"
        result[column] = result["signal_id"].map(transitioned)
        counts = window.groupby("signal_id").size()
        changing = window.groupby("signal_id")["funding_rate_raw"].nunique().gt(1)
        audit[f"{hours}h"] = {
            "signals": len(signals),
            "signals_with_later_feature_observation": len(observed),
            "observation_coverage": len(observed) / len(signals) if len(signals) else 0.0,
            "signals_with_more_than_one_distinct_later_rate": int(changing.sum()),
            "signals_with_strict_transition": int(result[column].notna().sum()),
            "transition_coverage": float(result[column].notna().mean()),
            "median_update_rows_when_observed": float(counts.median()) if len(counts) else 0.0,
        }
    if len(valid):
        diffs = (
            valid.sort_values(["signal_id", "update_time"])
            .groupby("signal_id")["update_time"]
            .diff()
            .dropna()
            .dt.total_seconds()
            / 60.0
        )
        audit["feature_update_gap_minutes"] = {
            "p10": float(diffs.quantile(0.10)) if len(diffs) else None,
            "median": float(diffs.median()) if len(diffs) else None,
            "p90": float(diffs.quantile(0.90)) if len(diffs) else None,
        }
    return result, audit


def settlement_audit(
    signals: pd.DataFrame, funding: dict[str, list[tuple]]
) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for hours in WINDOWS:
        counts = []
        for signal in signals.itertuples(index=False):
            cutoff = pd.Timestamp(signal.feature_time) + pd.Timedelta(hours=hours)
            counts.append(
                sum(
                    pd.Timestamp(timestamp).tz_convert("UTC") <= cutoff
                    for timestamp, _ in funding.get(str(signal.signal_id), [])
                )
            )
        values = np.asarray(counts)
        report[f"{hours}h"] = {
            "signals": len(signals),
            "signals_with_settlement": int((values > 0).sum()),
            "settlement_coverage": float((values > 0).mean()) if len(values) else 0.0,
            "mean_settlements": float(values.mean()) if len(values) else 0.0,
            "max_settlements": int(values.max()) if len(values) else 0,
        }
    return report


def _attach_keys(signals: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    left = _canonical(signals, "feature_time")
    right = keys.rename(columns={"signal_time": "feature_time"})[
        ["period", "symbol", "feature_time"]
    ]
    result = left.merge(
        right,
        on=["symbol", "feature_time"],
        how="inner",
        validate="one_to_one",
    )
    if len(result) != len(keys):
        raise RuntimeError(f"slice/source intersection {len(result)}/{len(keys)}")
    return result


def _evaluate_period(
    signals: pd.DataFrame,
    paths: dict[str, list[tuple]],
    funding: dict[str, list[tuple]],
    dev_stats: dict[str, float],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    all_events = []
    baseline = Variant(BASELINE_ID, "baseline")
    all_events.append(evaluate(signals, [baseline], paths, funding, dev_stats))
    for hours in WINDOWS:
        current = signals.copy()
        current["transition_time"] = current[f"transition_time_{hours}h"]
        variant = Variant(
            f"true_transition_{hours}h",
            "true_funding_transition",
            window_hours=hours,
            offset_mode="volatility",
            add_gate="true_transition",
        )
        all_events.append(evaluate(current, [variant], paths, funding, dev_stats))
    events = pd.concat(all_events, ignore_index=True)
    return events, {
        variant_id: summarize(frame)
        for variant_id, frame in events.groupby("variant_id")
    }


def _period_source(
    period: str,
    keys: pd.DataFrame,
    historical: pd.DataFrame,
    august: pd.DataFrame,
) -> pd.DataFrame:
    if period == "development":
        source = historical[historical["fold"].isin([1, 2, 3])]
    elif period == "fold4_recycled":
        source = historical[historical["fold"].eq(4)]
    else:
        source = august
    return _attach_keys(source, keys)


def run(
    output_dir: Path = Path("artifacts/forward48_true_funding_transition_20260914"),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    intersection_csv = Path(
        "artifacts/forward48_funding_execution_compatibility_20260914/"
        "exact_intersection_events.csv"
    )
    execution_lock_path = Path(
        "artifacts/forward48_execution_risk_20260914/selection_lock.json"
    )
    execution_lock = json.loads(execution_lock_path.read_text(encoding="utf-8"))
    dev_stats = execution_lock["dev_stats_frozen_for_holdout"]
    keys = _slice_keys(intersection_csv)

    historical = load_frozen_signals(ExecutionConfig())
    compatibility = CompatibilityConfig()
    _, august = _load_inputs(compatibility)
    august = august[august["exclusion_reason"].isna()].copy()
    august["fold"] = 5

    period_reports: dict[str, Any] = {}
    event_frames = []
    for period in EXPECTED_SLICE_COUNTS:
        period_keys = keys[keys["period"].eq(period)]
        source = _period_source(period, period_keys, historical, august)
        if period == "august_opened":
            updates = _later_feature_updates(
                Path("data_live/live.duckdb"), "feature_results", source
            )
            all_paths, all_funding, path_coverage = _load_live_paths(
                compatibility, source
            )
        else:
            updates = _later_feature_updates(
                Path("artifacts/universe_policy_v2_48h.duckdb"),
                "universe_policy_candidates_v2",
                source,
            )
            all_paths, all_funding, path_coverage = _load_paths(
                ExecutionConfig(), source
            )
        source, feature_audit = transition_table(source, updates)
        events, cells = _evaluate_period(
            source, all_paths, all_funding, dev_stats
        )
        events["period"] = period
        event_frames.append(events)
        period_reports[period] = {
            "signals": len(source),
            "path_coverage": path_coverage,
            "feature_update_availability": feature_audit,
            "settlement_availability": settlement_audit(source, all_funding),
            "cells": cells,
        }

    events = pd.concat(event_frames, ignore_index=True)
    events.to_csv(output_dir / "events.csv", index=False)
    six_settlement = [
        period_reports[period]["settlement_availability"]["6h"]["settlement_coverage"]
        for period in period_reports
    ]
    report = {
        "artifact": "forward48_true_funding_transition_feasibility_v1",
        "generated_at": datetime.now(timezone.utc),
        "status": "exploratory_mechanism_feasibility_only",
        "live_configuration_changed": False,
        "no_selection_no_retuning_no_promotion": True,
        "inputs": {
            "execution_lock_sha256": _sha256(execution_lock_path),
            "compatibility_intersection_sha256": _sha256(intersection_csv),
            "entry1_scout": (
                "funding_percentile_30d>=0.80 AND funding_persistence_7d>0 "
                "AND funding_change_8h>0"
            ),
            "strict_later_transition": (
                "at a later point-in-time feature timestamp: funding_change_8h<=0 "
                "AND funding_rate_raw<Entry1 funding_rate_raw"
            ),
            "price_confirmation": (
                "offset touched, then close <=99.5% of offset and below previous close"
            ),
            "variants": [
                asdict(Variant(BASELINE_ID, "baseline")),
                asdict(
                    Variant(
                        "true_transition_6h",
                        "true_funding_transition",
                        window_hours=6,
                        offset_mode="volatility",
                        add_gate="true_transition",
                    )
                ),
                asdict(
                    Variant(
                        "true_transition_12h",
                        "true_funding_transition",
                        window_hours=12,
                        offset_mode="volatility",
                        add_gate="true_transition",
                    )
                ),
            ],
        },
        "data_semantics": {
            "funding_rate_raw": "last known settled funding rate, forward-filled on the 5m feature timeline",
            "funding_change_8h": "last-known settled rate minus 96-row (8h) lag",
            "predicted_funding_persisted_for_research": False,
            "evidence": (
                "feature builder uses funding_rate_last_known; historical collector is "
                "/fapi/v1/fundingRate. premiumIndex predicted funding is used by web API "
                "but not present in historical candidate/live feature_results schema"
            ),
        },
        "periods": period_reports,
        "mechanism_feasibility": {
            "six_hour_settlement_coverage_by_period": six_settlement,
            "six_hour_is_structurally_limited": min(six_settlement) < 0.80,
            "interpretation": (
                "A 6h window is shorter than the normal ~8h settlement cadence. "
                "Only entries crossing a settlement boundary can observe a genuine update."
            ),
        },
        "decision": {
            "promotion_eligible": False,
            "reason": (
                "opened/post-hoc feasibility audit on a low-coverage scout; no variant "
                "selection and no synthetic funding transitions"
            ),
        },
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, default=_json_default, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    report = run()
    print(
        json.dumps(
            {
                period: {
                    "feature": value["feature_update_availability"],
                    "settlement": value["settlement_availability"],
                    "cells": value["cells"],
                }
                for period, value in report["periods"].items()
            },
            default=_json_default,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
