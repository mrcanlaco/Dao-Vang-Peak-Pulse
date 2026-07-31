import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.domain.enums import RunStatus


def test_klines_collector_success(tmp_path: Path) -> None:
    settings = AppSettings()
    settings.paths.data_dir = tmp_path

    mock_client = MagicMock()
    # Mock data: 2 pages
    p1 = [1600000000000, "1", "2", "0.5", "1.5", "10", 1600000299999, "50", 100]
    p2 = [1600000300000, "1", "2", "0.5", "1.5", "10", 1600000599999, "50", 100]
    page1 = [p1, p2] * 500  # 1000 items

    page2 = [[1600000600000, "1", "2", "0.5", "1.5", "10", 1600000899999, "50", 100]]

    mock_client.get.side_effect = [page1, page2]

    collector = KlinesCollector(mock_client, settings)

    start_time = datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)
    end_time = datetime(2020, 9, 13, 12, 41, 40, tzinfo=timezone.utc)

    manifest = collector.collect(start_time, end_time, "test-run-id")

    assert manifest.status == RunStatus.SUCCEEDED
    assert manifest.rows_raw == 1001
    assert manifest.error_count == 0

    # Verify file output
    dt = start_time.date()
    date_str = dt.isoformat()
    target_file = tmp_path / "raw" / "klines" / f"date={date_str}" / "test-run-id.jsonl"
    assert target_file.exists()

    with open(target_file, "r") as f:
        lines = f.readlines()
        assert len(lines) == 2  # 2 requests => 2 envelopes
        env1 = json.loads(lines[0])
        env2 = json.loads(lines[1])
        assert env1["collection_run_id"] == "test-run-id"
        assert len(json.loads(env1["payload_json"])) == 1000
        assert len(json.loads(env2["payload_json"])) == 1


def test_klines_collector_api_error(tmp_path: Path) -> None:
    settings = AppSettings()
    settings.paths.data_dir = tmp_path

    mock_client = MagicMock()
    mock_client.get.side_effect = Exception("API Error")

    collector = KlinesCollector(mock_client, settings)

    start_time = datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)
    end_time = datetime(2020, 9, 13, 12, 41, 40, tzinfo=timezone.utc)

    manifest = collector.collect(start_time, end_time, "test-run-id")

    assert manifest.status == RunStatus.FAILED
    assert manifest.error_count == 1
    assert manifest.rows_raw == 0
