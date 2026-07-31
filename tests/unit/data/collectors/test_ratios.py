from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.ratios import GlobalRatioCollector, TopRatioCollector
from dao_vang.domain.enums import RunStatus


def test_global_ratio_collector_success(tmp_path: Path) -> None:
    settings = AppSettings()
    settings.paths.data_dir = tmp_path

    mock_client = MagicMock()
    # Mock data: 2 pages
    p1 = {
        "symbol": "BTCUSDT",
        "longShortRatio": "1.5",
        "longAccount": "0.6",
        "shortAccount": "0.4",
        "timestamp": 1600000000000,
    }
    p2 = {
        "symbol": "BTCUSDT",
        "longShortRatio": "1.5",
        "longAccount": "0.6",
        "shortAccount": "0.4",
        "timestamp": 1600000300000,
    }
    page1 = [p1, p2] * 250  # 500 items

    page2 = [
        {
            "symbol": "BTCUSDT",
            "longShortRatio": "1.5",
            "longAccount": "0.6",
            "shortAccount": "0.4",
            "timestamp": 1600000600000,
        }
    ]

    mock_client.get.side_effect = [page1, page2]

    collector = GlobalRatioCollector(mock_client, settings)

    start_time = datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)
    end_time = datetime(2020, 9, 13, 12, 41, 40, tzinfo=timezone.utc)

    manifest = collector.collect(start_time, end_time, "test-run-id")

    assert manifest.status == RunStatus.SUCCEEDED
    assert manifest.rows_raw == 501
    assert manifest.error_count == 0

    # Verify file output
    dt = start_time.date()
    date_str = dt.isoformat()
    target_file = (
        tmp_path / "raw" / "global_ratio" / f"date={date_str}" / "test-run-id.jsonl"
    )
    assert target_file.exists()


def test_top_ratio_collector_success(tmp_path: Path) -> None:
    settings = AppSettings()
    settings.paths.data_dir = tmp_path

    mock_client = MagicMock()
    # Mock data: 1 page
    p1 = {
        "symbol": "BTCUSDT",
        "longShortRatio": "1.5",
        "longAccount": "0.6",
        "shortAccount": "0.4",
        "timestamp": 1600000000000,
    }
    page1 = [p1]

    mock_client.get.side_effect = [page1]

    collector = TopRatioCollector(mock_client, settings)

    start_time = datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)
    end_time = datetime(2020, 9, 13, 12, 41, 40, tzinfo=timezone.utc)

    manifest = collector.collect(start_time, end_time, "test-run-id2")

    assert manifest.status == RunStatus.SUCCEEDED
    assert manifest.rows_raw == 1
    assert manifest.error_count == 0

    # Verify file output
    dt = start_time.date()
    date_str = dt.isoformat()
    target_file = (
        tmp_path / "raw" / "top_ratio" / f"date={date_str}" / "test-run-id2.jsonl"
    )
    assert target_file.exists()


def test_ratios_collector_api_error(tmp_path: Path) -> None:
    settings = AppSettings()
    settings.paths.data_dir = tmp_path

    mock_client = MagicMock()
    mock_client.get.side_effect = Exception("API Error")

    collector = GlobalRatioCollector(mock_client, settings)

    start_time = datetime(2020, 9, 13, 12, 26, 40, tzinfo=timezone.utc)
    end_time = datetime(2020, 9, 13, 12, 41, 40, tzinfo=timezone.utc)

    manifest = collector.collect(start_time, end_time, "test-run-id")

    assert manifest.status == RunStatus.FAILED
    assert manifest.error_count == 1
    assert manifest.rows_raw == 0
