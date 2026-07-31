import typer

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


@app.callback()
def main_callback() -> None:
    """Đảo Vàng - Predictive model for crypto distribution phases."""
    pass
