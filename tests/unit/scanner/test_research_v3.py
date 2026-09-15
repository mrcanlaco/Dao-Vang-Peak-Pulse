import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import duckdb
import numpy as np
import pandas as pd
import pytest

from dao_vang.experiments.train_distribution_v2 import SERVING_FEATURE_COLS
from dao_vang.scanner import research_v3
from dao_vang.web import api_server

START = datetime(2026, 9, 14, tzinfo=timezone.utc)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    model = MagicMock()
    model.predict_proba.side_effect = lambda frame: np.tile([0.5, 0.5], (len(frame), 1))
    calibrator = MagicMock()
    calibrator.transform.side_effect = lambda scores: scores
    monkeypatch.setattr(research_v3, "file_hash", lambda path: research_v3.MODEL_SHA)
    monkeypatch.setattr("joblib.load", lambda path: {
        "model": model, "calibrator": calibrator, "feature_columns": SERVING_FEATURE_COLS,
    })
    conn = duckdb.connect()
    features = pd.DataFrame([{**dict.fromkeys(SERVING_FEATURE_COLS, 0.1),
                              "symbol": "TESTUSDT", "feature_time": START + timedelta(hours=i, minutes=5, milliseconds=-1),
                              "price_ret_24h": 0.35, "funding_percentile_30d": 0.85}
                             for i in range(5)])
    conn.register("features", features)
    conn.execute("CREATE TABLE feature_results AS SELECT * FROM features")
    conn.execute("""CREATE TABLE kline (symbol VARCHAR, market VARCHAR, interval VARCHAR,
                    close_time TIMESTAMPTZ, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, quality_status VARCHAR)""")
    for i in range(5):
        conn.execute("INSERT INTO kline VALUES (?, ?, ?, ?, 100, 101, 99, 100, 'valid')",
                     ["TESTUSDT", "USD-M Futures", "5m", START + timedelta(hours=i, minutes=5, milliseconds=-1)])
    yield conn, {"storage": tmp_path / "research_v3", "model_path": tmp_path / "model.joblib"}
    conn.close()


def test_forward_only_restart_fills_and_terminal_outcome(setup):
    conn, args = setup
    first = research_v3.observe(conn, **args, now=START)
    assert first["candidate_count"] == 0
    for hour in range(5):
        result = research_v3.observe(conn, **args, now=START + timedelta(hours=hour, minutes=5))
    assert result["candidate_count"] == 5
    assert result["entry_count"] == 1
    assert result["items"][0]["scout"]
    assert result["items"][0]["outcome"]["status"] == "open"
    conn.execute("INSERT INTO kline VALUES (?, ?, ?, ?, 100, 106, 90, 100, 'valid')",
                 ["TESTUSDT", "USD-M Futures", "5m", START + timedelta(hours=4, minutes=10, milliseconds=-1)])
    result = research_v3.observe(conn, **args, now=START + timedelta(hours=4, minutes=10))
    assert len(result["items"][0]["outcome"]["fills"]) == 3
    conn.execute("INSERT INTO kline VALUES (?, ?, ?, ?, 100, 103, 82, 83, 'valid')",
                 ["TESTUSDT", "USD-M Futures", "5m", START + timedelta(hours=4, minutes=15, milliseconds=-1)])
    result = research_v3.observe(conn, **args, now=START + timedelta(hours=4, minutes=15))
    outcome = result["items"][0]["outcome"]
    assert outcome["status"] == "target"
    assert outcome["net_return_planned"] is None
    repeated = research_v3.observe(conn, **args, now=START + timedelta(hours=4, minutes=20))
    assert repeated["candidate_count"] == 5
    assert repeated["items"][0]["outcome"] == outcome
    assert not repeated["orders_enabled"] and not repeated["telegram_enabled"]


def test_cold_start_does_not_backfill_old_winners(setup):
    conn, args = setup
    result = research_v3.observe(conn, **args, now=START + timedelta(days=2))
    assert result["candidate_count"] == result["entry_count"] == 0


def test_changed_runtime_identity_fails_closed(setup):
    conn, args = setup
    research_v3.observe(conn, **args, now=START)
    import sqlite3
    with sqlite3.connect(args["storage"] / "observations.sqlite") as ledger:
        state = json.loads(ledger.execute("SELECT payload FROM state").fetchone()[0])
        state["model_checksum"] = "changed"
        ledger.execute("UPDATE state SET payload=?", [json.dumps(state)])
    with pytest.raises(ValueError, match="identity"):
        research_v3.observe(conn, **args, now=START + timedelta(minutes=5))


def test_model_checksum_mismatch_does_not_unpickle(setup, monkeypatch):
    conn, args = setup
    monkeypatch.setattr(research_v3, "file_hash", lambda path: "mismatch")
    load = MagicMock()
    monkeypatch.setattr("joblib.load", load)
    with pytest.raises(ValueError, match="checksum"):
        research_v3.observe(conn, **args, now=START)
    load.assert_not_called()


def test_discovery_does_not_replay_features_from_before_first_seen(setup):
    conn, args = setup
    research_v3.observe(conn, **args, now=START)
    now = START + timedelta(minutes=10)
    discovery = {"collection_symbols": ["TESTUSDT"], "first_seen": {"TESTUSDT": now.isoformat()}}
    result = research_v3.observe(conn, **args, now=now, discovery=discovery)
    assert result["candidate_count"] == 0
    result = research_v3.observe(conn, **args, now=START + timedelta(hours=1, minutes=5), discovery=discovery)
    assert result["candidate_count"] == 1


def test_five_minute_discovery_does_not_accelerate_hourly_confirmations(setup):
    conn, args = setup
    research_v3.observe(conn, **args, now=START)
    conn.execute("INSERT INTO feature_results SELECT * REPLACE (feature_time + INTERVAL '5 minutes' AS feature_time) FROM feature_results WHERE feature_time < ?", [START + timedelta(minutes=5)])
    conn.execute("INSERT INTO kline SELECT * REPLACE (close_time + INTERVAL '5 minutes' AS close_time) FROM kline WHERE close_time < ?", [START + timedelta(minutes=5)])
    result = research_v3.observe(conn, **args, now=START + timedelta(minutes=10))
    assert result["candidate_count"] == 2
    assert result["items"][0]["reason"] == "confirmation_pending"
    assert result["entry_count"] == 0


def test_coverage_migration_preserves_history_and_resets_timing(setup):
    import sqlite3

    conn, args = setup
    research_v3.observe(conn, **args, now=START)
    research_v3.observe(conn, **args, now=START + timedelta(minutes=5))
    with sqlite3.connect(args["storage"] / "observations.sqlite") as ledger:
        state = json.loads(ledger.execute("SELECT payload FROM state").fetchone()[0])
        state["runtime_version"] = "v3_shadow_runtime_v1"
        ledger.execute("UPDATE state SET payload=?", [json.dumps(state)])
    now = START + timedelta(minutes=10)
    result = research_v3.observe(conn, **args, now=now)
    assert result["candidate_count"] == 1
    assert result["activated_at"] == now.isoformat()
    assert result["previous_activated_at"] == START.isoformat()
    with sqlite3.connect(args["storage"] / "observations.sqlite") as ledger:
        state = json.loads(ledger.execute("SELECT payload FROM state").fetchone()[0])
    assert state["timing"]["episodes"] == {}


def test_snapshot_api_disabled_and_stale(tmp_path, monkeypatch):
    monkeypatch.setattr(api_server._settings.paths, "data_dir", tmp_path)
    monkeypatch.setattr(api_server._settings, "research_v3_enabled", True)
    research_v3.atomic_snapshot(tmp_path / "research_v3/snapshot.json",
                               {"status": "running", "updated_at": START - timedelta(days=365), "items": []})
    handler = MagicMock()
    handler.wfile = io.BytesIO()
    # Resolve the real class without starting a server.
    cls = next(value for value in vars(api_server).values()
               if isinstance(value, type) and "get_research_v3" in vars(value))
    cls.get_research_v3(handler)
    assert json.loads(handler.wfile.getvalue())["stale"]
    monkeypatch.setattr(api_server._settings, "research_v3_enabled", False)
    handler.wfile = io.BytesIO()
    cls.get_research_v3(handler)
    assert json.loads(handler.wfile.getvalue())["status"] == "disabled"
