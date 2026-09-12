"""HTTP boundary tests for the locked production forward-test protocol."""

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pandas as pd

from dao_vang.data.storage import duckdb as storage
from dao_vang.experiments import forward_evidence
from dao_vang.web import api_server


def _write_protocol(path: Path, model_id: str = "frozen_locked") -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": "forward_evidence_v1",
                "model_id": model_id,
                "evaluation_start": "2026-09-01T00:00:00Z",
                "evaluation_end": None,
                "cutoff_policy": "max_train_cutoff_and_freeze_time",
                "universe_policy": {
                    "mode": "all_scored_rows",
                    "source": "feature_results",
                },
                "label_version": "distribution_short_v1",
                "label_horizon_hours": 24,
                "event_gap_minutes": 240,
                "min_evaluated_rows": 1000,
                "min_positive_events": 50,
                "min_predicted_events": 30,
                "min_evaluation_days": 7,
                "expected_model_sha256": "0" * 64,
                "expected_calibrator_sha256": "1" * 64,
                "expected_metadata_sha256": "2" * 64,
                "external_api_cost_per_1000_rows_usd": 0,
                "compute_cost_per_hour_usd": None,
            }
        ),
        encoding="utf-8",
    )


def _handler() -> api_server.APIHandler:
    handler = object.__new__(api_server.APIHandler)
    handler.wfile = io.BytesIO()
    handler._set_headers = MagicMock()
    return handler


def test_unapproved_model_returns_protocol_required_without_querying_db(
    tmp_path: Path,
    monkeypatch,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    _write_protocol(protocol_path)
    monkeypatch.setattr(
        api_server,
        "FORWARD_TEST_PROTOCOL_PATH",
        protocol_path,
    )

    class UnexpectedQueryLayer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("DB must not be queried for an unapproved model")

    monkeypatch.setattr(storage, "DuckDBQueryLayer", UnexpectedQueryLayer)
    handler = _handler()

    api_server.APIHandler.evaluate_frozen_model(handler, "frozen_unapproved")

    handler._set_headers.assert_called_once_with(200)
    payload = json.loads(handler.wfile.getvalue())
    assert payload["status"] == "protocol_required"
    assert payload["protocol_model_id"] == "frozen_locked"
    assert payload["metrics"] is None


def test_approved_model_filters_label_contract_and_uses_strict_evaluator(
    tmp_path: Path,
    monkeypatch,
) -> None:
    protocol_path = tmp_path / "protocol.json"
    _write_protocol(protocol_path)
    monkeypatch.setattr(
        api_server,
        "FORWARD_TEST_PROTOCOL_PATH",
        protocol_path,
    )
    captured: dict[str, Any] = {}

    class FakeRelation:
        def df(self) -> pd.DataFrame:
            return pd.DataFrame({"feature_time": ["2026-09-10T00:00:00Z"]})

    class FakeConnection:
        def execute(
            self,
            query: str,
            parameters: list[Any],
        ) -> FakeRelation:
            captured["query"] = query
            captured["parameters"] = parameters
            return FakeRelation()

    class FakeQueryLayer:
        def __init__(self, db_path: str, read_only: bool = False) -> None:
            captured["db_path"] = db_path
            captured["read_only"] = read_only
            self.conn = FakeConnection()

        def close(self) -> None:
            captured["closed"] = True

    def fake_evaluate(
        model_id: str,
        frame: pd.DataFrame,
        protocol: forward_evidence.ForwardTestProtocol,
        artifact_dir: Path,
    ) -> dict[str, Any]:
        captured["model_id"] = model_id
        captured["frame_rows"] = len(frame)
        captured["protocol"] = protocol
        captured["artifact_dir"] = artifact_dir
        return {
            "status": "insufficient_evidence",
            "model_id": model_id,
            "metrics": None,
        }

    monkeypatch.setattr(storage, "DuckDBQueryLayer", FakeQueryLayer)
    monkeypatch.setattr(
        forward_evidence,
        "evaluate_forward_evidence",
        fake_evaluate,
    )
    handler = _handler()

    api_server.APIHandler.evaluate_frozen_model(handler, "frozen_locked")

    handler._set_headers.assert_called_once_with(200)
    payload = json.loads(handler.wfile.getvalue())
    assert payload["status"] == "insufficient_evidence"
    assert payload["metrics"] is None
    assert captured["parameters"] == [24, "distribution_short_v1"]
    assert "l.horizon_hours = ?" in captured["query"]
    assert "l.label_version = ?" in captured["query"]
    assert captured["read_only"] is True
    assert captured["closed"] is True
    assert captured["frame_rows"] == 1
