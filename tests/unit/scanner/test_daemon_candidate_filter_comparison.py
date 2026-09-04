from __future__ import annotations

import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import duckdb

from dao_vang.config.settings import AppSettings
from dao_vang.scanner.candidate_filter_store import CandidateFilterStore
from dao_vang.scanner.candidate_filter_v2 import (
    CandidateV2Decision,
    MarketObservation,
)
from dao_vang.scanner.daemon import ScannerDaemon
from dao_vang.scanner.pump_filter import PumpCandidate


def test_shadow_comparison_persists_paired_rows_without_telegram_lane(tmp_path) -> None:
    observed_at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    snapshot_path = tmp_path / "comparison.json"
    state_path = tmp_path / "state.json"
    settings = AppSettings(
        candidate_comparison={
            "enabled": True,
            "snapshot_path": snapshot_path,
            "state_path": state_path,
            "min_resolved": 200,
            "min_positive_events": 50,
        }
    )
    daemon = ScannerDaemon.__new__(ScannerDaemon)
    daemon._settings = settings
    daemon._candidate_filter_state_path = state_path
    daemon._candidate_filter_comparison_path = snapshot_path
    daemon._candidate_filter_store = CandidateFilterStore()
    daemon._run_id = "run-test"
    daemon._cycle_count = 1
    daemon._last_candidate_comparison = {}

    decisions = [
        CandidateV2Decision(
            symbol="AAAUSDT",
            selected=False,
            stage="PUMPING",
            rank_score=0.5,
        ),
        CandidateV2Decision(
            symbol="BBBUSDT",
            selected=True,
            stage="DISTRIBUTING",
            rank=1,
            rank_score=1.5,
            evidence_groups=("price_structure", "order_flow"),
        ),
    ]
    observations = [
        MarketObservation(symbol, observed_at, 101, 99, 100)
        for symbol in ("AAAUSDT", "BBBUSDT")
    ]
    next_state = {"AAAUSDT": {"last_evaluated_at": observed_at}}
    conn = duckdb.connect(":memory:")

    with patch(
        "dao_vang.scanner.daemon.scan_candidate_filter_v2",
        return_value=(decisions, observations, next_state),
    ) as scan_v2:
        daemon._run_candidate_filter_comparison(
            db=SimpleNamespace(conn=conn),
            universe_tickers=[
                {
                    "symbol": "AAAUSDT",
                    "quoteVolume": "3000000",
                    "lastPrice": "100",
                },
                {
                    "symbol": "BBBUSDT",
                    "quoteVolume": "2000000",
                    "lastPrice": "100",
                },
            ],
            production_symbols=["AAAUSDT"],
            champion_score_symbols=["AAAUSDT"],
            pump_candidates=[
                PumpCandidate(
                    "AAAUSDT",
                    0.8,
                    2,
                    0.9,
                    110,
                    100,
                    3_000_000,
                )
            ],
            comparison_now=observed_at,
            champion_fallback_all=False,
        )

    scan_v2.assert_called_once()
    assert (
        conn.execute("SELECT count(*) FROM candidate_filter_opportunities").fetchone()[
            0
        ]
        == 2
    )
    assert (
        conn.execute("SELECT count(*) FROM candidate_filter_decisions").fetchone()[0]
        == 4
    )
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert payload["telegram_lane"] == "pump_filter_v1"
    assert payload["challenger_telegram_enabled"] is False
    assert payload["champion_selected"] == 1
    assert payload["challenger_selected"] == 1
    assert payload["challenger_only"] == 1
    assert payload["status"] == "collecting_outcomes"
    assert state_path.exists()
