import json
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from dao_vang.scanner.research_v3_discovery import discover, enrich
from tests.unit.scanner.test_research_v3 import START, setup  # noqa: F401


def ticker(symbol, change=35, volume=2_000_000, now=START):
    return {
        "symbol": symbol,
        "priceChangePercent": str(change),
        "lastPrice": "10",
        "quoteVolume": str(volume),
        "closeTime": now.timestamp() * 1000,
    }


def test_positive_universe_does_not_depend_on_legacy_pump_filter(tmp_path):
    result = discover(
        [
            ticker("BRUSDT"),
            ticker("AINUSDT"),
            ticker("DOWNUSDT", -35),
            ticker("USDCUSDT"),
            ticker("LOWUSDT", 40, 100),
        ],
        storage=tmp_path,
        now=START,
    )
    assert set(result["collection_symbols"]) == {"BRUSDT", "AINUSDT"}
    assert result["market_count"] == 3
    assert (
        next(i for i in result["items"] if i["symbol"] == "LOWUSDT")["discovery_reason"]
        == "below_volume"
    )


def test_first_seen_survives_restart_and_short_dip_but_capacity_is_explicit(tmp_path):
    first = discover([ticker("BRUSDT")], storage=tmp_path, now=START)
    later = START + timedelta(minutes=5)
    result = discover(
        [ticker("BRUSDT", 40, now=later), ticker("AINUSDT", 60, now=later)],
        storage=tmp_path,
        now=later,
        capacity=1,
    )
    assert result["collection_symbols"] == ["AINUSDT"]
    assert result["deferred_count"] == 1
    assert result["first_seen"]["BRUSDT"] == first["first_seen"]["BRUSDT"]
    dipped = discover([], storage=tmp_path, now=later)
    assert set(dipped["collection_symbols"]) == {"BRUSDT", "AINUSDT"}
    expired = discover([], storage=tmp_path, now=START + timedelta(hours=7))
    assert expired["collection_symbols"] == []


def test_missing_24h_history_is_visible_not_misreported_as_low_score(setup):  # noqa: F811
    conn, args = setup
    now = START + timedelta(minutes=5)
    conn.execute("UPDATE feature_results SET price_ret_24h=NULL")
    discovery = discover(
        [ticker("TESTUSDT", now=now), ticker("ABSENTUSDT", now=now)],
        storage=args["storage"],
        now=now,
    )
    result = enrich(conn, discovery, now=now)
    by_symbol = {i["symbol"]: i for i in result["items"]}
    assert by_symbol["TESTUSDT"]["discovery_reason"] == "history_24h_pending"
    assert by_symbol["ABSENTUSDT"]["discovery_reason"] == "features_pending"
    assert by_symbol["TESTUSDT"]["feature_return_24h"] is None


def test_open_position_retained_after_leaving_gainers(tmp_path):
    with sqlite3.connect(tmp_path / "observations.sqlite") as conn:
        conn.executescript(
            "CREATE TABLE observations (id TEXT, symbol TEXT, timestamp TEXT, selected INTEGER); CREATE TABLE outcomes (id TEXT, payload TEXT);"
        )
        conn.execute(
            "INSERT INTO observations VALUES ('a','POSITIONUSDT',?,1)",
            [START.isoformat()],
        )
        conn.execute(
            "INSERT INTO outcomes VALUES ('a',?)", [json.dumps({"status": "open"})]
        )
    result = discover([], storage=tmp_path, now=START + timedelta(hours=24))
    assert result["collection_symbols"] == ["POSITIONUSDT"]
    assert (
        discover([], storage=tmp_path, now=START + timedelta(hours=50))[
            "collection_symbols"
        ]
        == []
    )


def test_stale_ticker_visible_but_not_eligible(tmp_path):
    result = discover(
        [ticker("BRUSDT")], storage=tmp_path, now=START + timedelta(hours=1)
    )
    assert result["items"][0]["discovery_reason"] == "ticker_stale"
    assert result["collection_symbols"] == []


@pytest.mark.parametrize("legacy_symbols", [[], ["OLDUSDT"]])
def test_daemon_collects_v3_universe_even_when_legacy_list_is_empty(tmp_path, monkeypatch, legacy_symbols):
    from dao_vang.config.settings import AppSettings
    from dao_vang.scanner import daemon as module
    from dao_vang.scanner import research_v3, research_v3_discovery

    settings = AppSettings(research_v3_enabled=True)
    settings.paths.data_dir = tmp_path
    settings.candidate_comparison.enabled = False
    settings.scanner.regime_gate_enabled = False
    daemon = MagicMock(spec=module.ScannerDaemon)
    daemon._settings = settings
    daemon._scanner_cfg = settings.scanner
    daemon._cycle_count = 2
    daemon._alert_store = MagicMock()
    daemon._alert_store.get_episode_tracking_symbols.return_value = []
    daemon._normalize_and_timeline.return_value = False
    daemon._score_and_alert_composite.return_value = 0
    monkeypatch.setattr(module, "build_scan_list", lambda config: legacy_symbols)
    monkeypatch.setattr(module, "scan_pumps", lambda config, symbols: [])
    monkeypatch.setattr(module, "DuckDBQueryLayer", MagicMock())
    monkeypatch.setattr(module, "resolve_pending_outcomes", lambda *args: 0)
    monkeypatch.setattr(research_v3_discovery, "fetch_tickers", lambda base: [ticker("BRUSDT", now=datetime.now(timezone.utc))])
    observed = MagicMock()
    monkeypatch.setattr(research_v3, "run_cycle", observed)
    module.ScannerDaemon._run_cycle(daemon)
    assert set(daemon._collect_all.call_args.args[0]) == set(legacy_symbols + ["BTCUSDT", "BRUSDT"])
    observed.assert_called_once()
    assert observed.call_args.kwargs["discovery"]["collection_symbols"] == ["BRUSDT"]
    assert [call.args[0] for call in daemon._score_and_alert_composite.call_args_list] == legacy_symbols
