from pathlib import Path

from typer.testing import CliRunner

from dao_vang.cli.main import app

runner = CliRunner()


def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Đảo Vàng CLI" in result.stdout
    assert "Đảo Vàng CLI" in result.output
    assert "data" in result.output
    assert "experiment" in result.output


def test_report_generate_not_found(tmp_path: Path):
    out_file = tmp_path / "report.md"
    result = runner.invoke(
        app, ["report", "generate", "exp_non_existent", str(tmp_path), str(out_file)]
    )
    assert result.exit_code == 1
    assert "not found" in result.output
