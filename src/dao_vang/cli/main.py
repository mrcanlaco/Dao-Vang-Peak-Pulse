from datetime import datetime, timezone
from pathlib import Path

import duckdb
import typer

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.experiments.artifacts import ArtifactRegistry
from dao_vang.experiments.forward_test import (
    evaluate_frozen,
    freeze_model,
    list_frozen_models,
)
from dao_vang.experiments.runner import ExperimentConfig, run_experiment
from dao_vang.features.builder import build_features
from dao_vang.labels.engine import DistributionLabelEngine
from dao_vang.reports.generator import generate_markdown_report

app = typer.Typer(help="Đảo Vàng CLI")

data_app = typer.Typer(help="Data collection and normalization commands")
labels_app = typer.Typer(help="Labeling commands")
features_app = typer.Typer(help="Feature generation commands")
experiment_app = typer.Typer(help="Experiment and training commands")
report_app = typer.Typer(help="Reporting commands")

app.add_typer(data_app, name="data")
app.add_typer(labels_app, name="labels")
app.add_typer(features_app, name="features")
app.add_typer(experiment_app, name="experiment")
app.add_typer(report_app, name="report")


@data_app.command("collect")
def data_collect(
    start_timestamp: float,
    end_timestamp: float,
    run_id: str = "manual_run",
) -> None:
    """Collect klines data from Binance."""
    settings = AppSettings()
    client = BinanceClient()
    collector = KlinesCollector(client, settings)

    start_dt = datetime.fromtimestamp(start_timestamp, tz=timezone.utc)
    end_dt = datetime.fromtimestamp(end_timestamp, tz=timezone.utc)

    manifest = collector.collect(start_dt, end_dt, run_id)
    typer.echo(f"Collected data with manifest status: {manifest.status}")


@data_app.command("normalize")
def data_normalize() -> None:
    """Normalize raw data (placeholder)."""
    typer.echo("Normalization not fully exposed via CLI yet.")


@labels_app.command("generate")
def label_generate(
    db_path: str,
    source_table: str,
) -> None:
    """Generate labels from normalized data."""
    conn = duckdb.connect(db_path)
    engine = DistributionLabelEngine()
    results = engine.compute_all(conn, source_table)
    typer.echo(f"Generated {len(results)} labels.")


@features_app.command("generate")
def feature_generate(
    db_path: str,
    source_table: str,
    target_table: str,
) -> None:
    """Generate features from normalized data."""
    db = DuckDBQueryLayer(db_path)
    build_features(db, source_table, target_table)
    typer.echo(f"Generated features into {target_table}")


@experiment_app.command("run")
def experiment_run(
    hypothesis_id: str,
    baseline_model: str,
    dataset_version: str,
    label_version: str,
    feature_set_version: str,
    split_version: str,
    seed: int,
    metrics: str = "precision,recall",
    artifact_dir: str = "./artifacts",
) -> None:
    """Run an experiment and save to artifact registry."""
    config = ExperimentConfig(
        hypothesis_id=hypothesis_id,
        baseline_model=baseline_model,
        dataset_version=dataset_version,
        label_version=label_version,
        feature_set_version=feature_set_version,
        split_version=split_version,
        seed=seed,
        metrics=metrics.split(","),
    )
    result = run_experiment(config)

    registry = ArtifactRegistry(Path(artifact_dir))
    artifact_id = registry.save_experiment(result)

    typer.echo(f"Experiment completed. Artifact ID: {artifact_id}")


@experiment_app.command("freeze")
def experiment_freeze(
    db_path: str,
    artifact_dir: str = "./artifacts",
    hypothesis_id: str = "forward_test",
    dataset_version: str = "v1",
    label_version: str = "v1",
    feature_set_version: str = "v1",
    seed: int = 42,
) -> None:
    """Freeze a trained model for forward testing.

    Trains a LogisticRegression on ALL labeled data in the DB, tunes threshold
    on the last 20% validation window, and saves the frozen model + metadata.
    The train_cutoff is the latest feature_time in the training data — data
    after this point is forward-test data.
    """
    from sklearn.linear_model import LogisticRegression

    conn = duckdb.connect(db_path, read_only=True)
    try:
        df = conn.execute(
            """
            SELECT f.*, l.label_value AS is_distribution
            FROM feature_results f
            INNER JOIN labels l
                ON f.feature_time = l.signal_time AND f.symbol = l.symbol
            """
        ).df()
    finally:
        conn.close()

    if df.empty or "is_distribution" not in df.columns:
        typer.echo("No labeled data found in DB.", err=True)
        raise typer.Exit(code=1)

    df = df.dropna(subset=["is_distribution"])
    if len(df) < 200 or df["is_distribution"].nunique() < 2:
        typer.echo(f"Insufficient data: {len(df)} rows, need ≥200 with both classes.", err=True)
        raise typer.Exit(code=1)

    df = df.sort_values("feature_time").reset_index(drop=True)
    exclude_cols = [
        "feature_time", "decision_time", "is_distribution", "quality_status",
        "symbol", "lead_time_minutes", "invalidation_time",
    ]
    feature_cols = [c for c in df.columns if c not in exclude_cols]

    # Tune threshold on last 20% validation
    val_cutoff = df["feature_time"].quantile(0.8)
    train_df = df[df["feature_time"] < val_cutoff]
    val_df = df[df["feature_time"] >= val_cutoff]

    model = LogisticRegression(max_iter=1000, random_state=seed, class_weight="balanced")
    model.fit(train_df[feature_cols].fillna(0), train_df["is_distribution"])

    # Threshold tuning on validation
    best_threshold, best_f1 = 0.5, 0.0
    if len(val_df) > 0 and val_df["is_distribution"].nunique() >= 2:
        y_val_prob = model.predict_proba(val_df[feature_cols].fillna(0))[:, 1]
        y_val = val_df["is_distribution"].values
        import numpy as np
        for thresh in np.arange(0.05, 0.95, 0.05):
            y_pred_t = (y_val_prob >= thresh).astype(int)
            tp = int(((y_pred_t == 1) & (y_val == 1)).sum())
            fp = int(((y_pred_t == 1) & (y_val == 0)).sum())
            fn = int(((y_pred_t == 0) & (y_val == 1)).sum())
            if tp + fp == 0 or tp + fn == 0:
                continue
            p = tp / (tp + fp)
            r = tp / (tp + fn)
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            if f1 > best_f1:
                best_f1 = f1
                best_threshold = thresh

    # Retrain on ALL data with the tuned threshold
    final_model = LogisticRegression(max_iter=1000, random_state=seed, class_weight="balanced")
    final_model.fit(df[feature_cols].fillna(0), df["is_distribution"])

    train_cutoff = df["feature_time"].max()
    config = {
        "hypothesis_id": hypothesis_id,
        "dataset_version": dataset_version,
        "label_version": label_version,
        "feature_set_version": feature_set_version,
        "seed": seed,
    }
    training_stats = {
        "train_size": len(df),
        "train_positives": int(df["is_distribution"].sum()),
        "threshold": float(best_threshold),
        "n_features": len(feature_cols),
    }

    info = freeze_model(
        model=final_model,
        threshold=float(best_threshold),
        feature_cols=feature_cols,
        config=config,
        train_cutoff=train_cutoff,
        training_stats=training_stats,
        artifact_dir=Path(artifact_dir),
    )
    typer.echo(f"Frozen model saved: {info.model_id}")
    typer.echo(f"  Train cutoff: {info.train_cutoff}")
    typer.echo(f"  Threshold: {info.threshold:.4f}")
    typer.echo(f"  Features: {len(info.feature_cols)}")
    typer.echo(f"  Training rows: {training_stats['train_size']} ({training_stats['train_positives']}+)")


@experiment_app.command("forward-test")
def experiment_forward_test(
    db_path: str,
    model_id: str,
    artifact_dir: str = "./artifacts",
) -> None:
    """Evaluate a frozen model on forward-test data (data after train_cutoff).

    Scores all labeled data after the frozen model's train_cutoff and computes
    precision, recall, brier, and drift vs training metrics.
    """
    conn = duckdb.connect(db_path, read_only=True)
    try:
        df = conn.execute(
            """
            SELECT f.*, l.label_value AS is_distribution
            FROM feature_results f
            INNER JOIN labels l
                ON f.feature_time = l.signal_time AND f.symbol = l.symbol
            """
        ).df()
    finally:
        conn.close()

    if df.empty:
        typer.echo("No data found in DB.", err=True)
        raise typer.Exit(code=1)

    result = evaluate_frozen(model_id, df, artifact_dir=Path(artifact_dir))

    if result["status"] != "ok":
        typer.echo(f"Cannot evaluate: {result.get('message', result['status'])}", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Forward test: {model_id}")
    typer.echo(f"  Forward rows: {result['n_forward_rows']}")
    typer.echo(f"  Actual distributions: {result['n_positive_labels']}")
    typer.echo(f"  Predicted positive: {result['n_predicted_positive']}")
    m = result["metrics"]
    tm = result["training_metrics"]
    typer.echo(f"  Precision: {m['precision']:.4f} (train: {tm['precision']:.4f}, drift: {m['precision'] - tm['precision']:+.4f})")
    typer.echo(f"  Recall: {m['recall']:.4f} (train: {tm['recall']:.4f})")
    typer.echo(f"  Brier: {m['brier']:.4f}")
    typer.echo(f"  {result['summary']}")


@experiment_app.command("frozen-list")
def experiment_frozen_list(
    artifact_dir: str = "./artifacts",
) -> None:
    """List all frozen models."""
    models = list_frozen_models(Path(artifact_dir))
    if not models:
        typer.echo("No frozen models found.")
        return
    for m in models:
        typer.echo(f"  {m.model_id}  cutoff={m.train_cutoff[:19]}  thresh={m.threshold:.4f}  features={len(m.feature_cols)}")


@report_app.command("generate")
def report_generate(
    artifact_id: str,
    artifact_dir: str,
    output_file: str,
) -> None:
    """Generate markdown report from an artifact ID."""
    registry = ArtifactRegistry(Path(artifact_dir))
    try:
        artifact = registry.load_experiment(artifact_id)
    except FileNotFoundError:
        typer.echo(f"Artifact {artifact_id} not found in {artifact_dir}", err=True)
        raise typer.Exit(code=1)

    md = generate_markdown_report(artifact)
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)

    typer.echo(f"Report generated at {output_file}")


@app.callback()
def main_callback() -> None:
    """Đảo Vàng - Predictive model for crypto distribution phases."""
    pass
