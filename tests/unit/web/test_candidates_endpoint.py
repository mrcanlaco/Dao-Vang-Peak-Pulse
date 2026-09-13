from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from dao_vang.web import api_server


def _serve_snapshot(monkeypatch: pytest.MonkeyPatch, tmp_path, generated_at: str) -> list[dict]:
    snapshot_path = tmp_path / "candidate_snapshot.json"
    snapshot_path.write_text(
        json.dumps(
            {
                "generated_at": generated_at,
                "timestamp_timezone": "UTC",
                "rows": [
                    {
                        "symbol": "TESTUSDT",
                        "scan_time": generated_at,
                        "score": 72.5,
                        "recommendation": "HIGH_CONFIDENCE",
                        "close_price": 1.25,
                        "oi_change_24h": -0.05,
                        "funding_rate": 0.0001,
                        "taker_sell_ratio": 0.62,
                        "volume_24h_usd": 2_000_000,
                        "model_probability": 0.75,
                        "calibrated_probability": 0.68,
                        "data_quality_score": 0.95,
                        "quality_status": "valid",
                        "max_feature_age_minutes": 2.0,
                        "horizon_hours": 24,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(api_server, "CANDIDATE_SNAPSHOT_PATH", snapshot_path)
    handler = object.__new__(api_server.APIHandler)
    handler.wfile = io.BytesIO()
    handler._set_headers = MagicMock()
    handler.get_candidates()
    return json.loads(handler.wfile.getvalue())


def test_candidates_expose_decision_fields_and_fresh_alertable_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    generated_at = datetime.now(timezone.utc).isoformat()
    rows = _serve_snapshot(monkeypatch, tmp_path, generated_at)

    assert len(rows) == 1
    assert rows[0]["recommendation"] == "HIGH_CONFIDENCE"
    assert rows[0]["calibrated_probability"] == 0.68
    assert rows[0]["quality_status"] == "valid"
    assert rows[0]["is_stale"] is False
    assert rows[0]["alertable"] is True


def test_candidates_fail_closed_when_snapshot_is_stale(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    generated_at = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    rows = _serve_snapshot(monkeypatch, tmp_path, generated_at)

    assert rows[0]["is_stale"] is True
    assert rows[0]["alertable"] is False
