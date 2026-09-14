"""Locked historical search and untouched August forward evaluation for 48h labels.

Stage ``lock`` uses only the pre-August PIT cache. Stage ``evaluate`` loads the
immutable research bundle, materializes August outcomes, and reports them once.
Nothing in this script can update the live configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from dao_vang.experiments.calibration import fit_probability_calibrator
from dao_vang.experiments.train_distribution_v2 import (
    SERVING_FEATURE_COLS,
    _partition_history,
    _probability_metrics,
)

DERIVED_FEATURES = (
    "pump_age_hours",
    "ret24h_peak_6h",
    "ret24h_off_peak_6h",
    "distance_high_change_1h",
    "short_long_momentum_spread",
    "reversal_pressure",
)


@dataclass(frozen=True)
class Config:
    history_db: Path = Path("artifacts/universe_policy_v2_48h.duckdb")
    live_db: Path = Path("data_live/live.duckdb")
    market_db: Path = Path(r"D:\Quant-trading\data_lake\quant_master.duckdb")
    forward_db: Path = Path("artifacts/forward48_aug_model_dataset.duckdb")
    lock_json: Path = Path("artifacts/forward48_aug_model_lock.json")
    bundle_path: Path = Path("artifacts/forward48_aug_model_bundle.joblib")
    report_json: Path = Path("artifacts/forward48_aug_model_report.json")
    events_csv: Path = Path("artifacts/forward48_aug_model_events.csv")
    history_table: str = "universe_policy_candidates_v2"
    forward_table: str = "forward48_aug_candidates"
    forward_start: str = "2026-08-01T00:00:00+00:00"
    forward_end: str = "2026-09-01T00:00:00+00:00"
    pump_threshold: float = 0.15
    base_pump_threshold: float = 0.10
    sample_minute: int = 4
    horizon_hours: int = 48
    target_drawdown: float = 0.20
    max_adverse_excursion: float = 0.16
    round_trip_cost: float = 0.002
    cooldown_hours: int = 24
    embargo_hours: int = 48
    warmup_days: int = 90
    development_folds: int = 3
    random_state: int = 42
    rebuild_forward: bool = False


VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "name": "reference_lgb_25",
        "family": "lightgbm",
        "features": "serving",
        "params": {
            "n_estimators": 300,
            "learning_rate": 0.03,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 80,
            "reg_alpha": 0.0,
            "reg_lambda": 1.0,
        },
    },
    {
        "name": "augmented_lgb_regularized",
        "family": "lightgbm",
        "features": "augmented",
        "params": {
            "n_estimators": 350,
            "learning_rate": 0.025,
            "max_depth": 3,
            "num_leaves": 7,
            "min_child_samples": 100,
            "reg_alpha": 1.0,
            "reg_lambda": 5.0,
        },
    },
    {
        "name": "augmented_lgb_reference",
        "family": "lightgbm",
        "features": "augmented",
        "params": {
            "n_estimators": 300,
            "learning_rate": 0.03,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 80,
            "reg_alpha": 0.0,
            "reg_lambda": 1.0,
        },
    },
    {
        "name": "augmented_logistic",
        "family": "logistic",
        "features": "augmented",
        "params": {"C": 0.1},
    },
)


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
    raise TypeError(type(value).__name__)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sql_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "/").replace("'", "''")


def _augment(frame: pd.DataFrame, threshold: float) -> pd.DataFrame:
    """Past-only episode/run-up/reversal features using hourly snapshots."""

    result = frame.sort_values(["symbol", "feature_time"]).copy()
    chunks: list[pd.DataFrame] = []
    for _, group in result.groupby("symbol", sort=False):
        group = group.copy()
        times = pd.to_datetime(group["feature_time"], utc=True)
        gap = times.diff().dt.total_seconds().div(3600)
        above = group["price_ret_24h"].ge(threshold)
        reset = (~above) | gap.gt(1.5) | gap.isna()
        episode = reset.cumsum()
        first = times.groupby(episode).transform("min")
        age = (times - first).dt.total_seconds().div(3600)
        group["pump_age_hours"] = age.where(above, 0.0).clip(0, 48)
        group["ret24h_peak_6h"] = group["price_ret_24h"].rolling(7, min_periods=1).max()
        group["ret24h_off_peak_6h"] = group["price_ret_24h"] - group["ret24h_peak_6h"]
        group["distance_high_change_1h"] = group["distance_from_high_24h"].diff()
        group["short_long_momentum_spread"] = (
            group["price_ret_1h"] - group["price_ret_4h"] / 4.0
        )
        group["reversal_pressure"] = (
            -group["price_ret_5m"].clip(upper=0)
            - group["price_ret_1h"].clip(upper=0)
            - group["momentum_deceleration_4h"].clip(upper=0)
        )
        chunks.append(group)
    return (
        pd.concat(chunks, ignore_index=True)
        .sort_values(["feature_time", "symbol"])
        .reset_index(drop=True)
    )


def _load_history(config: Config) -> pd.DataFrame:
    conn = duckdb.connect(str(config.history_db), read_only=True)
    conn.execute("PRAGMA disable_progress_bar")
    frame = conn.execute(
        f"SELECT * FROM {config.history_table} WHERE label_value IS NOT NULL "
        "ORDER BY feature_time, symbol"
    ).fetchdf()
    conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["label_value"] = frame["label_value"].astype("int8")
    return _augment(frame, config.pump_threshold)


def _build_model(spec: dict[str, Any], seed: int) -> Pipeline:
    if spec["family"] == "lightgbm":
        estimator: Any = lgb.LGBMClassifier(
            random_state=seed,
            subsample=0.85,
            colsample_bytree=0.85,
            deterministic=True,
            force_col_wise=True,
            verbosity=-1,
            n_jobs=4,
            **spec["params"],
        )
        return Pipeline(
            [
                ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
                ("estimator", estimator),
            ]
        )
    estimator = LogisticRegression(
        max_iter=2000, solver="lbfgs", random_state=seed, **spec["params"]
    )
    return Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            ("estimator", estimator),
        ]
    )


def _features(spec: dict[str, Any]) -> list[str]:
    cols = list(SERVING_FEATURE_COLS)
    if spec["features"] == "augmented":
        cols.extend(DERIVED_FEATURES)
    return cols


def _boundaries(
    frame: pd.DataFrame, config: Config
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    start = frame["feature_time"].min() + pd.Timedelta(days=config.warmup_days)
    end = frame["feature_time"].max() + pd.Timedelta(microseconds=1)
    points = pd.date_range(start, end, periods=config.development_folds + 1)
    return [(points[i], points[i + 1]) for i in range(config.development_folds)]


def _episode_mask(frame: pd.DataFrame, raw: np.ndarray, cooldown: int) -> np.ndarray:
    selected = np.zeros(len(frame), dtype=bool)
    last: dict[str, pd.Timestamp] = {}
    for index, row in enumerate(
        frame[["symbol", "feature_time"]].itertuples(index=False)
    ):
        if not raw[index]:
            continue
        when = pd.Timestamp(row.feature_time)
        previous = last.get(row.symbol)
        if previous is None or when >= previous + pd.Timedelta(hours=cooldown):
            selected[index] = True
            last[row.symbol] = when
    return selected


def _decision_metrics(
    frame: pd.DataFrame, probability: np.ndarray, threshold: float, config: Config
) -> dict[str, Any]:
    selected = _episode_mask(frame, probability >= threshold, config.cooldown_hours)
    y = frame["label_value"].to_numpy()
    signals = int(selected.sum())
    hits = int(((y == 1) & selected).sum())
    positives = int((y == 1).sum())
    precision = hits / signals if signals else 0.0
    recall = hits / positives if positives else 0.0
    ev = (
        precision * config.target_drawdown
        - (1 - precision) * config.max_adverse_excursion
        - config.round_trip_cost
    )
    return {
        "threshold": threshold,
        "signals": signals,
        "true_positives": hits,
        "false_positives": signals - hits,
        "precision": precision,
        "recall": recall,
        "conservative_ev": ev,
    }


def _wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return 0.0, 1.0
    p = successes / total
    den = 1 + z * z / total
    centre = p + z * z / (2 * total)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total)
    return max(0.0, (centre - margin) / den), min(1.0, (centre + margin) / den)


def _select_threshold(
    frame: pd.DataFrame, probability: np.ndarray, config: Config
) -> tuple[float, dict[str, Any]]:
    rows = []
    for threshold in np.arange(0.05, 0.951, 0.01):
        metrics = _decision_metrics(frame, probability, float(threshold), config)
        if metrics["signals"] < 20:
            continue
        lower, upper = _wilson(metrics["true_positives"], metrics["signals"])
        metrics.update(
            {
                "wilson95_lower": lower,
                "wilson95_upper": upper,
                "wilson_ev": lower * config.target_drawdown
                - (1 - lower) * config.max_adverse_excursion
                - config.round_trip_cost,
            }
        )
        rows.append(metrics)
    if not rows:
        return 0.95, _decision_metrics(frame, probability, 0.95, config)
    best = max(
        rows, key=lambda row: (row["wilson_ev"], row["conservative_ev"], row["signals"])
    )
    return float(best["threshold"]), best


def _fit_calibrate(
    fit: pd.DataFrame,
    calibration: pd.DataFrame,
    spec: dict[str, Any],
    method: str,
    seed: int,
) -> tuple[Any, Any, list[str]]:
    features = _features(spec)
    model = _build_model(spec, seed)
    model.fit(fit[features], fit["label_value"])
    raw = model.predict_proba(calibration[features])[:, 1]
    calibrator = fit_probability_calibrator(
        raw,
        calibration["label_value"].to_numpy(),
        method=method,
        calibrator_id=f"forward48_{method}_{spec['name']}",
    )
    return model, calibrator, features


def _predict(
    model: Any, calibrator: Any, frame: pd.DataFrame, features: list[str]
) -> np.ndarray:
    raw = model.predict_proba(frame[features])[:, 1]
    return np.asarray(calibrator.predict(raw), dtype=float)


def lock(config: Config) -> dict[str, Any]:
    """Search only historical development folds and persist an immutable lock."""

    history_all = _load_history(config)
    history = history_all[history_all["price_ret_24h"] >= config.pump_threshold].copy()
    embargo = pd.Timedelta(hours=config.embargo_hours)
    candidates: list[dict[str, Any]] = []
    for spec in VARIANTS:
        for method in ("isotonic", "platt"):
            fold_rows = []
            for fold, (start, end) in enumerate(_boundaries(history, config), 1):
                prior = history[history["feature_time"] < start - embargo]
                fit, calibration, policy = _partition_history(prior, embargo)
                test = history[
                    (history["feature_time"] >= start) & (history["feature_time"] < end)
                ]
                if any(
                    len(part) < 50 or part["label_value"].nunique() < 2
                    for part in (fit, calibration, policy, test)
                ):
                    continue
                model, calibrator, features = _fit_calibrate(
                    fit, calibration, spec, method, config.random_state + fold
                )
                policy_probability = _predict(model, calibrator, policy, features)
                threshold, policy_metrics = _select_threshold(
                    policy, policy_probability, config
                )
                probability = _predict(model, calibrator, test, features)
                decision = _decision_metrics(test, probability, threshold, config)
                fold_rows.append(
                    {
                        "fold": fold,
                        "test_start": test["feature_time"].min(),
                        "test_end": test["feature_time"].max(),
                        "threshold": threshold,
                        "policy": policy_metrics,
                        "decision": decision,
                        "probability": _probability_metrics(
                            test["label_value"].to_numpy(), probability
                        ),
                    }
                )
            if len(fold_rows) != config.development_folds:
                continue
            signals = sum(row["decision"]["signals"] for row in fold_rows)
            hits = sum(row["decision"]["true_positives"] for row in fold_rows)
            precision = hits / signals if signals else 0.0
            evs = [row["decision"]["conservative_ev"] for row in fold_rows]
            lower, upper = _wilson(hits, signals)
            candidates.append(
                {
                    "candidate": f"{spec['name']}__{method}",
                    "spec": spec,
                    "calibration": method,
                    "folds": fold_rows,
                    "signals": signals,
                    "hits": hits,
                    "precision": precision,
                    "wilson95": [lower, upper],
                    "mean_fold_ev": float(np.mean(evs)),
                    "std_fold_ev": float(np.std(evs)),
                    "min_fold_ev": float(np.min(evs)),
                    "positive_ev_folds": sum(x > 0 for x in evs),
                    "selection_score": float(np.mean(evs) - 0.5 * np.std(evs)),
                }
            )
    eligible = [row for row in candidates if row["signals"] >= 30]
    if not eligible:
        raise RuntimeError("no historical candidate has at least 30 episode signals")
    champion = max(
        eligible,
        key=lambda row: (
            row["selection_score"],
            row["positive_ev_folds"],
            row["precision"],
            row["signals"],
        ),
    )
    fit, calibration, policy = _partition_history(history, embargo)
    model, calibrator, features = _fit_calibrate(
        fit,
        calibration,
        champion["spec"],
        champion["calibration"],
        config.random_state + 1000,
    )
    probability = _predict(model, calibrator, policy, features)
    threshold, policy_metrics = _select_threshold(policy, probability, config)
    bundle = {
        "model": model,
        "calibrator": calibrator,
        "features": features,
        "threshold": threshold,
        "champion": champion["candidate"],
        "config": asdict(config),
    }
    config.bundle_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, config.bundle_path)
    report = {
        "artifact": "forward48_aug_model_lock",
        "generated_at": datetime.now(timezone.utc),
        "status": "research_only",
        "live_configuration_changed": False,
        "forward_data_opened": False,
        "selection_data_end": history["feature_time"].max(),
        "history": {
            "rows": len(history),
            "positives": int(history["label_value"].sum()),
            "symbols": int(history["symbol"].nunique()),
            "start": history["feature_time"].min(),
            "end": history["feature_time"].max(),
        },
        "config": asdict(config),
        "variants": candidates,
        "locked_champion": champion,
        "locked_threshold": threshold,
        "policy_metrics": policy_metrics,
        "feature_cols": features,
        "derived_feature_contract": {
            "past_only": True,
            "runtime_compatible": True,
            "note": "derived from current/past hourly serving snapshots; no future market values",
        },
        "bundle_sha256": _sha256(config.bundle_path),
    }
    config.lock_json.write_text(
        json.dumps(report, indent=2, default=_jsonable), encoding="utf-8"
    )
    return report


def materialize_forward(config: Config) -> dict[str, Any]:
    config.forward_db.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(config.forward_db))
    conn.execute("PRAGMA disable_progress_bar")
    conn.execute("SET threads=4")
    conn.execute(f"ATTACH '{_sql_path(config.live_db)}' AS live (READ_ONLY)")
    conn.execute(f"ATTACH '{_sql_path(config.market_db)}' AS market (READ_ONLY)")
    exists = conn.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema='main' AND table_name=?",
        [config.forward_table],
    ).fetchone()[0]
    if config.rebuild_forward or not exists:
        cols = ",\n".join(f"f.{col}" for col in SERVING_FEATURE_COLS)
        conn.execute(f"DROP TABLE IF EXISTS {config.forward_table}")
        conn.execute(f"""
        CREATE TABLE {config.forward_table} AS
        WITH candidates AS (
          SELECT f.feature_time, f.symbol, k.close AS entry_price, {cols}
          FROM live.main.feature_results f
          INNER JOIN live.main.kline k ON k.symbol=f.symbol AND k.close_time=f.feature_time
          WHERE f.feature_time >= TIMESTAMPTZ '{config.forward_start}'
            AND f.feature_time < TIMESTAMPTZ '{config.forward_end}'
            AND f.price_ret_24h >= {config.base_pump_threshold}
            AND EXTRACT(MINUTE FROM f.feature_time)={config.sample_minute}
        ), outcomes AS (
          SELECT c.symbol,c.feature_time,count(k.close_time) future_bars,max(k.close_time) last_future_time,
            min(k.close_time) FILTER (WHERE k.low<=c.entry_price*{1 - config.target_drawdown}) target_time,
            min(k.close_time) FILTER (WHERE k.high>=c.entry_price*{1 + config.max_adverse_excursion}) stop_time
          FROM candidates c LEFT JOIN live.main.kline k
            ON k.symbol=c.symbol AND k.close_time>c.feature_time
            AND k.close_time<=c.feature_time+INTERVAL '{config.horizon_hours}' HOUR
          GROUP BY c.symbol,c.feature_time
        )
        SELECT c.*,o.future_bars,o.target_time,o.stop_time,
          CASE WHEN o.future_bars<552 OR o.last_future_time<c.feature_time+INTERVAL '48' HOUR-INTERVAL '5' MINUTE THEN 'incomplete_future'
               WHEN o.target_time IS NOT NULL AND o.target_time=o.stop_time THEN 'ambiguous_same_bar' END exclusion_reason,
          CASE WHEN o.future_bars<552 OR o.last_future_time<c.feature_time+INTERVAL '48' HOUR-INTERVAL '5' MINUTE THEN NULL
               WHEN o.target_time IS NOT NULL AND o.target_time=o.stop_time THEN NULL
               WHEN o.target_time IS NOT NULL AND (o.stop_time IS NULL OR o.target_time<o.stop_time) THEN 1 ELSE 0 END label_value
        FROM candidates c INNER JOIN outcomes o USING(symbol,feature_time)
        ORDER BY feature_time,symbol
        """)
    cursor = conn.execute(
        f"SELECT count(*),count(label_value),sum(label_value=1),count(distinct symbol),min(feature_time),max(feature_time),sum(exclusion_reason='ambiguous_same_bar'),sum(exclusion_reason='incomplete_future') FROM {config.forward_table}"
    )
    values = cursor.fetchone()
    keys = (
        "rows",
        "labeled",
        "positives",
        "symbols",
        "start",
        "end",
        "ambiguous",
        "incomplete",
    )
    stats = dict(zip(keys, values))
    feature_filter = f"""f.feature_time >= TIMESTAMPTZ '{config.forward_start}'
      AND f.feature_time < TIMESTAMPTZ '{config.forward_end}'
      AND f.price_ret_24h >= {config.pump_threshold}
      AND EXTRACT(MINUTE FROM f.feature_time)={config.sample_minute}"""
    stats["coverage_audit_pump15"] = {
        "feature_candidates": conn.execute(
            "SELECT count(*) FROM live.main.feature_results f WHERE " + feature_filter
        ).fetchone()[0],
        "exact_live_kline": conn.execute(
            "SELECT count(*) FROM live.main.feature_results f "
            "JOIN live.main.kline k ON k.symbol=f.symbol AND k.close_time=f.feature_time "
            "WHERE " + feature_filter
        ).fetchone()[0],
        "exact_quant_master": conn.execute(
            "SELECT count(*) FROM live.main.feature_results f "
            "JOIN market.main.klines_5m k ON k.symbol=f.symbol AND k.close_time=f.feature_time "
            "WHERE " + feature_filter
        ).fetchone()[0],
    }
    conn.close()
    return stats


def evaluate(config: Config) -> dict[str, Any]:
    lock_report = json.loads(config.lock_json.read_text(encoding="utf-8"))
    expected = lock_report["bundle_sha256"]
    actual = _sha256(config.bundle_path)
    if actual != expected:
        raise RuntimeError("research bundle hash differs from pre-forward lock")
    stats = materialize_forward(config)
    conn = duckdb.connect(str(config.forward_db), read_only=True)
    frame = conn.execute(
        f"SELECT * FROM {config.forward_table} WHERE label_value IS NOT NULL "
        "ORDER BY feature_time,symbol"
    ).fetchdf()
    conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["label_value"] = frame["label_value"].astype("int8")
    frame = _augment(frame, config.pump_threshold)
    frame = frame[frame["price_ret_24h"] >= config.pump_threshold].reset_index(
        drop=True
    )
    bundle = joblib.load(config.bundle_path)
    probability = _predict(
        bundle["model"], bundle["calibrator"], frame, bundle["features"]
    )
    selected = _episode_mask(
        frame, probability >= bundle["threshold"], config.cooldown_hours
    )
    decisions = _decision_metrics(frame, probability, bundle["threshold"], config)
    lower, upper = _wilson(decisions["true_positives"], decisions["signals"])
    decisions.update(
        {
            "precision_wilson95_lower": lower,
            "precision_wilson95_upper": upper,
            "wilson95_conservative_ev": lower * config.target_drawdown
            - (1 - lower) * config.max_adverse_excursion
            - config.round_trip_cost,
        }
    )
    events = frame[
        [
            "symbol",
            "feature_time",
            "entry_price",
            "label_value",
            "target_time",
            "stop_time",
        ]
    ].copy()
    events["probability"] = probability
    events["threshold"] = bundle["threshold"]
    events["episode_signal"] = selected
    signal_events = events[events["episode_signal"]].copy()
    signal_events["week"] = (
        signal_events["feature_time"].dt.to_period("W-SUN").astype(str)
    )
    weekly = []
    for week, group in signal_events.groupby("week"):
        hits = int(group["label_value"].sum())
        signals = len(group)
        p = hits / signals if signals else 0.0
        lo, hi = _wilson(hits, signals)
        weekly.append(
            {
                "week": week,
                "signals": signals,
                "hits": hits,
                "precision": p,
                "wilson95": [lo, hi],
                "conservative_ev": p * config.target_drawdown
                - (1 - p) * config.max_adverse_excursion
                - config.round_trip_cost,
            }
        )
    config.events_csv.parent.mkdir(parents=True, exist_ok=True)
    events.to_csv(config.events_csv, index=False)
    report = {
        "artifact": "forward48_aug_model_evaluation",
        "generated_at": datetime.now(timezone.utc),
        "status": "research_only",
        "live_configuration_changed": False,
        "lock": {
            "path": config.lock_json,
            "bundle_sha256_expected": expected,
            "bundle_sha256_actual": actual,
            "champion": bundle["champion"],
            "threshold": bundle["threshold"],
        },
        "protocol": {
            "forward_start": config.forward_start,
            "forward_end": config.forward_end,
            "target_drawdown": config.target_drawdown,
            "stop_mae": config.max_adverse_excursion,
            "horizon_hours": config.horizon_hours,
            "same_bar": "excluded",
            "cooldown_hours": config.cooldown_hours,
            "cost": config.round_trip_cost,
            "forward_used_for_selection": False,
        },
        "data_provenance": {
            "history_db": config.history_db,
            "live_feature_db": config.live_db,
            "market_db": config.market_db,
            "entry_and_outcome_source": "data_live/live.duckdb::kline",
            "quant_master_role": (
                "coverage audit only; exact August symbol/time coverage was 1.98%, "
                "so it was not used as the denominator"
            ),
            "materialized": stats,
        },
        "forward_universe": {
            "rows": len(frame),
            "positives": int(frame["label_value"].sum()),
            "prevalence": float(frame["label_value"].mean()),
            "symbols": int(frame["symbol"].nunique()),
        },
        "probability_metrics": _probability_metrics(
            frame["label_value"].to_numpy(), probability
        ),
        "decision_metrics": decisions,
        "per_week": weekly,
        "promotion": {
            "eligible": bool(
                decisions["signals"] >= 100
                and decisions["precision"] >= 0.50
                and lower > 0.45
                and sum(x["conservative_ev"] > 0 for x in weekly) >= 3
            ),
            "minimum_signals": 100,
            "minimum_precision": 0.50,
            "wilson_lower_above_break_even": lower > 0.45,
            "positive_weeks": sum(x["conservative_ev"] > 0 for x in weekly),
        },
    }
    config.report_json.write_text(
        json.dumps(report, indent=2, default=_jsonable), encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("lock", "evaluate"))
    parser.add_argument("--rebuild-forward", action="store_true")
    args = parser.parse_args()
    config = Config(rebuild_forward=args.rebuild_forward)
    result = lock(config) if args.stage == "lock" else evaluate(config)
    if args.stage == "lock":
        print(
            json.dumps(
                {
                    "champion": result["locked_champion"]["candidate"],
                    "threshold": result["locked_threshold"],
                    "bundle_sha256": result["bundle_sha256"],
                },
                indent=2,
            )
        )
    else:
        print(
            json.dumps(
                {
                    "lock": result["lock"],
                    "forward_universe": result["forward_universe"],
                    "probability_metrics": result["probability_metrics"],
                    "decision_metrics": result["decision_metrics"],
                    "promotion": result["promotion"],
                },
                indent=2,
                default=_jsonable,
            )
        )


if __name__ == "__main__":
    main()
