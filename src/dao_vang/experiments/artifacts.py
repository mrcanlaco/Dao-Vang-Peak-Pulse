import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


class ArtifactRegistry:
    """
    Registry for persisting experiment artifacts immutably.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save_experiment(self, result: Dict[str, Any]) -> str:
        """
        Saves the experiment result to a JSON file.
        Returns the unique artifact ID.
        """
        now_utc = datetime.now(timezone.utc)
        timestamp = now_utc.strftime("%Y%m%d_%H%M%S")
        short_uuid = uuid.uuid4().hex[:8]
        artifact_id = f"exp_{timestamp}_{short_uuid}"

        file_path = self.base_dir / f"{artifact_id}.json"

        # Inject provenance metadata
        artifact = {
            "artifact_id": artifact_id,
            "created_at": now_utc.isoformat(),
            "data": result,
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(artifact, f, indent=2)

        return artifact_id

    def load_experiment(self, artifact_id: str) -> Dict[str, Any]:
        """
        Loads an experiment artifact by ID.
        """
        file_path = self.base_dir / f"{artifact_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(
                f"Artifact {artifact_id} not found in {self.base_dir}."
            )

        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
