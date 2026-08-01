from pathlib import Path

import pytest

from dao_vang.experiments.artifacts import ArtifactRegistry


def test_save_and_load_experiment(tmp_path: Path):
    registry = ArtifactRegistry(base_dir=tmp_path)

    dummy_result = {
        "config": {"hypothesis_id": "test_hyp"},
        "status": "completed",
        "results": {"aggregate": {"precision": 0.8}},
    }

    # Save
    artifact_id = registry.save_experiment(dummy_result)
    assert artifact_id.startswith("exp_")

    # Check file exists
    file_path = tmp_path / f"{artifact_id}.json"
    assert file_path.exists()

    # Load
    loaded = registry.load_experiment(artifact_id)
    assert loaded["artifact_id"] == artifact_id
    assert loaded["data"] == dummy_result
    assert "created_at" in loaded


def test_load_nonexistent_experiment(tmp_path: Path):
    registry = ArtifactRegistry(base_dir=tmp_path)
    with pytest.raises(FileNotFoundError, match="not found"):
        registry.load_experiment("exp_invalid_123")
