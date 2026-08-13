"""Unit tests for daily derivative-data collection orchestrator."""
from datetime import datetime, timezone

import pytest

from dao_vang.config.settings import AppSettings
from dao_vang.data.daily_collection import collect_derivatives
from dao_vang.data.manifests.models import CollectionRunManifest
from dao_vang.domain.enums import RunStatus


class _FakeCollector:
    def __init__(self, client, settings):
        self.calls = []

    def collect(self, start_time: datetime, end_time: datetime, run_id: str):
        self.calls.append((start_time, end_time, run_id))
        return CollectionRunManifest(
            collection_run_id=run_id,
            started_at=datetime.now(timezone.utc),
            status=RunStatus.SUCCEEDED,
            data_type="fake",
            range_start=start_time,
            range_end=end_time,
            rows_raw=10,
            collector_version="1.0.0",
        )


@pytest.fixture
def fake_collectors(monkeypatch):
    """Replace all derivative collectors with a fake that records calls."""
    for data_type in (
        "funding",
        "open_interest",
        "taker_ratio",
        "global_ratio",
        "top_ratio",
    ):
        mod = __import__(
            "dao_vang.data.daily_collection", fromlist=["_COLLECTORS"]
        )
        monkeypatch.setitem(mod._COLLECTORS, data_type, _FakeCollector)


def test_collect_derivatives_runs_all_collectors_for_each_symbol(fake_collectors):
    settings = AppSettings()
    symbols = ["BTCUSDT", "ETHUSDT"]

    summary = collect_derivatives(
        symbols=symbols,
        settings=settings,
        hours_back=24,
        run_id="test_run",
    )

    assert summary["run_id"] == "test_run"
    assert summary["symbols"] == symbols
    assert summary["hours_back"] == 24
    # 2 symbols * 5 collectors, each returning 10 rows
    assert summary["total_rows_raw"] == 100
    assert len(summary["manifests"]) == 10
    assert summary["failures"] == []

    # Check symbol rotation
    symbols_in_manifests = {m["symbol"] for m in summary["manifests"]}
    assert symbols_in_manifests == set(symbols)


def test_collect_derivatives_requires_symbols():
    with pytest.raises(ValueError):
        collect_derivatives(symbols=[], settings=AppSettings())


def test_collect_derivatives_requires_positive_hours_back():
    with pytest.raises(ValueError):
        collect_derivatives(
            symbols=["BTCUSDT"], settings=AppSettings(), hours_back=0
        )
