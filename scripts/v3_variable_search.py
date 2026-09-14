"""Multi-variable walk-forward grid search for V3 (48h / 20% target).

Explores candidate filtering, feature subsets, model architectures,
regularization, and calibration under strict zero-lookahead walk-forward CV
with 48h temporal embargoes. Never alters production configurations.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import Pipeline

from dao_vang.experiments.calibration import (
    fit_probability_calibrator,
)
from dao_vang.experiments.train_distribution_v2 import SERVING_FEATURE_COLS
from dao_vang.labels.specs.distribution_short_v3 import SPEC

LOGGER = logging.getLogger(__name__)

DATASET_PATH = Path("artifacts/universe_policy_v2_48h.duckdb")
OUTPUT_JSON = Path("artifacts/v3_variable_search_report.json")
OUTPUT_MD = Path("docs/V3_VARIABLE_SEARCH_REPORT.md")


@dataclass(frozen=True)
class VariantSpec:
    name: str
    axis: str
    description: str
    pump_threshold: float = 0.15
    min_volume_24h: float = 0.0
    filter_expr: str | None = None
    feature_cols: tuple[str, ...] = SERVING_FEATURE_COLS
    model_type: str = "lightgbm"
    model_params: dict[str, Any] = field(default_factory=dict)
    calibration_method: str = "isotonic"
    min_recall: float = 0.05
    cooldown_hours: int = 24


def load_dataset() -> pd.DataFrame:
    conn = duckdb.connect(str(DATASET_PATH), read_only=True)
    try:
        frame = conn.execute("""
            SELECT
                symbol,
                feature_time,
                entry_price,
                quote_volume_24h,
                label_value,
                """ + ", ".join(SERVING_FEATURE_COLS) + """
            FROM universe_policy_candidates_v2
            WHERE label_value IS NOT NULL
              AND symbol NOT IN ('USDCUSDT', 'FDUSDUSDT', 'TUSDUSDT', 'BUSDUSDT', 'USDPUSDT', 'EURUSDT')
            ORDER BY feature_time, symbol
        """).fetchdf()
    finally:
        conn.close()
    frame["feature_time"] = pd.to_datetime(frame["feature_time"], utc=True)
    frame["label_value"] = frame["label_value"].astype("int8")
    return frame


def _build_estimator(model_type: str, params: dict[str, Any], seed: int) -> Pipeline:
    if model_type == "lightgbm":
        default_lgb: dict[str, Any] = {
            "random_state": seed,
            "n_estimators": 300,
            "learning_rate": 0.03,
            "max_depth": 4,
            "num_leaves": 15,
            "min_child_samples": 80,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
            "reg_lambda": 1.0,
            "deterministic": True,
            "force_col_wise": True,
            "verbosity": -1,
            "n_jobs": 4,
        }
        default_lgb.update(params)
        estimator: Any = lgb.LGBMClassifier(**default_lgb)
    elif model_type == "random_forest":
        default_rf: dict[str, Any] = {
            "random_state": seed,
            "n_estimators": 300,
            "max_depth": 6,
            "min_samples_leaf": 50,
            "n_jobs": 4,
        }
        default_rf.update(params)
        estimator = RandomForestClassifier(**default_rf)
    elif model_type == "logistic_regression":
        default_lr: dict[str, Any] = {
            "random_state": seed,
            "max_iter": 1500,
            "C": 0.1,
        }
        default_lr.update(params)
        estimator = LogisticRegression(**default_lr)
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    return Pipeline([
        ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
        ("estimator", estimator),
    ])


def _partition_history(
    history: pd.DataFrame, embargo: pd.Timedelta
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    unique_times = pd.Series(history["feature_time"].drop_duplicates()).sort_values()
    if len(unique_times) < 30:
        empty = history.iloc[:0]
        return empty, empty, empty
    fit_boundary = unique_times.iloc[int((len(unique_times) - 1) * 0.70)]
    calibration_boundary = unique_times.iloc[int((len(unique_times) - 1) * 0.85)]
    fit = history[history["feature_time"] < fit_boundary]
    calibration = history[
        (history["feature_time"] >= fit_boundary + embargo)
        & (history["feature_time"] < calibration_boundary)
    ]
    policy = history[history["feature_time"] >= calibration_boundary + embargo]
    return pd.DataFrame(fit), pd.DataFrame(calibration), pd.DataFrame(policy)


def _threshold_metrics(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
    target: float,
    stop: float,
    cost: float,
    identities: pd.DataFrame | None = None,
    cooldown_hours: int = 24,
) -> dict[str, Any]:
    signal = probabilities >= threshold
    if identities is not None:
        episode_signal = np.zeros(len(signal), dtype=bool)
        last_signal: dict[str, pd.Timestamp] = {}
        for index, (symbol, feature_time) in enumerate(
            identities[["symbol", "feature_time"]].itertuples(index=False)
        ):
            if not signal[index]:
                continue
            ts = pd.Timestamp(feature_time)
            previous = last_signal.get(str(symbol))
            if previous is None or ts >= previous + pd.Timedelta(hours=cooldown_hours):
                episode_signal[index] = True
                last_signal[str(symbol)] = ts
        signal = episode_signal
    positives = int((y_true == 1).sum())
    true_positives = int((signal & (y_true == 1)).sum())
    false_positives = int((signal & (y_true == 0)).sum())
    signals = int(signal.sum())
    precision = true_positives / signals if signals else 0.0
    recall = true_positives / positives if positives else 0.0
    conservative_ev = precision * target - (1.0 - precision) * stop - cost
    return {
        "threshold": float(threshold),
        "signals": signals,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "precision": float(precision),
        "recall": float(recall),
        "conservative_ev": float(conservative_ev),
    }


def _select_threshold(
    y_true: np.ndarray,
    probabilities: np.ndarray,
    min_recall: float,
    target: float,
    stop: float,
    cost: float,
    identities: pd.DataFrame | None = None,
    cooldown_hours: int = 24,
) -> tuple[float, dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for threshold in np.arange(0.05, 0.951, 0.01):
        row = _threshold_metrics(
            y_true, probabilities, float(threshold), target, stop, cost, identities, cooldown_hours
        )
        if row["signals"] >= 5:
            candidates.append(row)
    eligible = [r for r in candidates if r["recall"] >= min_recall]
    pool = eligible or candidates
    if not pool:
        fallback = _threshold_metrics(y_true, probabilities, 0.95, target, stop, cost, identities, cooldown_hours)
        return 0.95, fallback
    best = max(pool, key=lambda r: (r["conservative_ev"], r["precision"], r["recall"], r["threshold"]))
    return float(best["threshold"]), best


def evaluate_variant(frame: pd.DataFrame, spec: VariantSpec) -> dict[str, Any]:
    # Apply filters
    filtered = pd.DataFrame(frame[frame["price_ret_24h"] >= spec.pump_threshold])
    if spec.min_volume_24h > 0:
        filtered = pd.DataFrame(filtered[filtered["quote_volume_24h"] >= spec.min_volume_24h])
    if spec.filter_expr:
        filtered = pd.DataFrame(filtered.query(spec.filter_expr))

    if len(filtered) < 200:
        return {"name": spec.name, "axis": spec.axis, "description": spec.description, "error": f"Insufficient data after filter: {len(filtered)} rows"}
    embargo = pd.Timedelta(hours=48)
    start = filtered["feature_time"].min()
    end = filtered["feature_time"].max() + pd.Timedelta(microseconds=1)
    warmup = start + pd.Timedelta(days=90)
    if warmup >= end:
        return {"name": spec.name, "axis": spec.axis, "description": spec.description, "error": "Dataset shorter than warmup"}

    n_folds = 4
    step = (end - warmup) / n_folds
    boundaries = [(warmup + i * step, warmup + (i + 1) * step) for i in range(n_folds)]
    feature_cols = list(spec.feature_cols)

    folds_data: list[dict[str, Any]] = []
    for fold_idx, (test_start, test_end) in enumerate(boundaries, 1):
        history = pd.DataFrame(filtered[filtered["feature_time"] < test_start - embargo])
        test = pd.DataFrame(filtered[(filtered["feature_time"] >= test_start) & (filtered["feature_time"] < test_end)])
        if test.empty:
            continue
        fit, calibration, policy = _partition_history(history, embargo)
        if any(len(part) < 30 or part["label_value"].nunique() < 2 for part in (fit, calibration, policy)):
            continue

        model = _build_estimator(spec.model_type, spec.model_params, 42 + fold_idx)
        model.fit(fit[feature_cols], fit["label_value"])

        # Calibrate
        raw_calib = model.predict_proba(calibration[feature_cols])[:, 1]
        calibrator = fit_probability_calibrator(
            raw_calib,
            calibration["label_value"].to_numpy(),
            method=spec.calibration_method,
            calibrator_id=f"{spec.calibration_method}_{spec.name}",
        )

        # Policy threshold
        raw_pol = model.predict_proba(policy[feature_cols])[:, 1]
        pol_probs = calibrator.transform(raw_pol)
        threshold, _ = _select_threshold(
            np.asarray(policy["label_value"], dtype=np.int8),
            pol_probs,
            spec.min_recall,
            SPEC.target,
            SPEC.stop,
            0.002,
            pd.DataFrame(policy[["symbol", "feature_time"]]),
            spec.cooldown_hours,
        )

        # Test evaluation
        raw_test = model.predict_proba(test[feature_cols])[:, 1]
        test_probs = calibrator.transform(raw_test)
        test_y = np.asarray(test["label_value"], dtype=np.int8)

        # Metrics
        ap = float(average_precision_score(test_y, test_probs))
        auc = float(roc_auc_score(test_y, test_probs)) if len(np.unique(test_y)) == 2 else 0.5
        brier = float(brier_score_loss(test_y, test_probs))
        prevalence = float(np.mean(test_y))
        null_brier = float(brier_score_loss(test_y, np.full(len(test_y), prevalence)))

        # ECE
        bins = np.linspace(0.0, 1.0, 11)
        ece = 0.0
        for b_idx in range(10):
            mask = (test_probs >= bins[b_idx]) & (test_probs <= bins[b_idx + 1] if b_idx == 9 else test_probs < bins[b_idx + 1])
            if mask.any():
                ece += float(mask.mean()) * abs(float(test_probs[mask].mean()) - float(test_y[mask].mean()))

        t_met = _threshold_metrics(
            test_y,
            test_probs,
            threshold,
            SPEC.target,
            SPEC.stop,
            0.002,
            pd.DataFrame(test[["symbol", "feature_time"]]),
            spec.cooldown_hours,
        )
        folds_data.append({
            "fold": fold_idx,
            "test_rows": len(test),
            "prevalence": prevalence,
            "threshold": threshold,
            "ap": ap,
            "auc": auc,
            "brier": brier,
            "null_brier": null_brier,
            "ece": ece,
            **t_met,
        })

    if not folds_data:
        return {"error": "No evaluable folds"}

    total_signals = sum(f["signals"] for f in folds_data)
    total_tp = sum(f["true_positives"] for f in folds_data)
    mean_precision = float(np.mean([f["precision"] for f in folds_data if f["signals"] > 0])) if any(f["signals"] > 0 for f in folds_data) else 0.0
    mean_ev = float(np.mean([f["conservative_ev"] for f in folds_data]))
    mean_ap = float(np.mean([f["ap"] for f in folds_data]))
    mean_auc = float(np.mean([f["auc"] for f in folds_data]))
    mean_ece = float(np.mean([f["ece"] for f in folds_data]))
    mean_brier = float(np.mean([f["brier"] for f in folds_data]))
    pos_folds = sum(f["conservative_ev"] > 0 for f in folds_data)

    return {
        "name": spec.name,
        "axis": spec.axis,
        "description": spec.description,
        "total_rows": len(filtered),
        "folds": len(folds_data),
        "signals": total_signals,
        "true_positives": total_tp,
        "precision": mean_precision,
        "conservative_ev": mean_ev,
        "positive_ev_folds": pos_folds,
        "ap": mean_ap,
        "auc": mean_auc,
        "ece": mean_ece,
        "brier": mean_brier,
        "fold_details": folds_data,
    }


def define_search_grid() -> list[VariantSpec]:
    clean_features = (
        "price_ret_1h", "price_ret_4h", "price_ret_24h", "price_volatility_24h",
        "distance_from_high_24h", "funding_rate_raw", "funding_percentile_30d",
        "funding_change_8h", "oi_change_4h", "volume_percentile_24h",
    )
    core_no_ls = tuple(
        c for c in SERVING_FEATURE_COLS
        if c not in ("global_ls_ratio", "top_ls_ratio", "retail_top_spread", "spread_trend_1h", "spread_trend_4h")
    )
    funding_momentum = (
        "price_ret_1h", "price_ret_4h", "price_ret_24h", "price_volatility_24h",
        "distance_from_high_24h", "momentum_deceleration_4h", "funding_rate_raw",
        "funding_percentile_7d", "funding_percentile_30d", "funding_change_8h",
        "funding_persistence_7d", "oi_change_1h", "oi_change_4h", "taker_buy_ratio",
    )

    variants: list[VariantSpec] = [
        # Baseline
        VariantSpec(
            name="baseline_default",
            axis="Baseline",
            description="Default LightGBM (depth=4, leaves=15), 25 features, pump>=15%, isotonic",
        ),
        # Axis 1: Universe & Filtering
        VariantSpec(
            name="universe_pump_ge_20",
            axis="Universe & Filtering",
            description="Higher pre-pump filter: price_ret_24h >= 20%",
            pump_threshold=0.20,
        ),
        VariantSpec(
            name="universe_pump_ge_25",
            axis="Universe & Filtering",
            description="Large pump filter: price_ret_24h >= 25%",
            pump_threshold=0.25,
        ),
        VariantSpec(
            name="universe_pump_ge_30",
            axis="Universe & Filtering",
            description="Extreme pump filter: price_ret_24h >= 30%",
            pump_threshold=0.30,
        ),
        VariantSpec(
            name="universe_min_volume_5m",
            axis="Universe & Filtering",
            description="Strict liquidity rule: quote_volume_24h >= $5M (Rule 7)",
            min_volume_24h=5_000_000,
        ),
        VariantSpec(
            name="universe_min_volume_10m",
            axis="Universe & Filtering",
            description="High liquidity rule: quote_volume_24h >= $10M",
            min_volume_24h=10_000_000,
        ),
        VariantSpec(
            name="universe_reversal_3pct",
            axis="Universe & Filtering",
            description="Distribution roll-over: distance_from_high_24h <= -3%",
            filter_expr="distance_from_high_24h <= -0.03",
        ),
        VariantSpec(
            name="universe_exhaustion_momentum",
            axis="Universe & Filtering",
            description="Momentum exhaustion: distance_from_high <= -2% and deceleration > 0",
            filter_expr="distance_from_high_24h <= -0.02 and momentum_deceleration_4h > 0",
        ),
        VariantSpec(
            name="universe_funding_scout",
            axis="Universe & Filtering",
            description="Funding exhaustion gate: percentile>=80%, persist>0, change_8h>0",
            filter_expr="funding_percentile_30d >= 0.80 and funding_persistence_7d > 0 and funding_change_8h > 0",
        ),
        # Axis 2: Feature Selection
        VariantSpec(
            name="features_clean_10",
            axis="Feature Selection",
            description="10 core features (price, funding, OI, vol; exclude noise)",
            feature_cols=clean_features,
        ),
        VariantSpec(
            name="features_no_ls_ratios",
            axis="Feature Selection",
            description="Drop noisy long/short positioning ratios (20 features)",
            feature_cols=core_no_ls,
        ),
        VariantSpec(
            name="features_funding_momentum",
            axis="Feature Selection",
            description="Focus on funding + OI + momentum (14 features)",
            feature_cols=funding_momentum,
        ),
        # Axis 3: Model Architecture & Regularization
        VariantSpec(
            name="model_lgb_shallow_reg",
            axis="Model Architecture",
            description="Shallow regularized LightGBM (depth=3, leaves=7, lambda=5)",
            model_params={"max_depth": 3, "num_leaves": 7, "min_child_samples": 100, "learning_rate": 0.02, "reg_lambda": 5.0},
        ),
        VariantSpec(
            name="model_lgb_heavy_reg",
            axis="Model Architecture",
            description="Heavy L1/L2 regularized LightGBM (depth=3, leaves=8, alpha=2, lambda=10)",
            model_params={"max_depth": 3, "num_leaves": 8, "min_child_samples": 120, "reg_alpha": 2.0, "reg_lambda": 10.0, "learning_rate": 0.02},
        ),
        VariantSpec(
            name="model_lgb_feature_subsample",
            axis="Model Architecture",
            description="Random feature subsampling (colsample=0.5, subsample=0.7)",
            model_params={"colsample_bytree": 0.5, "subsample": 0.7, "max_depth": 4, "num_leaves": 12},
        ),
        VariantSpec(
            name="model_random_forest",
            axis="Model Architecture",
            description="RandomForest (300 trees, depth=6, leaf=50)",
            model_type="random_forest",
        ),
        VariantSpec(
            name="model_logistic_l2_c01",
            axis="Model Architecture",
            description="Logistic Regression L2 (C=0.1)",
            model_type="logistic_regression",
            model_params={"C": 0.1},
        ),
        VariantSpec(
            name="model_logistic_l2_c001",
            axis="Model Architecture",
            description="Strong L2 Logistic Regression (C=0.01)",
            model_type="logistic_regression",
            model_params={"C": 0.01},
        ),
        # Axis 4: Calibration & Decision Strategy
        VariantSpec(
            name="calib_platt_sigmoid",
            axis="Calibration & Decision",
            description="Sigmoid/Platt calibration (avoids isotonic step overfitting)",
            calibration_method="sigmoid",
        ),
        VariantSpec(
            name="decision_strict_recall_10",
            axis="Calibration & Decision",
            description="Strict recall constraint (min_recall=0.10)",
            min_recall=0.10,
        ),
        VariantSpec(
            name="decision_cooldown_48h",
            axis="Calibration & Decision",
            description="Longer episode cooldown: 48h per symbol",
            cooldown_hours=48,
        ),
        # Combinations
        VariantSpec(
            name="combo_pump20_liquidity5m",
            axis="Combinations",
            description="Pump >= 20% + Liquidity >= $5M",
            pump_threshold=0.20,
            min_volume_24h=5_000_000,
        ),
        VariantSpec(
            name="combo_pump20_shallow_lgb",
            axis="Combinations",
            description="Pump >= 20% + Shallow Regularized LightGBM",
            pump_threshold=0.20,
            model_params={"max_depth": 3, "num_leaves": 7, "min_child_samples": 80, "reg_lambda": 3.0},
        ),
        VariantSpec(
            name="combo_pump25_shallow_sigmoid",
            axis="Combinations",
            description="Pump >= 25% + Shallow LGBM + Sigmoid calibration",
            pump_threshold=0.25,
            model_params={"max_depth": 3, "num_leaves": 7, "min_child_samples": 60, "reg_lambda": 3.0},
            calibration_method="sigmoid",
        ),
        VariantSpec(
            name="combo_clean_features_shallow_sigmoid",
            axis="Combinations",
            description="10 Clean features + Shallow LGBM + Sigmoid calibration",
            feature_cols=clean_features,
            model_params={"max_depth": 3, "num_leaves": 7, "min_child_samples": 80, "reg_lambda": 3.0},
            calibration_method="sigmoid",
        ),
        VariantSpec(
            name="combo_pump20_funding_scout",
            axis="Combinations",
            description="Pump >= 20% + Funding Scout Gate (high funding exhaustion)",
            pump_threshold=0.20,
            filter_expr="funding_percentile_30d >= 0.80 and funding_persistence_7d > 0 and funding_change_8h > 0",
        ),
        VariantSpec(
            name="combo_pump25_reversal3pct",
            axis="Combinations",
            description="Pump >= 25% + Reversal >= 3% from high",
            pump_threshold=0.25,
            filter_expr="distance_from_high_24h <= -0.03",
        ),
        VariantSpec(
            name="combo_pump25_funding_scout",
            axis="Combinations",
            description="Pump >= 25% + Funding Scout Gate",
            pump_threshold=0.25,
            filter_expr="funding_percentile_30d >= 0.80 and funding_persistence_7d > 0 and funding_change_8h > 0",
        ),
        VariantSpec(
            name="combo_pump25_reversal_funding_scout",
            axis="Combinations",
            description="Pump >= 25% + Reversal >= 2% + Funding Scout Gate",
            pump_threshold=0.25,
            filter_expr="distance_from_high_24h <= -0.02 and funding_percentile_30d >= 0.80 and funding_persistence_7d > 0 and funding_change_8h > 0",
        ),
        VariantSpec(
            name="combo_pump20_reversal3pct",
            axis="Combinations",
            description="Pump >= 20% + Reversal >= 3% from high",
            pump_threshold=0.20,
            filter_expr="distance_from_high_24h <= -0.03",
        ),
        VariantSpec(
            name="combo_pump25_liquidity5m",
            axis="Combinations",
            description="Pump >= 25% + Liquidity >= $5M (Rule 7)",
            pump_threshold=0.25,
            min_volume_24h=5_000_000,
        ),
    ]
    return variants


def main() -> None:
    LOGGER.info("Loading dataset from %s", DATASET_PATH)
    frame = load_dataset()
    LOGGER.info("Loaded %d rows across %d symbols", len(frame), frame["symbol"].nunique())

    variants = define_search_grid()
    LOGGER.info("Starting evaluation of %d search variants...", len(variants))

    results: list[dict[str, Any]] = []
    start_time = time.time()

    for idx, spec in enumerate(variants, 1):
        v_start = time.time()
        LOGGER.info("[%d/%d] Evaluating: %s (%s)", idx, len(variants), spec.name, spec.axis)
        try:
            res = evaluate_variant(frame, spec)
            elapsed = time.time() - v_start
            res["elapsed_seconds"] = round(elapsed, 2)
            results.append(res)
            if "error" in res:
                LOGGER.warning("  -> Error: %s", res["error"])
            else:
                LOGGER.info(
                    "  -> Signals: %d | Precision: %.1f%% | EV: %.2f%% | AUC: %.3f | AP: %.3f | PosFolds: %d/4 (%.1fs)",
                    res["signals"], res["precision"] * 100, res["conservative_ev"] * 100,
                    res["auc"], res["ap"], res["positive_ev_folds"], elapsed
                )
        except Exception as exc:
            LOGGER.exception("Failed variant %s: %s", spec.name, exc)
            results.append({"name": spec.name, "axis": spec.axis, "error": str(exc)})

    total_time = time.time() - start_time
    LOGGER.info("Grid search completed in %.1f seconds.", total_time)

    # Sort valid results by Conservative EV descending, then precision
    valid = [r for r in results if "error" not in r]
    valid.sort(key=lambda r: (r["conservative_ev"], r["precision"], r["ap"]), reverse=True)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_variants": len(variants),
        "evaluated_variants": len(results),
        "total_time_seconds": round(total_time, 1),
        "rankings": valid,
        "all_results": results,
    }
    OUTPUT_JSON.write_text(json.dumps(report_data, indent=2, default=str), encoding="utf-8")
    LOGGER.info("Saved JSON report to %s", OUTPUT_JSON)

    # Write Markdown summary table
    md_lines = [
        "# Kết quả tìm kiếm đa biến số tối ưu hoá mô hình V3 (20% / 48h)",
        f"\n*Thời gian thực hiện: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}*",
        f"\nTổng số biến thể thử nghiệm: {len(variants)} | Thời gian chạy: {total_time:.1f}s\n",
        "| Hạng | Biến thể | Trục (Axis) | Signals | Precision | Conservative EV | Pos Folds | AP | ROC-AUC | ECE |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, r in enumerate(valid, 1):
        prec_str = f"{r['precision'] * 100:.1f}%"
        ev_str = f"**{r['conservative_ev'] * 100:+.2f}%**" if r['conservative_ev'] > 0 else f"{r['conservative_ev'] * 100:+.2f}%"
        md_lines.append(
            f"| {rank} | `{r['name']}` | {r['axis']} | {r['signals']} | {prec_str} | {ev_str} | {r['positive_ev_folds']}/4 | {r['ap']:.3f} | {r['auc']:.3f} | {r['ece']:.3f} |"
        )

    md_lines.append("\n## Chi tiết các biến thể hàng đầu và phát hiện chính\n")
    for rank, r in enumerate(valid[:5], 1):
        md_lines.append(f"### Top {rank}: `{r['name']}` ({r['axis']})")
        md_lines.append(f"- **Mô tả**: {r['description']}")
        md_lines.append(f"- **Hiệu năng**: Signals = {r['signals']}, Precision = {r['precision']*100:.1f}%, Conservative EV = {r['conservative_ev']*100:+.2f}%, Folds dương = {r['positive_ev_folds']}/4")
        md_lines.append(f"- **Đo lường xác suất**: ROC-AUC = {r['auc']:.3f}, Average Precision = {r['ap']:.3f}, ECE = {r['ece']:.3f}, Brier = {r['brier']:.4f}\n")

    OUTPUT_MD.write_text("\n".join(md_lines), encoding="utf-8")
    LOGGER.info("Saved Markdown report to %s", OUTPUT_MD)


if __name__ == "__main__":
    main()
