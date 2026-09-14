"""Nested model-variant search for ``distribution_short_v2``.

The first N-1 expanding chronological folds are development validation folds.
Only those folds may choose the model, calibration method and threshold policy.
The last fold is opened once for the locked champion and is never used for
selection.  Every boundary keeps the 24-hour label embargo used by the serving
trainer.
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
    V2TrainingConfig,
    _partition_history,
    _probability_metrics,
    _threshold_metrics,
    _walk_forward_boundaries,
    load_v2_dataset,
    select_threshold,
)


@dataclass(frozen=True)
class BaseVariant:
    name: str
    family: str
    params: dict[str, Any]


BASE_VARIANTS = (
    BaseVariant(
        "logistic_l2_c0_1",
        "logistic",
        {"C": 0.1, "class_weight": None},
    ),
    BaseVariant(
        "logistic_l2_c1_balanced",
        "logistic",
        {"C": 1.0, "class_weight": "balanced"},
    ),
    BaseVariant(
        "lgb_depth3_leaves7_reg5",
        "lightgbm",
        {
            "n_estimators": 300,
            "learning_rate": 0.03,
            "max_depth": 3,
            "num_leaves": 7,
            "min_child_samples": 100,
            "reg_alpha": 1.0,
            "reg_lambda": 5.0,
            "class_weight": None,
        },
    ),
    BaseVariant(
        "lgb_depth4_leaves15_reference",
        "lightgbm",
        {
            "n_estimators": 300,
            "learning_rate": 0.03,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 80,
            "reg_alpha": 0.0,
            "reg_lambda": 1.0,
            "class_weight": None,
        },
    ),
    BaseVariant(
        "lgb_depth4_leaves15_reg5_balanced",
        "lightgbm",
        {
            "n_estimators": 400,
            "learning_rate": 0.025,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 120,
            "reg_alpha": 1.0,
            "reg_lambda": 5.0,
            "class_weight": "balanced",
        },
    ),
    BaseVariant(
        "lgb_depth5_leaves31_reg3_balanced",
        "lightgbm",
        {
            "n_estimators": 350,
            "learning_rate": 0.025,
            "max_depth": 5,
            "num_leaves": 31,
            "min_child_samples": 60,
            "reg_alpha": 0.5,
            "reg_lambda": 3.0,
            "class_weight": "balanced",
        },
    ),
)

CALIBRATION_METHODS = ("isotonic", "platt")
THRESHOLD_POLICIES = ("point_ev", "wilson95_ev")


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


def _build_model(variant: BaseVariant, seed: int) -> Pipeline:
    if variant.family == "logistic":
        estimator: Any = LogisticRegression(
            max_iter=2000,
            solver="lbfgs",
            random_state=seed,
            **variant.params,
        )
        steps = [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scaler", StandardScaler()),
            ("estimator", estimator),
        ]
    elif variant.family == "lightgbm":
        estimator = lgb.LGBMClassifier(
            random_state=seed,
            subsample=0.85,
            colsample_bytree=0.85,
            deterministic=True,
            force_col_wise=True,
            verbosity=-1,
            n_jobs=4,
            **variant.params,
        )
        steps = [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("estimator", estimator),
        ]
    else:
        raise ValueError(f"unsupported family: {variant.family}")
    return Pipeline(steps)


def _wilson_lower(successes: int, total: int, z: float = 1.96) -> float:
    if total <= 0:
        return 0.0
    p = successes / total
    denominator = 1.0 + z * z / total
    centre = p + z * z / (2.0 * total)
    margin = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * total)) / total)
    return max(0.0, (centre - margin) / denominator)


def _select_wilson_threshold(
    y: np.ndarray,
    probabilities: np.ndarray,
    config: V2TrainingConfig,
    identities: pd.DataFrame,
) -> tuple[float, dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for threshold in np.arange(0.05, 0.951, 0.01):
        row = _threshold_metrics(
            y,
            probabilities,
            float(threshold),
            config.target_drawdown,
            config.max_adverse_excursion,
            config.round_trip_cost,
            identities,
            cooldown_hours=24,
        )
        if row["signals"] < 20:
            continue
        lower = _wilson_lower(row["true_positives"], row["signals"])
        row["precision_wilson95_lower"] = lower
        row["wilson95_conservative_ev"] = (
            lower * config.target_drawdown
            - (1.0 - lower) * config.max_adverse_excursion
            - config.round_trip_cost
        )
        candidates.append(row)
    eligible = [row for row in candidates if row["recall"] >= 0.05]
    pool = eligible or candidates
    if not pool:
        fallback = _threshold_metrics(
            y,
            probabilities,
            0.95,
            config.target_drawdown,
            config.max_adverse_excursion,
            config.round_trip_cost,
            identities,
            cooldown_hours=24,
        )
        fallback["precision_wilson95_lower"] = 0.0
        fallback["wilson95_conservative_ev"] = -(
            config.max_adverse_excursion + config.round_trip_cost
        )
        return 0.95, fallback
    best = max(
        pool,
        key=lambda row: (
            row["wilson95_conservative_ev"],
            row["conservative_ev"],
            row["recall"],
            row["threshold"],
        ),
    )
    return float(best["threshold"]), best


def _choose_threshold(
    policy_name: str,
    y: np.ndarray,
    probabilities: np.ndarray,
    config: V2TrainingConfig,
    identities: pd.DataFrame,
) -> tuple[float, dict[str, Any]]:
    if policy_name == "point_ev":
        threshold, metrics = select_threshold(y, probabilities, config, identities)
        metrics = {**metrics, "selection_objective": "point_conservative_ev"}
        return threshold, metrics
    if policy_name == "wilson95_ev":
        threshold, metrics = _select_wilson_threshold(
            y, probabilities, config, identities
        )
        metrics = {**metrics, "selection_objective": "wilson95_conservative_ev"}
        return threshold, metrics
    raise ValueError(f"unsupported threshold policy: {policy_name}")


def _evaluate_decision(
    frame: pd.DataFrame,
    probabilities: np.ndarray,
    threshold: float,
    config: V2TrainingConfig,
) -> dict[str, Any]:
    return _threshold_metrics(
        frame["label_value"].to_numpy(dtype=int),
        probabilities,
        threshold,
        config.target_drawdown,
        config.max_adverse_excursion,
        config.round_trip_cost,
        frame[["symbol", "feature_time"]],
        cooldown_hours=24,
    )


def _aggregate_candidate(
    fold_rows: list[dict[str, Any]],
    config: V2TrainingConfig,
) -> dict[str, Any]:
    signals = sum(row["decision_metrics"]["signals"] for row in fold_rows)
    true_positives = sum(
        row["decision_metrics"]["true_positives"] for row in fold_rows
    )
    positives = sum(row["probability_metrics"]["positives"] for row in fold_rows)
    precision = true_positives / signals if signals else 0.0
    recall = true_positives / positives if positives else 0.0
    ev = (
        precision * config.target_drawdown
        - (1.0 - precision) * config.max_adverse_excursion
        - config.round_trip_cost
    )
    wilson = _wilson_lower(true_positives, signals)
    wilson_ev = (
        wilson * config.target_drawdown
        - (1.0 - wilson) * config.max_adverse_excursion
        - config.round_trip_cost
    )
    total_rows = sum(row["probability_metrics"]["rows"] for row in fold_rows)
    weighted_ap = sum(
        row["probability_metrics"]["average_precision"]
        * row["probability_metrics"]["rows"]
        for row in fold_rows
    ) / total_rows
    weighted_brier = sum(
        row["probability_metrics"]["brier"]
        * row["probability_metrics"]["rows"]
        for row in fold_rows
    ) / total_rows
    return {
        "development_folds": len(fold_rows),
        "rows": total_rows,
        "positives": positives,
        "signals": signals,
        "true_positives": true_positives,
        "precision": precision,
        "precision_wilson95_lower": wilson,
        "recall": recall,
        "average_precision_weighted": weighted_ap,
        "brier_weighted": weighted_brier,
        "conservative_ev": ev,
        "wilson95_conservative_ev": wilson_ev,
        "positive_ev_folds": sum(
            row["decision_metrics"]["conservative_ev"] > 0 for row in fold_rows
        ),
    }


def _candidate_key(base: str, calibration: str, threshold_policy: str) -> str:
    return f"{base}__{calibration}__{threshold_policy}"


def _fit_fold_models(
    fit: pd.DataFrame,
    calibration: pd.DataFrame,
    policy: pd.DataFrame,
    evaluation: pd.DataFrame,
    fold_index: int,
    config: V2TrainingConfig,
) -> dict[str, dict[str, Any]]:
    columns = list(SERVING_FEATURE_COLS)
    output: dict[str, dict[str, Any]] = {}
    for base in BASE_VARIANTS:
        model = _build_model(base, config.random_state + fold_index)
        model.fit(fit[columns], fit["label_value"])
        raw_calibration = model.predict_proba(calibration[columns])[:, 1]
        raw_policy = model.predict_proba(policy[columns])[:, 1]
        raw_evaluation = model.predict_proba(evaluation[columns])[:, 1]
        for calibration_method in CALIBRATION_METHODS:
            calibrator = fit_probability_calibrator(
                raw_calibration,
                calibration["label_value"].to_numpy(dtype=int),
                method=calibration_method,
                calibrator_id=f"{calibration_method}_{base.name}_v2",
            )
            policy_probability = calibrator.transform(raw_policy)
            evaluation_probability = calibrator.transform(raw_evaluation)
            probability_metrics = _probability_metrics(
                evaluation["label_value"].to_numpy(dtype=int),
                evaluation_probability,
            )
            for threshold_policy in THRESHOLD_POLICIES:
                threshold, policy_selection = _choose_threshold(
                    threshold_policy,
                    policy["label_value"].to_numpy(dtype=int),
                    policy_probability,
                    config,
                    policy[["symbol", "feature_time"]],
                )
                decision_metrics = _evaluate_decision(
                    evaluation, evaluation_probability, threshold, config
                )
                key = _candidate_key(
                    base.name, calibration_method, threshold_policy
                )
                output[key] = {
                    "base_variant": base.name,
                    "family": base.family,
                    "model_params": base.params,
                    "calibration": calibration_method,
                    "threshold_policy": threshold_policy,
                    "threshold": threshold,
                    "policy_selection": policy_selection,
                    "probability_metrics": probability_metrics,
                    "decision_metrics": decision_metrics,
                }
    return output


def _partition_for_boundary(
    frame: pd.DataFrame,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    config: V2TrainingConfig,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
    embargo = pd.Timedelta(hours=config.embargo_hours)
    history = frame[frame["feature_time"] < test_start - embargo]
    fit, calibration, policy = _partition_history(history, embargo)
    test = frame[
        (frame["feature_time"] >= test_start)
        & (frame["feature_time"] < test_end)
    ]
    parts = {"fit": fit, "calibration": calibration, "policy": policy, "test": test}
    if any(len(part) < 50 or part["label_value"].nunique() < 2 for part in parts.values()):
        raise ValueError(f"insufficient partition at test_start={test_start}")
    audit = {
        "fit_start": fit["feature_time"].min(),
        "fit_end": fit["feature_time"].max(),
        "calibration_start": calibration["feature_time"].min(),
        "calibration_end": calibration["feature_time"].max(),
        "policy_start": policy["feature_time"].min(),
        "policy_end": policy["feature_time"].max(),
        "test_start": test["feature_time"].min(),
        "test_end": test["feature_time"].max(),
        "rows": {name: len(part) for name, part in parts.items()},
        "embargo_hours": config.embargo_hours,
    }
    return parts, audit


def run_search(dataset_db: Path, output_dir: Path) -> dict[str, Any]:
    config = V2TrainingConfig(
        dataset_db=dataset_db,
        freeze_if_passed=False,
        calibration_method="isotonic",
    )
    frame = load_v2_dataset(config).sort_values(
        ["feature_time", "symbol"], kind="mergesort"
    ).reset_index(drop=True)
    boundaries = _walk_forward_boundaries(frame, config)
    if len(boundaries) < 4:
        raise ValueError("four folds are required: three development plus holdout")

    development_boundaries = boundaries[:-1]
    holdout_boundary = boundaries[-1]
    folds_by_candidate: dict[str, list[dict[str, Any]]] = {}
    partition_audit: list[dict[str, Any]] = []
    for fold_index, (test_start, test_end) in enumerate(
        development_boundaries, start=1
    ):
        parts, audit = _partition_for_boundary(
            frame, test_start, test_end, config
        )
        partition_audit.append({"fold": fold_index, "role": "development", **audit})
        rows = _fit_fold_models(
            parts["fit"],
            parts["calibration"],
            parts["policy"],
            parts["test"],
            fold_index,
            config,
        )
        for key, row in rows.items():
            folds_by_candidate.setdefault(key, []).append(
                {"fold": fold_index, "role": "development_validation", **row}
            )

    leaderboard: list[dict[str, Any]] = []
    for key, fold_rows in folds_by_candidate.items():
        first = fold_rows[0]
        aggregate = _aggregate_candidate(fold_rows, config)
        leaderboard.append(
            {
                "candidate": key,
                "base_variant": first["base_variant"],
                "family": first["family"],
                "calibration": first["calibration"],
                "threshold_policy": first["threshold_policy"],
                **aggregate,
            }
        )
    leaderboard.sort(
        key=lambda row: (
            row["wilson95_conservative_ev"],
            row["positive_ev_folds"],
            row["average_precision_weighted"],
            -row["brier_weighted"],
        ),
        reverse=True,
    )
    champion_key = leaderboard[0]["candidate"]
    champion_spec = folds_by_candidate[champion_key][0]

    # The holdout is accessed only after the complete development leaderboard
    # has selected and locked the champion specification above.
    holdout_parts, holdout_audit = _partition_for_boundary(
        frame, holdout_boundary[0], holdout_boundary[1], config
    )
    partition_audit.append({"fold": len(boundaries), "role": "final_holdout", **holdout_audit})
    base = next(
        item for item in BASE_VARIANTS if item.name == champion_spec["base_variant"]
    )
    columns = list(SERVING_FEATURE_COLS)
    model = _build_model(base, config.random_state + 10_000)
    model.fit(holdout_parts["fit"][columns], holdout_parts["fit"]["label_value"])
    raw_cal = model.predict_proba(holdout_parts["calibration"][columns])[:, 1]
    calibrator = fit_probability_calibrator(
        raw_cal,
        holdout_parts["calibration"]["label_value"].to_numpy(dtype=int),
        method=champion_spec["calibration"],
        calibrator_id=f"locked_{champion_spec['calibration']}_{base.name}_v2",
    )
    policy_probability = calibrator.transform(
        model.predict_proba(holdout_parts["policy"][columns])[:, 1]
    )
    threshold, policy_selection = _choose_threshold(
        champion_spec["threshold_policy"],
        holdout_parts["policy"]["label_value"].to_numpy(dtype=int),
        policy_probability,
        config,
        holdout_parts["policy"][["symbol", "feature_time"]],
    )
    holdout_raw = model.predict_proba(holdout_parts["test"][columns])[:, 1]
    holdout_probability = calibrator.transform(holdout_raw)
    holdout_probability_metrics = _probability_metrics(
        holdout_parts["test"]["label_value"].to_numpy(dtype=int),
        holdout_probability,
    )
    holdout_decision = _evaluate_decision(
        holdout_parts["test"], holdout_probability, threshold, config
    )

    timestamp = datetime.now(timezone.utc)
    output_dir.mkdir(parents=True, exist_ok=True)
    run_stamp = timestamp.strftime("%Y%m%d_%H%M%S")
    report_path = output_dir / f"model_variants_{run_stamp}.json"
    leaderboard_path = output_dir / f"model_variants_{run_stamp}_leaderboard.csv"
    holdout_path = output_dir / f"model_variants_{run_stamp}_holdout.csv"
    bundle_path = output_dir / f"model_variants_{run_stamp}_research_bundle.joblib"

    holdout_export = holdout_parts["test"][
        ["symbol", "feature_time", "label_value"]
    ].copy()
    holdout_export["raw_probability"] = holdout_raw
    holdout_export["probability"] = holdout_probability
    holdout_export["threshold"] = threshold
    holdout_export["raw_signal"] = holdout_probability >= threshold
    holdout_export.to_csv(holdout_path, index=False)
    pd.DataFrame(leaderboard).to_csv(leaderboard_path, index=False)
    joblib.dump(
        {
            "research_only": True,
            "model": model,
            "calibrator": calibrator,
            "feature_cols": columns,
            "threshold": threshold,
            "candidate": champion_key,
            "label_version": "distribution_short_v2",
        },
        bundle_path,
    )

    holdout_break_even_precision = (
        config.max_adverse_excursion + config.round_trip_cost
    ) / (config.target_drawdown + config.max_adverse_excursion)
    report = {
        "artifact": "model_variants_distribution_short_v2_nested_search",
        "generated_at": timestamp,
        "status": "research_only",
        "production_config_changed": False,
        "selection_contract": {
            "feature_set": "serving_features_v1_25",
            "feature_count": len(columns),
            "label_version": "distribution_short_v2",
            "target_drawdown": config.target_drawdown,
            "max_adverse_excursion": config.max_adverse_excursion,
            "horizon_hours": config.horizon_hours,
            "round_trip_cost": config.round_trip_cost,
            "episode_cooldown_hours": 24,
            "split": "expanding_4fold; folds_1_to_3_development; fold_4_locked_holdout",
            "embargo_hours": config.embargo_hours,
            "hyperparameter_selection_data": "development_validation_folds_only",
            "threshold_selection_data": "policy_partition_only",
            "holdout_used_for_selection": False,
            "ranking_objective": "pooled_development_wilson95_conservative_ev",
            "break_even_precision": holdout_break_even_precision,
        },
        "dataset": {
            "path": str(dataset_db),
            "rows": len(frame),
            "positives": int(frame["label_value"].sum()),
            "prevalence": float(frame["label_value"].mean()),
            "symbols": int(frame["symbol"].nunique()),
            "start": frame["feature_time"].min(),
            "end": frame["feature_time"].max(),
        },
        "base_variants": [asdict(item) for item in BASE_VARIANTS],
        "calibration_methods": list(CALIBRATION_METHODS),
        "threshold_policies": list(THRESHOLD_POLICIES),
        "candidate_count": len(leaderboard),
        "partition_audit": partition_audit,
        "development_leaderboard": leaderboard,
        "development_folds": folds_by_candidate,
        "locked_champion": {
            "candidate": champion_key,
            "selected_before_holdout": True,
            "development_summary": leaderboard[0],
            "development_fold_metrics": folds_by_candidate[champion_key],
        },
        "final_holdout": {
            "fold": len(boundaries),
            "threshold": threshold,
            "policy_selection": policy_selection,
            "probability_metrics": holdout_probability_metrics,
            "decision_metrics": holdout_decision,
            "break_even_precision": holdout_break_even_precision,
            "positive_ev": holdout_decision["conservative_ev"] > 0,
        },
        "artifacts": {
            "report": str(report_path),
            "leaderboard_csv": str(leaderboard_path),
            "holdout_csv": str(holdout_path),
            "research_bundle": str(bundle_path),
        },
    }
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=_jsonable),
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dataset-db",
        type=Path,
        default=Path("artifacts/distribution_v2_training.duckdb"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()
    report = run_search(args.dataset_db, args.output_dir)
    print(
        json.dumps(
            {
                "champion": report["locked_champion"]["candidate"],
                "development": report["locked_champion"]["development_summary"],
                "final_holdout": report["final_holdout"],
                "artifacts": report["artifacts"],
            },
            indent=2,
            default=_jsonable,
        )
    )


if __name__ == "__main__":
    main()
