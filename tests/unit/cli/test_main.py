from typer.testing import CliRunner

from dao_vang.cli.main import app

runner = CliRunner()


def test_app_help() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "data" in result.stdout
    assert "labels" in result.stdout
    assert "features" in result.stdout
    assert "experiment" in result.stdout
    assert "report" in result.stdout


def test_invalid_command() -> None:
    result = runner.invoke(app, ["nonexistent_command"])
    assert result.exit_code != 0
