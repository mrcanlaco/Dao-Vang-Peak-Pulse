"""Post-hoc 2x2 funding-scout x execution compatibility audit.

No policy is selected or tuned here.  The exact predeclared
``funding_exhaustion_rising`` slice is crossed with the already locked compact
baseline and ``vol_offsets_exhaustion_adds`` execution candidate.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    from forward48_execution_risk_search import (
        BASELINE_ID,
        Variant,
        evaluate,
        summarize,
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
        evaluate,
        summarize,
    )
    from scripts.forward48_scalein_timing_compatibility import (
        CompatibilityConfig,
        _load_inputs,
        _load_live_paths,
    )


SCOUT_ID = "funding_exhaustion_rising"
EXPECTED_COUNTS = {"development": 25, "fold4_recycled": 7, "august_opened": 10}


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def funding_exhaustion_rising(frame: pd.DataFrame) -> pd.Series:
    """Exact predeclared regime scout, evaluated at Entry 1 only."""
    return (
        frame["funding_percentile_30d"].ge(0.80)
        & frame["funding_persistence_7d"].gt(0.0)
        & frame["funding_change_8h"].gt(0.0)
    )


def _load_locks(
    execution_lock: Path, regime_report: Path
) -> tuple[Variant, dict[str, float], dict[str, Any], dict[str, Any]]:
    lock = json.loads(execution_lock.read_text(encoding="utf-8"))
    regime = json.loads(regime_report.read_text(encoding="utf-8"))
    selected = lock["selected_candidate"]
    if selected["variant_id"] != "vol_offsets_exhaustion_adds":
        raise RuntimeError("unexpected locked execution candidate")
    if selected["add_gate"] != "exhaustion_reversal":
        raise RuntimeError("locked candidate no longer has exhaustion gate")
    leaderboard = {
        item["variant_id"]: item for item in regime["selection"]["development_leaderboard"]
    }
    scout = leaderboard.get(SCOUT_ID)
    if scout is None or scout["signals"] != EXPECTED_COUNTS["development"]:
        raise RuntimeError("regime report does not contain expected predeclared scout")
    return Variant(**selected), lock["dev_stats_frozen_for_holdout"], lock, regime


def _canonical_keys(frame: pd.DataFrame, time_column: str, *, require_unique: bool = True) -> pd.DataFrame:
    result = frame.copy()
    result["symbol_key"] = result["symbol"].astype(str).str.strip().str.upper()
    result["time_key"] = pd.to_datetime(result[time_column], utc=True)
    if require_unique and result.duplicated(["symbol_key", "time_key"]).any():
        raise RuntimeError("duplicate canonical signal keys")
    return result


def attach_scout_mask(
    execution_events: pd.DataFrame, regime_events: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, Any]]:
    events = _canonical_keys(execution_events, "signal_time", require_unique=False)
    context = _canonical_keys(regime_events, "signal_time")
    context["in_funding_slice"] = funding_exhaustion_rising(context)
    context = context[
        [
            "symbol_key",
            "time_key",
            "in_funding_slice",
            "funding_percentile_30d",
            "funding_persistence_7d",
            "funding_change_8h",
        ]
    ]
    merged = events.merge(
        context,
        on=["symbol_key", "time_key"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    matched = int(merged["_merge"].eq("both").sum())
    if matched != len(merged) or merged["in_funding_slice"].isna().any():
        raise RuntimeError(f"exact context intersection failed: {matched}/{len(merged)}")
    merged["in_funding_slice"] = merged["in_funding_slice"].astype(bool)
    merged = merged.drop(columns=["_merge"])
    unique_keys = merged[["symbol_key", "time_key"]].drop_duplicates()
    return merged, {
        "execution_rows": len(events),
        "matched_rows": matched,
        "exact_row_coverage": matched / len(events) if len(events) else 0.0,
        "unique_signal_keys": len(unique_keys),
        "slice_signal_keys": int(
            merged.loc[merged["in_funding_slice"], ["symbol_key", "time_key"]]
            .drop_duplicates()
            .shape[0]
        ),
        "symbol_normalization": "upper(trim(symbol))",
        "timestamp_normalization": "UTC",
    }


def _cell_summary(frame: pd.DataFrame) -> dict[str, Any]:
    summary = summarize(frame)
    summary["targets"] = int(frame["target_hit"].sum())
    return summary


def four_cells(events: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for scope, scoped in (
        ("all", events),
        ("funding_slice", events[events["in_funding_slice"]]),
    ):
        for execution in (BASELINE_ID, "vol_offsets_exhaustion_adds"):
            cell = scoped[scoped["variant_id"].eq(execution)].copy()
            result[f"{scope}__{execution}"] = _cell_summary(cell)
    return result


def _load_historical_events(output_dir: Path) -> pd.DataFrame:
    frames = []
    for name, period in (
        ("development_events.csv", "development"),
        ("holdout_events.csv", "fold4_recycled"),
    ):
        frame = pd.read_csv(output_dir / name)
        frame = frame[
            frame["variant_id"].isin([BASELINE_ID, "vol_offsets_exhaustion_adds"])
        ].copy()
        frame["signal_time"] = pd.to_datetime(frame["signal_time"], utc=True)
        frame["target_hit"] = frame["target_hit"].astype(bool)
        frame["complete_path"] = frame["complete_path"].astype(bool)
        frame["ambiguous"] = frame["ambiguous"].astype(bool)
        frame["period"] = period
        frames.append(frame)
    return pd.concat(frames, ignore_index=True)


def _evaluate_august(
    candidate: Variant, dev_stats: dict[str, float]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    compatibility = CompatibilityConfig()
    _, signals = _load_inputs(compatibility)
    paths, funding, coverage = _load_live_paths(compatibility, signals)
    signals = signals[signals["exclusion_reason"].isna()].copy()
    signals["fold"] = 5
    baseline = Variant(BASELINE_ID, "baseline")
    events = evaluate(signals, [baseline, candidate], paths, funding, dev_stats)
    events["period"] = "august_opened"
    coverage = {
        **coverage,
        "resolved_signals_evaluated": len(signals),
        "execution_rows": len(events),
    }
    return events, coverage


def run(
    *,
    regime_report: Path = Path("artifacts/forward48_regime_context_20260914.json"),
    regime_events_csv: Path = Path(
        "artifacts/forward48_regime_context_events_20260914.csv"
    ),
    execution_lock: Path = Path(
        "artifacts/forward48_execution_risk_20260914/selection_lock.json"
    ),
    execution_output_dir: Path = Path(
        "artifacts/forward48_execution_risk_20260914"
    ),
    output_dir: Path = Path(
        "artifacts/forward48_funding_execution_compatibility_20260914"
    ),
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate, dev_stats, lock, regime = _load_locks(execution_lock, regime_report)
    regime_events = pd.read_csv(regime_events_csv)
    regime_events["signal_time"] = pd.to_datetime(regime_events["signal_time"], utc=True)
    historical_execution = _load_historical_events(execution_output_dir)
    august_execution, august_path_coverage = _evaluate_august(candidate, dev_stats)

    period_reports: dict[str, Any] = {}
    intersections: list[pd.DataFrame] = []
    for period, execution_events in pd.concat(
        [historical_execution, august_execution], ignore_index=True
    ).groupby("period", sort=False):
        regime_period = (
            regime_events[regime_events["period"].eq("historical_oos")]
            if period != "august_opened"
            else regime_events[
                regime_events["period"].eq("timing_lock_august_posthoc")
            ]
        )
        if period == "development":
            regime_period = regime_period[regime_period["fold"].isin([1, 2, 3])]
        elif period == "fold4_recycled":
            regime_period = regime_period[regime_period["fold"].eq(4)]
        else:
            regime_period = regime_period[regime_period["fold"].eq(5)]
        merged, coverage = attach_scout_mask(execution_events, regime_period)
        if coverage["slice_signal_keys"] != EXPECTED_COUNTS[period]:
            raise RuntimeError(
                f"{period} scout count changed: {coverage['slice_signal_keys']}"
            )
        intersections.append(merged)
        cells = four_cells(merged)
        slice_candidate = merged[
            merged["in_funding_slice"]
            & merged["variant_id"].eq("vol_offsets_exhaustion_adds")
        ]
        period_reports[period] = {
            "intersection": coverage,
            "cells": cells,
            "slice_candidate_adds": {
                "entry2_fills": int(slice_candidate["filled_legs"].ge(2).sum()),
                "entry3_fills": int(slice_candidate["filled_legs"].ge(3).sum()),
                "signals": len(slice_candidate),
            },
        }

    combined = pd.concat(intersections, ignore_index=True)
    keys = combined[
        [
            "period",
            "fold",
            "signal_id",
            "symbol",
            "signal_time",
            "variant_id",
            "in_funding_slice",
            "funding_percentile_30d",
            "funding_persistence_7d",
            "funding_change_8h",
            "target_hit",
            "filled_legs",
            "capital_deployed",
            "actual_return",
            "conservative_return",
        ]
    ].sort_values(["period", "signal_time", "symbol", "variant_id"])
    keys.to_csv(output_dir / "exact_intersection_events.csv", index=False)

    report = {
        "artifact": "forward48_funding_execution_compatibility_v1",
        "generated_at": datetime.now(timezone.utc),
        "status": "opened_posthoc_compatibility_only",
        "live_configuration_changed": False,
        "no_selection_no_retuning": True,
        "inputs": {
            "regime_report_sha256": _sha256(regime_report),
            "regime_events_sha256": _sha256(regime_events_csv),
            "execution_lock_sha256": _sha256(execution_lock),
            "execution_candidate": asdict(candidate),
            "scout": {
                "variant_id": SCOUT_ID,
                "predicate": (
                    "funding_percentile_30d >= 0.80 AND "
                    "funding_persistence_7d > 0 AND funding_change_8h > 0 at Entry1"
                ),
                "regime_development_signals": regime["selection"][
                    "development_leaderboard"
                ][
                    next(
                        i
                        for i, item in enumerate(
                            regime["selection"]["development_leaderboard"]
                        )
                        if item["variant_id"] == SCOUT_ID
                    )
                ]["signals"],
            },
            "execution_selection_lock_generated_at": lock["generated_at"],
        },
        "contract": {
            "target_from_weighted_average": 0.20,
            "hard_stop_from_weighted_average": 0.16,
            "horizon_hours": 48,
            "same_bar": "stop_first",
            "fees_slippage_and_funding": True,
        },
        "periods": period_reports,
        "august_path_coverage": august_path_coverage,
        "structural_tension": {
            "regime_entry1_requires": "funding_change_8h > 0",
            "locked_execution_add_requires": "Entry1 funding_change_8h <= 0 plus price reversal",
            "observed_later_funding_transition_available": False,
            "consequence": (
                "On the rising-funding slice the locked implementation cannot add E2/E3 "
                "by construction; it degenerates to a 20%-capital Entry1-only policy."
            ),
        },
        "decision": {
            "promotion_eligible": False,
            "reason": (
                "post-hoc composition of two scouts on opened historical fold4 and August; "
                "no selection or retuning performed"
            ),
        },
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, default=_json_default, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    report = run()
    print(json.dumps(report["periods"], default=_json_default, indent=2))


if __name__ == "__main__":
    main()
