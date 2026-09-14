"""Walk-forward AI challenger for execution-policy selection.

The challenger is research-only. It learns on earlier folds, evaluates once
on the latest fold, and includes an explicit skip class. It never changes the
runtime router or writes a deployable model artifact.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

CHALLENGER_VERSION = "execution_policy_rf_challenger_v1"
POLICIES = (
    "scale_in_compact",
    "scale_in_balanced",
    "scale_in_deep_squeeze",
)
NUMERIC_FEATURES = (
    "model_probability",
    "heuristic_score",
    "quality_score",
    "volume_24h_usd",
    "volatility_score",
    "squeeze_score",
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
CATEGORICAL_FEATURES = ("liquidity_tier", "volatility_tier")


@dataclass(frozen=True, slots=True)
class ChallengerConfig:
    input_csv: Path
    output_json: Path
    min_test_events: int = 200
    min_folds: int = 3
    min_return_gain: float = 0.0005
    random_seed: int = 42


def _max_drawdown(returns: list[float]) -> float:
    equity = 1.0
    peak = 1.0
    worst = 0.0
    for value in returns:
        equity *= max(0.0, 1.0 + value)
        peak = max(peak, equity)
        worst = max(worst, (peak - equity) / peak)
    return worst


def _metrics(returns: list[float]) -> dict[str, float | int]:
    if not returns:
        return {"events": 0}
    return {
        "events": len(returns),
        "mean_return": round(mean(returns), 8),
        "median_return": round(median(returns), 8),
        "positive_rate": round(
            sum(value > 0.0 for value in returns) / len(returns),
            4,
        ),
        "skip_rate": round(
            sum(value == 0.0 for value in returns) / len(returns),
            4,
        ),
        "sequential_max_drawdown": round(_max_drawdown(returns), 6),
        "additive_return": round(sum(returns), 6),
    }


def _target_for_event(row: pd.Series) -> str:
    best_policy = str(row.idxmax())
    return best_policy if float(row[best_policy]) > 0.0 else "skip"


def _prepare(
    input_csv: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    frame = pd.read_csv(input_csv)
    required = {
        "prediction_id",
        "fold",
        "evaluated_policy_id",
        "net_return_planned",
        "router_policy_id",
        *POLICIES,
    }
    missing_base = {
        name
        for name in required
        if name not in frame.columns and name not in POLICIES
    }
    if missing_base:
        raise ValueError(
            f"challenger dataset missing columns: {sorted(missing_base)}"
        )
    for name in (*NUMERIC_FEATURES, "net_return_planned", "fold"):
        frame[name] = pd.to_numeric(frame[name], errors="coerce")
    outcomes = frame.pivot(
        index="prediction_id",
        columns="evaluated_policy_id",
        values="net_return_planned",
    )
    missing_policies = set(POLICIES) - set(outcomes.columns)
    if missing_policies:
        raise ValueError(
            f"challenger dataset missing policies: {sorted(missing_policies)}"
        )
    outcomes = outcomes.loc[:, list(POLICIES)].dropna()
    features = (
        frame.drop_duplicates("prediction_id")
        .set_index("prediction_id")
        .loc[outcomes.index]
    )
    targets = outcomes.apply(_target_for_event, axis=1)
    return features, outcomes, targets


def evaluate_challenger(config: ChallengerConfig) -> dict[str, Any]:
    features, outcomes, targets = _prepare(config.input_csv)
    folds = features["fold"].astype(int)
    unique_folds = sorted(int(value) for value in folds.unique())
    if len(unique_folds) < 2:
        raise ValueError("at least two chronological folds are required")
    holdout_fold = unique_folds[-1]
    train_mask = folds < holdout_fold
    test_mask = folds == holdout_fold
    feature_names = [*NUMERIC_FEATURES, *CATEGORICAL_FEATURES]

    numeric_pipeline = Pipeline(
        [("imputer", SimpleImputer(strategy="median"))]
    )
    categorical_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            (
                "one_hot",
                OneHotEncoder(handle_unknown="ignore"),
            ),
        ]
    )
    preprocessor = ColumnTransformer(
        [
            ("numeric", numeric_pipeline, list(NUMERIC_FEATURES)),
            (
                "categorical",
                categorical_pipeline,
                list(CATEGORICAL_FEATURES),
            ),
        ]
    )
    model = Pipeline(
        [
            ("preprocessor", preprocessor),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=300,
                    max_depth=4,
                    min_samples_leaf=15,
                    class_weight="balanced",
                    random_state=config.random_seed,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    model.fit(features.loc[train_mask, feature_names], targets[train_mask])
    predictions = model.predict(features.loc[test_mask, feature_names])
    test_ids = outcomes.index[test_mask]

    challenger_returns = [
        0.0 if choice == "skip" else float(outcomes.loc[event_id, choice])
        for event_id, choice in zip(test_ids, predictions, strict=True)
    ]
    router_choices = features.loc[test_ids, "router_policy_id"]
    router_returns = [
        float(outcomes.loc[event_id, policy_id])
        for event_id, policy_id in zip(
            test_ids,
            router_choices,
            strict=True,
        )
    ]
    training_means = {
        policy_id: float(outcomes.loc[train_mask, policy_id].mean())
        for policy_id in POLICIES
    }
    best_static_policy = max(training_means, key=training_means.get)
    best_static_returns = [
        float(value)
        for value in outcomes.loc[test_mask, best_static_policy].tolist()
    ]
    oracle_returns = [
        max(0.0, *(float(value) for value in row))
        for row in outcomes.loc[test_mask].itertuples(index=False, name=None)
    ]

    challenger_metrics = _metrics(challenger_returns)
    router_metrics = _metrics(router_returns)
    static_metrics = _metrics(best_static_returns)
    promotion_reasons: list[str] = []
    if len(unique_folds) < config.min_folds:
        promotion_reasons.append("insufficient_walk_forward_folds")
    if len(test_ids) < config.min_test_events:
        promotion_reasons.append("insufficient_holdout_events")
    if float(challenger_metrics["mean_return"]) <= 0.0:
        promotion_reasons.append("challenger_expected_return_not_positive")
    if (
        float(challenger_metrics["mean_return"])
        < float(static_metrics["mean_return"]) + config.min_return_gain
    ):
        promotion_reasons.append("challenger_does_not_beat_best_static_policy")
    if float(challenger_metrics["sequential_max_drawdown"]) > float(
        static_metrics["sequential_max_drawdown"]
    ):
        promotion_reasons.append("challenger_drawdown_worse_than_static")

    report = {
        "challenger_version": CHALLENGER_VERSION,
        "generated_at": datetime.now().astimezone().isoformat(),
        "input_csv": str(config.input_csv),
        "research_only": True,
        "runtime_model_written": False,
        "train_folds": [value for value in unique_folds if value < holdout_fold],
        "holdout_fold": holdout_fold,
        "train_events": int(train_mask.sum()),
        "holdout_events": int(test_mask.sum()),
        "training_target_counts": dict(Counter(targets[train_mask])),
        "holdout_prediction_counts": dict(Counter(predictions)),
        "best_static_policy_from_training": best_static_policy,
        "training_policy_mean_returns": training_means,
        "holdout": {
            "challenger": challenger_metrics,
            "rule_router": router_metrics,
            "best_static": static_metrics,
            "oracle_upper_bound": _metrics(oracle_returns),
        },
        "promotion": {
            "approved": not promotion_reasons,
            "reason_codes": promotion_reasons,
        },
    }
    config.output_json.parent.mkdir(parents=True, exist_ok=True)
    config.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("artifacts/execution_policy_backtest_events_latest.csv"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/execution_policy_ai_challenger_latest.json"),
    )
    args = parser.parse_args()
    report = evaluate_challenger(
        ChallengerConfig(input_csv=args.input, output_json=args.output)
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
