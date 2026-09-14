"""Leakage-safe sensitivity backtest for v2 universe and episode policy.

The experiment selects pump threshold, PIT liquidity gate and cooldown only on
development walk-forward folds.  It then evaluates the locked configuration
once on the final sealed holdout.  It never writes a serving bundle or changes
live configuration.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

from dao_vang.experiments.train_distribution_v2 import (
    SERVING_FEATURE_COLS,
    _build_estimator,
    _calibrator,
    _partition_history,
    _predict_calibrated,
    _probability_metrics,
    _threshold_metrics,
)


@dataclass(frozen=True)
class SensitivityConfig:
    feature_db: Path = Path("artifacts/backtest_results_pit.duckdb")
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    dataset_db: Path = Path("artifacts/universe_policy_v2.duckdb")
    output_json: Path = Path("artifacts/universe_policy_sensitivity_20260913.json")
    source_table: str = "bt_combined"
    dataset_table: str = "universe_policy_candidates_v2"
    base_pump_threshold: float = 0.10
    pump_thresholds: tuple[float, ...] = (0.10, 0.15, 0.20, 0.30)
    cooldown_hours: tuple[int, ...] = (12, 24, 48)
    liquidity_variants: tuple[str, ...] = ("all", "exclude_bottom_quartile")
    sample_minute: int = 4
    target_drawdown: float = 0.20
    max_adverse_excursion: float = 0.16
    round_trip_cost: float = 0.002
    horizon_hours: int = 24
    min_future_bars: int = 276
    embargo_hours: int = 24
    warmup_days: int = 90
    development_folds: int = 3
    sealed_fraction: float = 0.20
    min_policy_signals: int = 10
    min_recall_for_threshold: float = 0.10
    random_state: int = 42
    rebuild_dataset: bool = False


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def materialize_dataset(config: SensitivityConfig) -> dict[str, Any]:
    """Materialize hourly PIT candidates, past liquidity and ordered outcomes."""

    config.dataset_db.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(config.dataset_db))
    conn.execute("PRAGMA disable_progress_bar")
    conn.execute("SET threads=4")
    conn.execute(f"ATTACH '{_sql_path(config.feature_db)}' AS fdb (READ_ONLY)")
    conn.execute(f"ATTACH '{_sql_path(config.market_db)}' AS mdb (READ_ONLY)")
    try:
        exists = conn.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='main' AND table_name=?",
            [config.dataset_table],
        ).fetchone()[0]
        if config.rebuild_dataset or not exists:
            columns = ",\n                        ".join(
                f"f.{column}" for column in SERVING_FEATURE_COLS
            )
            conn.execute(f"DROP TABLE IF EXISTS {config.dataset_table}")
            conn.execute(
                f"""
                CREATE TABLE {config.dataset_table} AS
                WITH candidates AS (
                    SELECT
                        f.feature_time,
                        f.symbol,
                        k.close AS entry_price,
                        {columns}
                    FROM fdb.main.{config.source_table} f
                    INNER JOIN mdb.main.klines_5m k
                      ON k.symbol=f.symbol AND k.close_time=f.feature_time
                    WHERE f.price_ret_24h >= {config.base_pump_threshold}
                      AND EXTRACT(MINUTE FROM f.feature_time)={config.sample_minute}
                ),
                past_liquidity AS (
                    SELECT
                        c.symbol,
                        c.feature_time,
                        SUM(p.quote_volume) AS quote_volume_24h
                    FROM candidates c
                    LEFT JOIN mdb.main.klines_5m p
                      ON p.symbol=c.symbol
                     AND p.close_time <= c.feature_time
                     AND p.close_time > c.feature_time - INTERVAL '24' HOUR
                    GROUP BY c.symbol, c.feature_time
                ),
                outcomes AS (
                    SELECT
                        c.symbol,
                        c.feature_time,
                        COUNT(f.close_time) AS future_bars,
                        MAX(f.close_time) AS last_future_time,
                        MIN(f.close_time) FILTER (
                          WHERE f.low <= c.entry_price * {1-config.target_drawdown}
                        ) AS target_time,
                        MIN(f.close_time) FILTER (
                          WHERE f.high >= c.entry_price * {1+config.max_adverse_excursion}
                        ) AS stop_time
                    FROM candidates c
                    LEFT JOIN mdb.main.klines_5m f
                      ON f.symbol=c.symbol
                     AND f.close_time > c.feature_time
                     AND f.close_time <= c.feature_time
                         + INTERVAL '{config.horizon_hours}' HOUR
                    GROUP BY c.symbol, c.feature_time
                ),
                assembled AS (
                    SELECT
                        c.*,
                        l.quote_volume_24h,
                        o.future_bars,
                        o.target_time,
                        o.stop_time,
                        CASE
                          WHEN o.future_bars < {config.min_future_bars}
                            OR o.last_future_time < c.feature_time
                               + INTERVAL '{config.horizon_hours}' HOUR
                               - INTERVAL '5' MINUTE
                            THEN 'incomplete_future'
                          WHEN o.target_time IS NOT NULL
                           AND o.target_time=o.stop_time
                            THEN 'ambiguous_same_bar'
                          ELSE NULL
                        END AS exclusion_reason,
                        CASE
                          WHEN o.future_bars < {config.min_future_bars}
                            OR o.last_future_time < c.feature_time
                               + INTERVAL '{config.horizon_hours}' HOUR
                               - INTERVAL '5' MINUTE
                            THEN NULL
                          WHEN o.target_time IS NOT NULL
                           AND o.target_time=o.stop_time
                            THEN NULL
                          WHEN o.target_time IS NOT NULL
                           AND (o.stop_time IS NULL OR o.target_time<o.stop_time)
                            THEN 1
                          ELSE 0
                        END AS label_value
                    FROM candidates c
                    INNER JOIN past_liquidity l USING(symbol, feature_time)
                    INNER JOIN outcomes o USING(symbol, feature_time)
                )
                SELECT
                    *,
                    PERCENT_RANK() OVER (
                      PARTITION BY feature_time ORDER BY quote_volume_24h
                    ) AS liquidity_percentile_xs
                FROM assembled
                ORDER BY feature_time, symbol
                """
            )
        cursor = conn.execute(
            f"""
            SELECT COUNT(*) AS row_count,
                   COUNT(label_value) labeled_rows,
                   SUM(label_value=1) positives,
                   COUNT(*) FILTER (WHERE exclusion_reason='ambiguous_same_bar') ambiguous,
                   COUNT(*) FILTER (WHERE exclusion_reason='incomplete_future') incomplete,
                   COUNT(DISTINCT symbol) symbols,
                   MIN(feature_time) min_time,
                   MAX(feature_time) max_time
            FROM {config.dataset_table}
            """
        )
        values = cursor.fetchone()
        return dict(zip([item[0] for item in cursor.description], values))
    finally:
        conn.close()


def load_dataset(config: SensitivityConfig) -> pd.DataFrame:
    conn = duckdb.connect(str(config.dataset_db), read_only=True)
    try:
        frame = conn.execute(
            f"SELECT * FROM {config.dataset_table} "
            "WHERE label_value IS NOT NULL ORDER BY feature_time, symbol"
        ).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["label_value"] = frame["label_value"].astype("int8")
    return frame


def _apply_universe(
    frame: pd.DataFrame, pump_threshold: float, liquidity_variant: str
) -> pd.DataFrame:
    mask = frame["price_ret_24h"] >= pump_threshold
    if liquidity_variant == "exclude_bottom_quartile":
        mask &= frame["liquidity_percentile_xs"] >= 0.25
    elif liquidity_variant != "all":
        raise ValueError(f"unknown liquidity variant: {liquidity_variant}")
    return frame.loc[mask].copy()


def _boundaries(
    frame: pd.DataFrame, warmup_days: int, folds: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start = frame["feature_time"].min()
    end = frame["feature_time"].max() + pd.Timedelta(microseconds=1)
    first_test = start + pd.Timedelta(days=warmup_days)
    if first_test >= end:
        raise ValueError("development dataset is shorter than warmup")
    step = (end - first_test) / folds
    return [
        (first_test + step * index, first_test + step * (index + 1))
        for index in range(folds)
    ]


def _select_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    identities: pd.DataFrame,
    cooldown: int,
    config: SensitivityConfig,
) -> tuple[float, dict[str, Any]]:
    candidates = []
    for threshold in np.arange(0.05, 0.951, 0.01):
        metrics = _threshold_metrics(
            y_true,
            probabilities,
            float(threshold),
            config.target_drawdown,
            config.max_adverse_excursion,
            config.round_trip_cost,
            identities,
            cooldown_hours=cooldown,
        )
        if metrics["signals"] >= config.min_policy_signals:
            candidates.append(metrics)
    eligible = [
        row for row in candidates
        if row["recall"] >= config.min_recall_for_threshold
    ]
    pool = eligible or candidates
    if not pool:
        return 0.95, _threshold_metrics(
            y_true,
            probabilities,
            0.95,
            config.target_drawdown,
            config.max_adverse_excursion,
            config.round_trip_cost,
            identities,
            cooldown_hours=cooldown,
        )
    best = max(
        pool,
        key=lambda row: (
            row["conservative_ev"], row["precision"],
            row["recall"], row["threshold"],
        ),
    )
    return float(best["threshold"]), best


def _aggregate_decisions(
    records: pd.DataFrame, config: SensitivityConfig
) -> dict[str, Any]:
    signals = int(records["episode_signal"].sum())
    true_positives = int(
        ((records["episode_signal"]) & (records["label"] == 1)).sum()
    )
    positives = int((records["label"] == 1).sum())
    precision = true_positives / signals if signals else 0.0
    recall = true_positives / positives if positives else 0.0
    ev = (
        precision * config.target_drawdown
        - (1.0 - precision) * config.max_adverse_excursion
        - config.round_trip_cost
    )
    return {
        "signals": signals,
        "true_positives": true_positives,
        "false_positives": signals - true_positives,
        "precision": precision,
        "recall": recall,
        "conservative_ev": ev,
    }


def evaluate_development_variant(
    frame: pd.DataFrame,
    cooldown: int,
    config: SensitivityConfig,
) -> dict[str, Any]:
    embargo = pd.Timedelta(hours=config.embargo_hours)
    features = list(SERVING_FEATURE_COLS)
    folds: list[dict[str, Any]] = []
    records: list[pd.DataFrame] = []
    for fold_index, (test_start, test_end) in enumerate(
        _boundaries(frame, config.warmup_days, config.development_folds), start=1
    ):
        history = frame[frame["feature_time"] < test_start - embargo]
        fit, calibration, policy = _partition_history(history, embargo)
        test = frame[
            (frame["feature_time"] >= test_start)
            & (frame["feature_time"] < test_end)
        ]
        partitions = (fit, calibration, policy, test)
        if any(len(part) < 50 or part["label_value"].nunique() < 2 for part in partitions):
            continue
        model = _build_estimator("lightgbm", config.random_state + fold_index)
        model.fit(fit[features], fit["label_value"])
        calibrator = _calibrator(model, calibration, features, "isotonic")
        _, policy_probability = _predict_calibrated(
            model, calibrator, policy, features
        )
        threshold, policy_metrics = _select_threshold(
            policy["label_value"].to_numpy(),
            policy_probability,
            policy[["symbol", "feature_time"]],
            cooldown,
            config,
        )
        _, probability = _predict_calibrated(model, calibrator, test, features)
        decision = _threshold_metrics(
            test["label_value"].to_numpy(),
            probability,
            threshold,
            config.target_drawdown,
            config.max_adverse_excursion,
            config.round_trip_cost,
            test[["symbol", "feature_time"]],
            cooldown_hours=cooldown,
        )
        raw_signal = probability >= threshold
        episode_signal = np.zeros(len(test), dtype=bool)
        last_signal: dict[str, pd.Timestamp] = {}
        for index, row in enumerate(
            test[["symbol", "feature_time"]].itertuples(index=False)
        ):
            if not raw_signal[index]:
                continue
            previous = last_signal.get(row.symbol)
            when = pd.Timestamp(row.feature_time)
            if previous is None or when >= previous + pd.Timedelta(hours=cooldown):
                episode_signal[index] = True
                last_signal[row.symbol] = when
        record = test[["symbol", "feature_time", "label_value"]].copy()
        record.columns = ["symbol", "feature_time", "label"]
        record["probability"] = probability
        record["threshold"] = threshold
        record["episode_signal"] = episode_signal
        record["fold"] = fold_index
        records.append(record)
        folds.append(
            {
                "fold": fold_index,
                "test_start": test["feature_time"].min(),
                "test_end": test["feature_time"].max(),
                "test_rows": len(test),
                "test_positives": int(test["label_value"].sum()),
                "test_prevalence": float(test["label_value"].mean()),
                "threshold": threshold,
                "policy_metrics": policy_metrics,
                "probability_metrics": _probability_metrics(
                    test["label_value"].to_numpy(), probability
                ),
                "decision_metrics": decision,
            }
        )
    if not records:
        return {"folds": [], "summary": {"folds": 0}}
    joined = pd.concat(records, ignore_index=True)
    summary = _aggregate_decisions(joined, config)
    probability_metrics = _probability_metrics(
        joined["label"].to_numpy(), joined["probability"].to_numpy()
    )
    fold_evs = [row["decision_metrics"]["conservative_ev"] for row in folds]
    summary.update(probability_metrics)
    summary.update(
        {
            "folds": len(folds),
            "positive_ev_folds": sum(value > 0 for value in fold_evs),
            "mean_fold_ev": float(np.mean(fold_evs)),
            "std_fold_ev": float(np.std(fold_evs)),
            "min_fold_ev": float(np.min(fold_evs)),
            "selection_score": float(np.mean(fold_evs) - 0.5 * np.std(fold_evs)),
        }
    )
    return {"folds": folds, "summary": summary}


def evaluate_sealed_once(
    development: pd.DataFrame,
    sealed: pd.DataFrame,
    cooldown: int,
    config: SensitivityConfig,
) -> dict[str, Any]:
    """Fit on locked development data and touch the sealed holdout once."""

    embargo = pd.Timedelta(hours=config.embargo_hours)
    features = list(SERVING_FEATURE_COLS)
    fit, calibration, policy = _partition_history(development, embargo)
    model = _build_estimator("lightgbm", config.random_state + 1000)
    model.fit(fit[features], fit["label_value"])
    calibrator = _calibrator(model, calibration, features, "isotonic")
    _, policy_probability = _predict_calibrated(model, calibrator, policy, features)
    threshold, policy_metrics = _select_threshold(
        policy["label_value"].to_numpy(),
        policy_probability,
        policy[["symbol", "feature_time"]],
        cooldown,
        config,
    )
    _, probability = _predict_calibrated(model, calibrator, sealed, features)
    decision = _threshold_metrics(
        sealed["label_value"].to_numpy(),
        probability,
        threshold,
        config.target_drawdown,
        config.max_adverse_excursion,
        config.round_trip_cost,
        sealed[["symbol", "feature_time"]],
        cooldown_hours=cooldown,
    )
    return {
        "test_start": sealed["feature_time"].min(),
        "test_end": sealed["feature_time"].max(),
        "rows": len(sealed),
        "positives": int(sealed["label_value"].sum()),
        "prevalence": float(sealed["label_value"].mean()),
        "threshold": threshold,
        "policy_metrics": policy_metrics,
        "probability_metrics": _probability_metrics(
            sealed["label_value"].to_numpy(), probability
        ),
        "decision_metrics": decision,
    }


def run(config: SensitivityConfig) -> dict[str, Any]:
    materialized = materialize_dataset(config)
    base = load_dataset(config)
    unique_times = pd.Series(base["feature_time"].drop_duplicates().sort_values())
    sealed_index = int(math.floor(len(unique_times) * (1-config.sealed_fraction)))
    sealed_start = pd.Timestamp(unique_times.iloc[sealed_index])
    development_end = sealed_start - pd.Timedelta(hours=config.embargo_hours)
    development_base = base[base["feature_time"] < development_end]
    sealed_base = base[base["feature_time"] >= sealed_start]
    base_dev_positives = int(development_base["label_value"].sum())
    variants = []
    for pump_threshold in config.pump_thresholds:
        for liquidity_variant in config.liquidity_variants:
            development = _apply_universe(
                development_base, pump_threshold, liquidity_variant
            )
            universe = {
                "pump_threshold": pump_threshold,
                "liquidity_variant": liquidity_variant,
                "rows": len(development),
                "symbols": int(development["symbol"].nunique()),
                "positives": int(development["label_value"].sum()),
                "prevalence": float(development["label_value"].mean()),
                "row_coverage_vs_base": len(development) / len(development_base),
                "positive_coverage_vs_base": (
                    int(development["label_value"].sum()) / base_dev_positives
                    if base_dev_positives else 0.0
                ),
            }
            for cooldown in config.cooldown_hours:
                evaluated = evaluate_development_variant(
                    development, cooldown, config
                )
                variants.append(
                    {
                        "pump_threshold": pump_threshold,
                        "liquidity_variant": liquidity_variant,
                        "cooldown_hours": cooldown,
                        "universe": universe,
                        "development": evaluated,
                    }
                )
    eligible = [
        item for item in variants
        if item["development"]["summary"].get("folds") == config.development_folds
        and item["development"]["summary"].get("signals", 0) >= 30
    ]
    if not eligible:
        raise RuntimeError("no development variant has complete folds and 30 signals")
    selected = max(
        eligible,
        key=lambda item: (
            item["development"]["summary"]["selection_score"],
            item["development"]["summary"]["positive_ev_folds"],
            item["development"]["summary"]["precision"],
            item["development"]["summary"]["signals"],
        ),
    )
    selected_dev = _apply_universe(
        development_base,
        selected["pump_threshold"],
        selected["liquidity_variant"],
    )
    selected_sealed = _apply_universe(
        sealed_base,
        selected["pump_threshold"],
        selected["liquidity_variant"],
    )
    sealed_result = evaluate_sealed_once(
        selected_dev, selected_sealed, selected["cooldown_hours"], config
    )
    report = {
        "experiment": "universe_policy_sensitivity_v2",
        "research_only": True,
        "live_configuration_changed": False,
        "generated_at": datetime.now(timezone.utc),
        "label_contract": {
            "target_drawdown": config.target_drawdown,
            "max_adverse_excursion": config.max_adverse_excursion,
            "horizon_hours": config.horizon_hours,
            "same_bar": "excluded",
            "cost": config.round_trip_cost,
        },
        "selection_protocol": {
            "development_only_selection": True,
            "sealed_holdout_evaluated_once": True,
            "embargo_hours": config.embargo_hours,
            "development_folds": config.development_folds,
            "selection_metric": "mean_fold_ev - 0.5 * std_fold_ev",
            "liquidity_proxy": (
                "cross-sectional percentile of trailing 24h quote volume; PIT"
            ),
            "market_cap_used": False,
        },
        "config": asdict(config),
        "materialized": materialized,
        "time_split": {
            "development_start": development_base["feature_time"].min(),
            "development_end": development_base["feature_time"].max(),
            "sealed_start": sealed_base["feature_time"].min(),
            "sealed_end": sealed_base["feature_time"].max(),
        },
        "development_variants": variants,
        "selected_on_development": {
            key: selected[key]
            for key in ("pump_threshold", "liquidity_variant", "cooldown_hours", "universe", "development")
        },
        "sealed_holdout": sealed_result,
    }
    config.output_json.parent.mkdir(parents=True, exist_ok=True)
    config.output_json.write_text(
        json.dumps(report, indent=2, default=_jsonable), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rebuild-dataset", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    config = SensitivityConfig(
        rebuild_dataset=args.rebuild_dataset,
        output_json=args.output or SensitivityConfig.output_json,
    )
    report = run(config)
    selected = report["selected_on_development"]
    sealed = report["sealed_holdout"]["decision_metrics"]
    print(json.dumps({
        "selected": {
            "pump_threshold": selected["pump_threshold"],
            "liquidity_variant": selected["liquidity_variant"],
            "cooldown_hours": selected["cooldown_hours"],
        },
        "sealed": sealed,
        "output": str(config.output_json),
    }, indent=2))


if __name__ == "__main__":
    main()
