from __future__ import annotations

import json
from datetime import datetime, timezone

from dao_vang.web import api_server


def _configure_paths(monkeypatch, tmp_path) -> tuple[object, object, object]:
    heartbeat = tmp_path / "scanner_heartbeat.json"
    trigger = tmp_path / "scanner_trigger.flag"
    runtime = tmp_path / "scanner_runtime_state.json"
    monkeypatch.setattr(api_server, "HEARTBEAT_PATH", heartbeat)
    monkeypatch.setattr(api_server, "TRIGGER_PATH", trigger)
    monkeypatch.setattr(api_server, "RUNTIME_STATE_PATH", runtime)
    return heartbeat, trigger, runtime


def test_plain_refresh_coalesces_into_running_cycle(monkeypatch, tmp_path) -> None:
    heartbeat, trigger, _ = _configure_paths(monkeypatch, tmp_path)
    heartbeat.write_text(
        json.dumps(
            {
                "cycle": 7,
                "last_cycle_status": "running",
                "last_cycle_started_at": "2026-08-13T08:00:00+00:00",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    result = api_server._request_scan()

    assert result == {
        "status": "in_progress",
        "queued": False,
        "cycle": 7,
        "started_at": "2026-08-13T08:00:00+00:00",
    }
    assert not trigger.exists()


def test_plain_refresh_queues_when_scanner_is_idle(monkeypatch, tmp_path) -> None:
    heartbeat, trigger, _ = _configure_paths(monkeypatch, tmp_path)
    heartbeat.write_text(
        json.dumps(
            {
                "cycle": 7,
                "last_cycle_status": "ok",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    result = api_server._request_scan()

    assert result == {"status": "queued", "queued": True}
    assert json.loads(trigger.read_text(encoding="utf-8"))["requested_at"]


def test_mode_change_always_queues_next_cycle(monkeypatch, tmp_path) -> None:
    heartbeat, trigger, runtime = _configure_paths(monkeypatch, tmp_path)
    heartbeat.write_text(
        json.dumps(
            {
                "cycle": 7,
                "last_cycle_status": "running",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )

    result = api_server._request_scan(["gainers", "losers"])

    assert result == {"status": "queued", "queued": True}
    assert trigger.exists()
    state = json.loads(runtime.read_text(encoding="utf-8"))
    assert state["scan_modes"] == ["gainers", "losers"]
    assert state["scan_mode"] == "gainers,losers"
