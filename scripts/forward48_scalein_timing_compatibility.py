"""Post-hoc compatibility check: locked timing signals x locked scale-in policies.

This runner deliberately performs no policy selection and is never promotion
evidence.  It verifies the pre-existing timing lock and signal keys, then uses
only live.kline/live.funding paths to compare fixed execution templates.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

try:
    from forward48_scalein_backtest import (
        BUILT_INS,
        Template,
        _evaluate_templates,
        _summarize,
        _weekly,
    )
    from forward48_scalein_backtest import (
        Config as ScaleInConfig,
    )
except ImportError:  # imported as scripts.forward48_scalein_timing_compatibility
    from scripts.forward48_scalein_backtest import (
        BUILT_INS,
        Template,
        _evaluate_templates,
        _summarize,
        _weekly,
    )
    from scripts.forward48_scalein_backtest import (
        Config as ScaleInConfig,
    )


EXPECTED_TIMING_LOCK_SHA256 = (
    "ba8ccac68fb824a952b60c998d5b0ff86977119d85692626adde7fb9f7371305"
)
OPTIMIZED_LOCKED = Template(
    "historical_optimized_0_10_18",
    (0.0, 0.10, 0.18),
    (0.10, 0.30, 0.60),
    6,
)
SINGLE_ENTRY = Template(
    "single_entry_timing_reference", (0.0, 9.0, 10.0), (1.0, 0.0, 0.0), 0
)


@dataclass(frozen=True)
class CompatibilityConfig:
    timing_report: Path = Path(
        "artifacts/forward48_timing_20260913/"
        "forward48_timing_locked_forward_report.json"
    )
    timing_signals: Path = Path(
        "artifacts/forward48_timing_20260913/"
        "forward48_timing_august_signals_live.csv"
    )
    timing_signal_keys: Path = Path(
        "artifacts/forward48_timing_20260913/"
        "forward48_timing_august_locked_signal_keys.csv"
    )
    live_db: Path = Path("data_live/live.duckdb")
    output_json: Path = Path(
        "artifacts/forward48_scalein_timing_compatibility_20260913.json"
    )
    output_csv: Path = Path(
        "artifacts/forward48_scalein_timing_compatibility_events_20260913.csv"
    )
    target_drawdown: float = 0.20
    hard_stop_pct: float = 0.16
    fee_bps_per_side: float = 5.0
    slippage_bps_per_side: float = 5.0


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def verify_locked_inputs(
    timing_report: dict[str, Any], signals: pd.DataFrame, keys: pd.DataFrame
) -> None:
    actual_lock = timing_report["immutable_inputs"]["policy_lock_sha256"]
    if actual_lock != EXPECTED_TIMING_LOCK_SHA256:
        raise RuntimeError(f"unexpected timing lock: {actual_lock}")
    if timing_report["immutable_inputs"].get(
        "august_labels_used_for_model_or_policy_selection"
    ) is not False:
        raise RuntimeError("timing report does not prove August-free selection")
    signal_key_set = set(
        zip(signals["symbol"].astype(str), signals["feature_time"].astype(str))
    )
    locked_key_set = set(
        zip(keys["symbol"].astype(str), keys["feature_time"].astype(str))
    )
    if signal_key_set != locked_key_set or len(signals) != len(keys):
        raise RuntimeError("timing signals do not exactly match locked signal keys")
    if len(signals) != int(timing_report["august"]["signals"]):
        raise RuntimeError("timing signal count differs from locked report")


def _load_inputs(config: CompatibilityConfig) -> tuple[dict[str, Any], pd.DataFrame]:
    timing_report = json.loads(config.timing_report.read_text(encoding="utf-8"))
    signals = pd.read_csv(config.timing_signals)
    keys = pd.read_csv(config.timing_signal_keys)
    verify_locked_inputs(timing_report, signals, keys)
    signals["feature_time"] = pd.to_datetime(signals["feature_time"], utc=True)
    signals = signals.sort_values(["feature_time", "symbol"]).reset_index(drop=True)
    signals["signal_id"] = [f"timing-{index:03d}" for index in range(len(signals))]
    return timing_report, signals


def _load_live_paths(
    config: CompatibilityConfig, signals: pd.DataFrame
) -> tuple[dict[str, list[tuple]], dict[str, list[tuple]], dict[str, Any]]:
    relation = signals[["signal_id", "symbol", "feature_time", "entry_price"]]
    conn = duckdb.connect(str(config.live_db), read_only=True)
    conn.register("locked_signals", relation)
    try:
        paths_raw = conn.execute(
            """
            SELECT s.signal_id, k.close_time, CAST(k.high AS DOUBLE),
                   CAST(k.low AS DOUBLE), CAST(k.close AS DOUBLE)
            FROM locked_signals s
            INNER JOIN kline k
              ON k.symbol=s.symbol AND k.interval='5m'
             AND k.close_time > s.feature_time
             AND k.close_time <= s.feature_time + INTERVAL '48' HOUR
            ORDER BY s.signal_id, k.close_time
            """
        ).fetchall()
        funding_raw = conn.execute(
            """
            SELECT s.signal_id, f.funding_time, CAST(f.funding_rate AS DOUBLE)
            FROM locked_signals s
            INNER JOIN funding f
              ON f.symbol=s.symbol
             AND f.funding_time > s.feature_time
             AND f.funding_time <= s.feature_time + INTERVAL '48' HOUR
            ORDER BY s.signal_id, f.funding_time
            """
        ).fetchall()
        coverage = conn.execute(
            """
            SELECT COUNT(*) signals,
                   SUM(path_bars >= 575) complete_by_count,
                   SUM(last_path_time >= feature_time + INTERVAL '48' HOUR
                                         - INTERVAL '5' MINUTE) complete_by_time,
                   MIN(first_path_time), MAX(last_path_time)
            FROM (
              SELECT s.signal_id, s.feature_time, COUNT(k.close_time) path_bars,
                     MIN(k.close_time) first_path_time,
                     MAX(k.close_time) last_path_time
              FROM locked_signals s
              LEFT JOIN kline k
                ON k.symbol=s.symbol AND k.interval='5m'
               AND k.close_time > s.feature_time
               AND k.close_time <= s.feature_time + INTERVAL '48' HOUR
              GROUP BY s.signal_id, s.feature_time
            )
            """
        ).fetchone()
    finally:
        conn.close()

    paths: dict[str, list[tuple]] = {}
    funding: dict[str, list[tuple]] = {}
    for signal in signals.itertuples(index=False):
        # Entry 1 is a market-at-signal reference fill, matching timing labels.
        paths[str(signal.signal_id)] = [
            (
                pd.Timestamp(signal.feature_time),
                float(signal.entry_price),
                float(signal.entry_price),
                float(signal.entry_price),
            )
        ]
    for signal_id, *row in paths_raw:
        paths[str(signal_id)].append(tuple(row))
    for signal_id, *row in funding_raw:
        funding.setdefault(str(signal_id), []).append(tuple(row))
    audit = {
        "signals": int(coverage[0]),
        "complete_by_575_bar_count": int(coverage[1] or 0),
        "complete_by_end_time": int(coverage[2] or 0),
        "first_path_time": coverage[3],
        "last_path_time": coverage[4],
        "path_source": "data_live/live.duckdb::kline",
        "funding_source": "data_live/live.duckdb::funding",
    }
    return paths, funding, audit


def _single_entry_registered(timing_report: dict[str, Any]) -> dict[str, Any]:
    registered = timing_report["august"]
    return {
        "signals": int(registered["signals"]),
        "resolved": int(registered["evaluable_signals"]),
        "excluded": int(registered["excluded_signals"]),
        "target_rate": float(registered["precision"]),
        "conservative_binary_ev": float(registered["conservative_ev"]),
        "note": (
            "pre-existing timing report; binary EV assigns every non-target "
            "the full -16% stop and 20 bps cost"
        ),
    }


def run(config: CompatibilityConfig) -> dict[str, Any]:
    timing_report, signals = _load_inputs(config)
    paths, funding, coverage = _load_live_paths(config, signals)
    templates = [SINGLE_ENTRY, *BUILT_INS, OPTIMIZED_LOCKED]
    execution_config = ScaleInConfig(
        target_drawdown=config.target_drawdown,
        hard_stop_pct=config.hard_stop_pct,
        fee_bps_per_side=config.fee_bps_per_side,
        slippage_bps_per_side=config.slippage_bps_per_side,
    )
    events = _evaluate_templates(
        signals,
        templates,
        paths,
        funding,
        execution_config,
        "timing_lock_august_posthoc",
    )
    exclusions = signals[["signal_id", "exclusion_reason", "label_value"]]
    events = events.merge(exclusions, on="signal_id", how="left", validate="many_to_one")
    resolved = events[events["exclusion_reason"].isna()].copy()
    summaries = {
        template.template_id: _summarize(
            resolved[resolved["template_id"] == template.template_id].sort_values(
                "signal_time"
            )
        )
        for template in templates
    }
    report = {
        "artifact": "forward48_scalein_timing_compatibility_v1",
        "generated_at": datetime.now(timezone.utc),
        "status": "posthoc_compatibility_not_sealed_not_promotion",
        "live_configuration_changed": False,
        "immutable_inputs": {
            "timing_policy_lock_sha256": EXPECTED_TIMING_LOCK_SHA256,
            "timing_signal_keys_sha256": timing_report["immutable_inputs"][
                "signal_keys_sha256_before_outcome_load"
            ],
            "signal_count": len(signals),
            "execution_templates": [asdict(item) for item in templates],
            "execution_optimized_on_august": False,
        },
        "compatibility_warning": (
            "Timing and scale-in components were individually selected before this "
            "composition, but this combination is inspected post-hoc on already "
            "opened August outcomes. It is not sealed forward evidence."
        ),
        "contract": {
            "target_drawdown_from_weighted_average": config.target_drawdown,
            "hard_stop_from_weighted_average": config.hard_stop_pct,
            "horizon_hours": 48,
            "same_bar": "stop_first",
            "round_trip_cost": 2
            * (config.fee_bps_per_side + config.slippage_bps_per_side)
            / 10_000,
            "funding": "actual live funding while each filled leg is active",
            "entry1": "market reference fill at signal timestamp",
        },
        "coverage": {
            **coverage,
            "locked_signals": len(signals),
            "timing_evaluable_signals": int(signals["exclusion_reason"].isna().sum()),
            "timing_excluded_signals": int(signals["exclusion_reason"].notna().sum()),
        },
        "single_entry_registered_timing_outcome": _single_entry_registered(
            timing_report
        ),
        "actual_path_summaries": summaries,
        "per_week": {
            template.template_id: _weekly(resolved, template.template_id)
            for template in templates
        },
        "decision": {
            "promotion_eligible": False,
            "reason": (
                "post-hoc composition on opened August outcomes; fewer than 100 "
                "resolved independent signals"
            ),
        },
    }
    config.output_json.parent.mkdir(parents=True, exist_ok=True)
    config.output_json.write_text(
        json.dumps(report, default=_jsonable, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    events.to_csv(config.output_csv, index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-json", type=Path, default=CompatibilityConfig.output_json)
    parser.add_argument("--output-csv", type=Path, default=CompatibilityConfig.output_csv)
    args = parser.parse_args()
    report = run(
        CompatibilityConfig(output_json=args.output_json, output_csv=args.output_csv)
    )
    print(
        json.dumps(
            {
                "coverage": report["coverage"],
                "single_entry_registered": report[
                    "single_entry_registered_timing_outcome"
                ],
                "actual_path_summaries": report["actual_path_summaries"],
            },
            default=_jsonable,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
