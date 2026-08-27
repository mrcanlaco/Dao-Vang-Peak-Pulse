from __future__ import annotations

import json

from dao_vang.web.api_server import _anomaly_fields


def test_anomaly_payload_decodes_report_and_marks_volume_spike() -> None:
    row = {
        "anomaly_score": 76.0,
        "anomaly_level": "ELEVATED",
        "anomaly_count": 2,
        "anomalies_json": json.dumps(
            {
                "score": 76.0,
                "level": "ELEVATED",
                "categories": ["volume", "funding"],
                "anomalies": [
                    {"code": "volume_spike", "category": "volume"},
                    {"code": "funding_shift", "category": "funding"},
                ],
            }
        ),
    }

    payload = _anomaly_fields(row)

    assert payload["anomaly_score"] == 76.0
    assert payload["anomaly_level"] == "ELEVATED"
    assert payload["anomaly_count"] == 2
    assert payload["anomaly_categories"] == ["volume", "funding"]
    assert payload["is_volume_spike"] is True
    assert [item["code"] for item in payload["anomalies"]] == [
        "volume_spike",
        "funding_shift",
    ]


def test_anomaly_payload_keeps_legacy_rows_safe() -> None:
    payload = _anomaly_fields({"score": 10.0})

    assert payload["anomaly_score"] == 0.0
    assert payload["anomaly_level"] == "NORMAL"
    assert payload["anomaly_count"] == 0
    assert payload["anomalies"] == []
    assert payload["is_volume_spike"] is False
