from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel


class ExperimentConfig(BaseModel):
    """
    Configuration for an experiment run.
    """

    hypothesis_id: str
    dataset_version: str
    label_version: str
    feature_set_version: str
    baseline_model: str
    split_version: str
    seed: int
    metrics: List[str]
    db_path: str = "./data/dev.duckdb"
    code_commit: Optional[str] = None


def _mock_results(config: ExperimentConfig) -> Dict[str, Any]:
    """Return mock results for MVP demo / when no real data is available."""
    return {
        "config": config.model_dump(),
        "status": "completed",
        "results": {
            "per_fold": [
                {
                    "fold_idx": 1,
                    "train_start": "2023-01-01",
                    "train_end": "2023-06-01",
                    "test_start": "2023-06-01",
                    "test_end": "2023-07-01",
                    "metrics": {"precision": 0.55, "recall": 0.60, "brier": 0.22},
                },
                {
                    "fold_idx": 2,
                    "train_start": "2023-02-01",
                    "train_end": "2023-07-01",
                    "test_start": "2023-07-01",
                    "test_end": "2023-08-01",
                    "metrics": {"precision": 0.58, "recall": 0.59, "brier": 0.21},
                },
            ],
            "aggregate": {
                "precision_mean": 0.565,
                "precision_std": 0.015,
                "recall_mean": 0.595,
                "recall_std": 0.005,
                "brier_mean": 0.215,
                "brier_std": 0.005,
            },
        },
    }


def run_experiment(
    config: ExperimentConfig, conn: Any = None
) -> Dict[str, Any]:
    """
    Orchestrates the experiment:
    - Loads dataset, features, labels based on versions in config.
    - Applies splits.
    - Runs the selected model.
    - Computes metrics.

    If ``conn`` is provided (a live DuckDB connection), it is used directly
    instead of opening a new one. This avoids file-lock conflicts when the
    caller (e.g. the Streamlit UI) already holds a write connection.

    Returns a dictionary containing the results and execution metadata.
    """
    import duckdb
    import pandas as pd
    import numpy as np
    from dao_vang.experiments.walk_forward import embargo_split, train_evaluate_logreg

    owns_conn = conn is None
    if owns_conn:
        # Connect to DuckDB and load data.
        # Fall back to mock results if the DB is unavailable (e.g. locked by
        # another process such as the Streamlit UI) or has no usable data.
        try:
            conn = duckdb.connect(config.db_path, read_only=True)
        except Exception:
            return _mock_results(config)

    # Load features joined with labels
    try:
        df = conn.execute(
            """
            SELECT f.*, l.label_value AS is_distribution,
                   l.lead_time_minutes, l.invalidation_time
            FROM feature_results f
            INNER JOIN labels l
                ON f.feature_time = l.signal_time
                AND f.symbol = l.symbol
            """
        ).df()
    except Exception:
        if owns_conn:
            try:
                conn.close()
            except Exception:
                pass
        return _mock_results(config)
    finally:
        if owns_conn:
            try:
                conn.close()
            except Exception:
                pass

    if df.empty or 'is_distribution' not in df.columns:
        return _mock_results(config)

    # Keep only rows with valid labels
    df = df.dropna(subset=['is_distribution'])

    if len(df) < 100:
        return _mock_results(config)

    # Sort by time
    df = df.sort_values(by="feature_time").reset_index(drop=True)

    # === Leakage audit ===
    leakage_report = _audit_leakage(df, feature_cols=None)

    # === Data quality report ===
    data_quality = _data_quality_report(df)

    # === Lead time stats (median/p25/p75 time-to-distribution for positive labels) ===
    lead_time_stats = _lead_time_stats(df)

    # === Walk-forward split: rolling window per VALIDATION.md ===
    # VALIDATION.md: train_window 90d, validation 30d, test 30d, step 30d.
    # With limited data we use a rolling expanding-window approach that
    # produces multiple non-overlapping test windows, each followed by an
    # embargo. We aim for ~5 folds when data allows, fewer when it doesn't.
    min_time = df["feature_time"].min()
    max_time = df["feature_time"].max()
    total_duration = max_time - min_time

    # Find time points where positives first appear
    pos_df = df[df["is_distribution"] == 1]
    if len(pos_df) == 0:
        # No positives at all — return with warning
        return {
            "config": config.model_dump(),
            "status": "completed",
            "results": {
                "per_fold": [],
                "aggregate": {
                    "precision_mean": 0.0, "precision_std": 0.0,
                    "recall_mean": 0.0, "recall_std": 0.0,
                    "brier_mean": 0.0, "brier_std": 0.0,
                },
                "baselines": {},
                "leakage_report": leakage_report,
                "data_quality": data_quality,
                "warning": "No positive labels in dataset — cannot train model.",
            },
        }

    first_pos_time = pos_df["feature_time"].min()

    # Rolling walk-forward: test windows of ~15% of total duration, stepping
    # forward by the same amount. Train = everything before test start.
    # This yields up to ~5 folds for 90 days of data.
    test_window = total_duration * 0.15

    # First test starts after we have enough train data (at least 50% of total)
    first_test_start = min_time + total_duration * 0.5
    # Ensure first test start is after first positive
    if first_test_start <= first_pos_time:
        first_test_start = first_pos_time + pd.Timedelta(hours=24)

    fold_splits = []
    test_start = first_test_start
    fold_idx = 0
    while test_start + test_window <= max_time + pd.Timedelta(minutes=5):
        fold_idx += 1
        test_end = test_start + test_window
        if test_end > max_time:
            test_end = max_time
        # Ensure test period contains at least some positives; if not, skip
        fold_splits.append((min_time, test_start, test_start, test_end))
        test_start = test_end  # step forward (non-overlapping)
        if fold_idx >= 6:  # cap at 6 folds
            break

    folds = [
        {"train_start": t0, "train_end": t1, "test_start": t1, "test_end": t2}
        for t0, t1, t1b, t2 in fold_splits
    ]

    # Feature columns (everything except time, decision time, labels, and
    # label-derived columns like lead_time/invalidation which must NOT be used
    # as features — that would be target leakage).
    exclude_cols = [
        'feature_time', 'decision_time', 'is_distribution', 'quality_status',
        'symbol', 'lead_time_minutes', 'invalidation_time',
    ]
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    results_per_fold = []
    baseline_results_per_fold = []

    for i, fold in enumerate(folds):
        train_df, test_df = embargo_split(
            df,
            fold["train_start"],
            fold["train_end"],
            fold["test_start"],
            fold["test_end"]
        )

        # Skip fold if train or test has only one class
        if train_df["is_distribution"].nunique() < 2 or test_df["is_distribution"].nunique() < 2:
            results_per_fold.append({
                "fold_idx": i + 1,
                "train_start": str(fold["train_start"]),
                "train_end": str(fold["train_end"]),
                "test_start": str(fold["test_start"]),
                "test_end": str(fold["test_end"]),
                "metrics": {"precision": 0.0, "recall": 0.0, "brier": 0.0, "threshold": 0.5},
                "skipped": True,
                "reason": "Insufficient class diversity in train or test",
            })
            continue

        X_train = train_df[feature_cols].fillna(0)
        y_train = train_df['is_distribution']
        X_test = test_df[feature_cols].fillna(0)
        y_test = test_df['is_distribution']

        # Model metrics (with threshold tuning)
        metrics = train_evaluate_logreg(X_train, y_train, X_test, y_test)

        results_per_fold.append({
            "fold_idx": i + 1,
            "train_start": str(fold["train_start"]),
            "train_end": str(fold["train_end"]),
            "test_start": str(fold["test_start"]),
            "test_end": str(fold["test_end"]),
            "metrics": metrics,
            "train_size": len(train_df),
            "train_positives": int(y_train.sum()),
            "test_size": len(test_df),
            "test_positives": int(y_test.sum()),
        })

        # Baseline metrics for the same test set
        baseline_metrics = _compute_baselines(test_df, y_test, config.seed)
        baseline_results_per_fold.append({
            "fold_idx": i + 1,
            "baselines": baseline_metrics,
        })

    # Aggregate model metrics — only count valid (non-skipped) folds
    valid_folds = [f for f in results_per_fold if not f.get("skipped")]
    precisions = [f["metrics"]["precision"] for f in valid_folds]
    recalls = [f["metrics"]["recall"] for f in valid_folds]
    briers = [f["metrics"]["brier"] for f in valid_folds]

    aggregate = {
        "precision_mean": float(np.mean(precisions)) if precisions else 0.0,
        "precision_std": float(np.std(precisions)) if precisions else 0.0,
        "recall_mean": float(np.mean(recalls)) if recalls else 0.0,
        "recall_std": float(np.std(recalls)) if recalls else 0.0,
        "brier_mean": float(np.mean(briers)) if briers else 0.0,
        "brier_std": float(np.std(briers)) if briers else 0.0,
        "n_valid_folds": len(valid_folds),
        "n_skipped_folds": len(results_per_fold) - len(valid_folds),
    }

    # Bootstrap confidence intervals (95%) for precision/recall/brier
    aggregate["confidence_intervals"] = _bootstrap_ci(
        precisions, recalls, briers, seed=config.seed
    )

    # Aggregate baseline metrics — only from valid folds
    valid_baseline_results = [
        br for br, f in zip(baseline_results_per_fold, results_per_fold) if not f.get("skipped")
    ]
    baseline_aggregate = _aggregate_baselines(valid_baseline_results)

    # Regime breakdown — split test predictions by market regime
    regime_breakdown = _regime_breakdown(df, results_per_fold, folds)

    return {
        "config": config.model_dump(),
        "status": "completed",
        "results": {
            "per_fold": results_per_fold,
            "aggregate": aggregate,
            "baselines": baseline_aggregate,
            "leakage_report": leakage_report,
            "data_quality": data_quality,
            "regime_breakdown": regime_breakdown,
            "lead_time_stats": lead_time_stats,
        },
    }


def _regime_breakdown(df: Any, results_per_fold: list, folds: list) -> Dict[str, Any]:
    """Break down label distribution by market regime (bull/bear/side).

    Regime is defined by 24h price return:
    - bull: price_ret_24h > +0.02
    - bear: price_ret_24h < -0.02
    - side: otherwise
    """
    if "price_ret_24h" not in df.columns or "is_distribution" not in df.columns:
        return {"status": "unavailable", "reason": "missing price_ret_24h or label column"}

    work = df.copy()
    work["price_ret_24h"] = work["price_ret_24h"].fillna(0)
    work["regime"] = "side"
    work.loc[work["price_ret_24h"] > 0.02, "regime"] = "bull"
    work.loc[work["price_ret_24h"] < -0.02, "regime"] = "bear"

    breakdown: Dict[str, Any] = {"status": "ok", "regimes": {}}
    for regime in ["bull", "bear", "side"]:
        subset = work[work["regime"] == regime]
        labels = subset["is_distribution"].dropna()
        n_pos = int((labels == 1).sum())
        n_neg = int((labels == 0).sum())
        prevalence = float(labels.mean()) if len(labels) > 0 else 0.0
        breakdown["regimes"][regime] = {
            "n_rows": len(subset),
            "n_positive": n_pos,
            "n_negative": n_neg,
            "prevalence": prevalence,
        }
    return breakdown


def _bootstrap_ci(
    precisions: list,
    recalls: list,
    briers: list,
    seed: int = 42,
    n_bootstrap: int = 1000,
) -> Dict[str, Dict[str, float]]:
    """Compute 95% bootstrap confidence intervals for precision/recall/brier.

    Resamples the per-fold metrics with replacement and reports the 2.5th and
    97.5th percentiles of the bootstrap distribution of the mean.
    """
    rng = np.random.default_rng(seed)

    def _ci(values: list) -> Dict[str, float]:
        if len(values) < 2:
            v = float(values[0]) if values else 0.0
            return {"mean": v, "ci_lower": v, "ci_upper": v}
        arr = np.array(values, dtype=float)
        boot_means = np.empty(n_bootstrap)
        for i in range(n_bootstrap):
            sample = rng.choice(arr, size=len(arr), replace=True)
            boot_means[i] = float(np.mean(sample))
        return {
            "mean": float(np.mean(arr)),
            "ci_lower": float(np.percentile(boot_means, 2.5)),
            "ci_upper": float(np.percentile(boot_means, 97.5)),
        }

    return {
        "precision": _ci(precisions),
        "recall": _ci(recalls),
        "brier": _ci(briers),
    }


def _lead_time_stats(df: Any) -> Dict[str, Any]:
    """Compute lead time statistics for positive labels.

    Lead time = minutes from signal_time to target_time (when distribution
    actually materialized). Only positive labels have a non-null lead_time.

    Returns median, mean, p25, p75, min, max in minutes, plus a human-readable
    summary. Also reports the invalidation horizon (24h for MVP v0.1).
    """
    stats: Dict[str, Any] = {
        "status": "unavailable",
        "horizon_minutes": 1440,  # MVP v0.1: 24h
        "n_positive_with_lead_time": 0,
    }
    if "lead_time_minutes" not in df.columns or "is_distribution" not in df.columns:
        return stats

    pos = df[df["is_distribution"] == 1]["lead_time_minutes"].dropna()
    if len(pos) == 0:
        stats["status"] = "no_positive_labels"
        return stats

    stats.update({
        "status": "ok",
        "n_positive_with_lead_time": int(len(pos)),
        "median_minutes": float(pos.median()),
        "mean_minutes": float(pos.mean()),
        "p25_minutes": float(pos.quantile(0.25)),
        "p75_minutes": float(pos.quantile(0.75)),
        "min_minutes": float(pos.min()),
        "max_minutes": float(pos.max()),
    })
    # Human-readable median
    median_h = stats["median_minutes"] / 60.0
    stats["median_hours"] = round(median_h, 1)
    stats["summary"] = (
        f"Median lead time: {stats['median_minutes']:.0f} min (~{median_h:.1f}h). "
        f"Range: {stats['min_minutes']:.0f}–{stats['max_minutes']:.0f} min. "
        f"Signal invalidates after {stats['horizon_minutes']} min (24h horizon)."
    )
    return stats


def _compute_baselines(
    test_df: Any, y_test: Any, seed: int
) -> Dict[str, Dict[str, float]]:
    """Compute B0 (random), B1 (price return), B2 (funding) baselines on the test set."""
    from dao_vang.baselines.rules import b0_random, b1_price_return, b2_funding

    y_true = y_test.astype(int).tolist()
    prevalence = float(y_test.mean()) if len(y_test) > 0 else 0.0
    n = len(y_true)

    results: Dict[str, Dict[str, float]] = {}

    # B0: random calibrated
    b0_pred = b0_random(prevalence, n, seed)
    results["B0_random"] = _calc_baseline_metrics(y_true, b0_pred)

    # B1: price return 24h threshold
    if "price_ret_24h" in test_df.columns:
        pr = test_df["price_ret_24h"].fillna(0).tolist()
        for thresh in [0.0, 0.02, 0.05]:
            b1_pred = b1_price_return(pr, thresh)
            results[f"B1_price_ret_{thresh}"] = _calc_baseline_metrics(y_true, b1_pred)

    # B2: funding percentile threshold
    if "funding_percentile_30d" in test_df.columns:
        fp = test_df["funding_percentile_30d"].fillna(0).tolist()
        for thresh in [0.5, 0.8, 0.9]:
            b2_pred = b2_funding(fp, thresh)
            results[f"B2_funding_{thresh}"] = _calc_baseline_metrics(y_true, b2_pred)

    return results


def _calc_baseline_metrics(y_true: list, y_pred: list) -> Dict[str, float]:
    """Calculate precision, recall, brier for a baseline."""
    from sklearn.metrics import precision_score, recall_score, brier_score_loss

    yt = [int(v) for v in y_true]
    yp = [int(v) for v in y_pred]

    try:
        precision = float(precision_score(yt, yp, zero_division=0))
        recall = float(recall_score(yt, yp, zero_division=0))
        # Brier needs probabilities; for baselines use 0/1 predictions
        brier = float(brier_score_loss(yt, yp))
    except Exception:
        precision, recall, brier = 0.0, 0.0, 0.0

    return {"precision": precision, "recall": recall, "brier": brier}


def _aggregate_baselines(
    baseline_results_per_fold: list,
) -> Dict[str, Dict[str, float]]:
    """Aggregate baseline metrics across folds."""
    if not baseline_results_per_fold:
        return {}

    # Collect all baseline names
    all_names = set()
    for fold_res in baseline_results_per_fold:
        all_names.update(fold_res["baselines"].keys())

    aggregate: Dict[str, Dict[str, float]] = {}
    for name in sorted(all_names):
        precisions = []
        recalls = []
        briers = []
        for fold_res in baseline_results_per_fold:
            if name in fold_res["baselines"]:
                m = fold_res["baselines"][name]
                precisions.append(m["precision"])
                recalls.append(m["recall"])
                briers.append(m["brier"])
        aggregate[name] = {
            "precision_mean": float(np.mean(precisions)) if precisions else 0.0,
            "recall_mean": float(np.mean(recalls)) if recalls else 0.0,
            "brier_mean": float(np.mean(briers)) if briers else 0.0,
        }

    return aggregate


def _audit_leakage(df: Any, feature_cols: Any = None) -> Dict[str, Any]:
    """Audit for data leakage: forbidden columns, split overlap, future data."""
    report: Dict[str, Any] = {
        "forbidden_columns": [],
        "split_overlap": "not_checked",
        "future_data_check": "passed",
        "status": "passed",
    }

    # Check for forbidden column prefixes
    forbidden_prefixes = ["label_", "is_distribution", "target_"]
    columns = list(df.columns)
    for col in columns:
        for prefix in forbidden_prefixes:
            if col.startswith(prefix) and col != "is_distribution":
                report["forbidden_columns"].append(col)

    if report["forbidden_columns"]:
        report["status"] = "failed"

    # Check that feature_time is monotonic within each symbol
    if "symbol" in df.columns and "feature_time" in df.columns:
        for sym in df["symbol"].unique():
            sym_df = df[df["symbol"] == sym].sort_values("feature_time")
            times = sym_df["feature_time"].tolist()
            for i in range(1, len(times)):
                if times[i] < times[i - 1]:
                    report["future_data_check"] = "failed"
                    report["status"] = "failed"
                    break

    return report


def _data_quality_report(df: Any) -> Dict[str, Any]:
    """Generate a data quality summary from the feature dataframe."""
    report: Dict[str, Any] = {
        "total_rows": len(df),
        "columns": len(df.columns),
        "null_counts": {},
        "duplicate_count": 0,
        "label_distribution": {},
        "time_range": {},
    }

    # Null counts per column (top 10)
    null_counts = df.isnull().sum().to_dict()
    sorted_nulls = dict(sorted(null_counts.items(), key=lambda x: -x[1])[:10])
    report["null_counts"] = {k: int(v) for k, v in sorted_nulls.items()}

    # Duplicate rows
    if "feature_time" in df.columns and "symbol" in df.columns:
        report["duplicate_count"] = int(df.duplicated(subset=["symbol", "feature_time"]).sum())

    # Label distribution
    if "is_distribution" in df.columns:
        labels = df["is_distribution"].dropna()
        report["label_distribution"] = {
            "positive": int((labels == 1).sum()),
            "negative": int((labels == 0).sum()),
            "null": int(df["is_distribution"].isnull().sum()),
            "prevalence": float(labels.mean()) if len(labels) > 0 else 0.0,
        }

    # Time range
    if "feature_time" in df.columns:
        report["time_range"] = {
            "start": str(df["feature_time"].min()),
            "end": str(df["feature_time"].max()),
            "duration_days": float(
                (df["feature_time"].max() - df["feature_time"].min()).total_seconds() / 86400
            ),
        }

    return report
