from __future__ import annotations

import io
import json
from unittest.mock import MagicMock

from dao_vang.web import api_server


def test_candidate_filter_comparison_endpoint_serves_fallback(monkeypatch, tmp_path) -> None:
    comp_file = tmp_path / "candidate_filter_comparison.json"
    monkeypatch.setattr(api_server, "CANDIDATE_FILTER_COMPARISON_PATH", comp_file)

    handler = object.__new__(api_server.APIHandler)
    handler.wfile = io.BytesIO()
    handler._set_headers = MagicMock()

    handler.get_candidate_filter_comparison()

    raw_response = handler.wfile.getvalue().decode("utf-8")
    data = json.loads(raw_response)

    assert data["available"] is False
    assert "enabled" in data
    assert data["champion_version"] == "pump_filter_v1"
    assert data["challenger_version"] == "candidate_filter_v2"


def test_candidate_filter_comparison_endpoint_serves_existing_snapshot(monkeypatch, tmp_path) -> None:
    comp_file = tmp_path / "candidate_filter_comparison.json"
    comp_file.write_text(
        json.dumps({
            "generated_at": "2026-08-15T00:00:00+00:00",
            "enabled": True,
            "universe_count": 120,
            "champion_selected": 8,
            "challenger_selected": 12,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_server, "CANDIDATE_FILTER_COMPARISON_PATH", comp_file)

    handler = object.__new__(api_server.APIHandler)
    handler.wfile = io.BytesIO()
    handler._set_headers = MagicMock()

    handler.get_candidate_filter_comparison()

    raw_response = handler.wfile.getvalue().decode("utf-8")
    data = json.loads(raw_response)

    assert data["available"] is True
    assert data["enabled"] is True
    assert data["universe_count"] == 120
    assert data["champion_selected"] == 8
    assert data["challenger_selected"] == 12
