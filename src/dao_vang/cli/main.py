from datetime import datetime, timezone
from pathlib import Path

import duckdb
import typer

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.experiments.artifacts import ArtifactRegistry
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
