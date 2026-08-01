from pathlib import Path

from typer.testing import CliRunner

from dao_vang.cli.main import app

runner = CliRunner()


def test_smoke_experiment_to_report(tmp_path: Path):
    artifact_dir = tmp_path / "artifacts"
    report_file = tmp_path / "report.md"

    # 1. Run experiment
    res_exp = runner.invoke(
        app,
        [
            "experiment",
            "run",
            "hyp_test",
            "baseline_test",
            "v1",
            "v1",
            "v1",
            "v1",
            "42",
            "--metrics",
            "precision,recall",
            "--artifact-dir",
            str(artifact_dir),
        ],
    )

    assert res_exp.exit_code == 0
    assert "Experiment completed" in res_exp.output

    # Extract artifact ID
    # Output format: Experiment completed. Artifact ID: exp_...
    output_parts = res_exp.output.strip().split("Artifact ID: ")
    assert len(output_parts) == 2
    artifact_id = output_parts[1].strip()

    # 2. Generate report
    res_rep = runner.invoke(
        app, ["report", "generate", artifact_id, str(artifact_dir), str(report_file)]
    )

    assert res_rep.exit_code == 0
    assert "Report generated" in res_rep.output

    # 3. Verify report exists and has content
    assert report_file.exists()
    content = report_file.read_text(encoding="utf-8")
    assert f"# Experiment Report: {artifact_id}" in content
    assert "**Hypothesis ID:** hyp_test" in content
