import copy
import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dao_vang.experiments.distribution_v3 import (
    PARENT,
    SCOUT,
    EvidenceLedger,
    Timing,
    normalize_input,
    replay,
)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/distribution_v3_replay.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_replay_records_all_decisions_and_pairs_lanes(payload):
    result = replay(payload)
    assert len(result["events"]) == 5
    assert len(result["decisions"]) == 10
    assert len(result["evaluations"]) == 2  # shared execution, not double-counted
    for lane in (PARENT, SCOUT):
        assert result["summary"][lane]["selected"] == 1
        assert result["summary"][lane]["resolved_with_costs_and_funding"] == 1
    assert result["evaluations"][0]["label"] == 1
    assert result["evaluations"][1]["label"] is None
    assert not result["live_eligible"]
    assert not result["promotion_eligible"]


def test_scout_never_selects_a_later_different_event(payload):
    payload["snapshots"][-1]["funding_change_8h"] = -0.1
    later = copy.deepcopy(payload["snapshots"][-1])
    later.update(
        feature_time="2026-09-01T05:00:00+00:00",
        features_available_at="2026-09-01T05:00:00+00:00",
        funding_change_8h=0.001,
    )
    payload["snapshots"].append(later)
    result = replay(payload)
    assert result["summary"][PARENT]["selected"] == 1
    assert result["summary"][SCOUT]["selected"] == 0
    assert result["decisions"][-1]["reason"] == "episode_already_consumed"


def test_missing_paths_are_excluded_not_silent_losers(payload):
    del payload["snapshots"][-1]["path"]
    result = replay(payload)
    summary = result["summary"][PARENT]
    assert summary["selected"] == summary["excluded"] == 1
    assert summary["target_rate"] is None
    assert summary["mean_net_return_planned"] is None


def test_ledger_idempotence_normalized_fills_and_immutable_conflict(payload, tmp_path):
    result = replay(payload)
    ledger = EvidenceLedger(tmp_path / "evidence.sqlite")
    assert ledger.save(result)
    assert not ledger.save(replay(payload))
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT count(*) FROM v3_runs").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM v3_events").fetchone()[0] == 5
        assert db.execute("SELECT count(*) FROM v3_decisions").fetchone()[0] == 10
        assert db.execute("SELECT count(*) FROM v3_fills").fetchone()[0] == 4
        assert db.execute("SELECT count(*) FROM v3_funding").fetchone()[0] == 2
    result["summary"][PARENT]["target_rate"] = 0
    with pytest.raises(ValueError, match="immutable run conflict"):
        ledger.save(result)


def test_extended_paths_append_new_run_and_share_candidate_events(payload, tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.sqlite")
    old = copy.deepcopy(payload)
    old["snapshots"][-1].pop("path")
    first, second = replay(old), replay(payload)
    assert first["run_id"] != second["run_id"]
    assert first["events"] == second["events"]
    ledger.save(first)
    ledger.save(second)
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT count(*) FROM v3_runs").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM v3_events").fetchone()[0] == 5


def test_ledger_rolls_back_entire_run_on_event_conflict(payload, tmp_path):
    ledger = EvidenceLedger(tmp_path / "evidence.sqlite")
    first = replay(payload)
    ledger.save(first)
    broken = copy.deepcopy(first)
    broken["run_id"] = "different-run"
    broken["events"][0]["snapshot"]["score"] = 0.9
    with pytest.raises(ValueError, match="immutable event conflict"):
        ledger.save(broken)
    with sqlite3.connect(ledger.path) as db:
        assert db.execute("SELECT count(*) FROM v3_runs").fetchone()[0] == 1


@pytest.mark.parametrize(
    "mutation",
    [
        lambda p: p["snapshots"][0].update(
            features_available_at="2026-09-02T00:00:00Z"
        ),
        lambda p: p["snapshots"][0].update(score=float("nan")),
        lambda p: p["snapshots"].reverse(),
        lambda p: p["snapshots"].append(copy.deepcopy(p["snapshots"][-1])),
        lambda p: p["provenance"].update(evidence_kind="sealed_forward"),
        lambda p: p["provenance"].update(model_checksum="unknown"),
        lambda p: p["snapshots"][0].update(is_stablecoin="false"),
    ],
)
def test_invalid_input_rejected(payload, mutation):
    mutation(payload)
    with pytest.raises(ValueError):
        replay(payload)


def test_cooldown_and_new_episode_are_point_in_time(payload):
    row = normalize_input(payload)["snapshots"][0]
    start = row["feature_time"]
    timing = Timing()
    reasons = []
    for hour in list(range(5)) + list(range(11, 16)) + list(range(28, 33)):
        current = {**row, "feature_time": start + timedelta(hours=hour)}
        reasons.append(timing.decide(current)[0])
    assert reasons[4] == "selected"
    assert reasons[9] == "symbol_cooldown"
    assert reasons[14] == "selected"


def test_confirmation_is_sticky_but_pair_requires_90min_contiguity(payload):
    row = normalize_input(payload)["snapshots"][0]
    start = row["feature_time"]
    timing = Timing()
    for hour in (0, 2, 4):
        reason, _ = timing.decide(
            {**row, "feature_time": start + timedelta(hours=hour)}
        )
        assert reason == "confirmation_pending"
    reason, _ = timing.decide({**row, "feature_time": start + timedelta(hours=5)})
    assert reason == "selected"


def test_cli_twice_is_idempotent_and_research_only(tmp_path):
    from dao_vang.cli.main import app

    args = [
        "experiment",
        "replay-v3",
        str(FIXTURE),
        "--ledger-path",
        str(tmp_path / "cli.sqlite"),
    ]
    runner = CliRunner()
    first = runner.invoke(app, args)
    assert first.exit_code == 0, first.output
    assert json.loads(first.stdout)["inserted"]
    second = runner.invoke(app, args)
    assert second.exit_code == 0, second.output
    assert not json.loads(second.stdout)["inserted"]
    assert not json.loads(second.stdout)["live_eligible"]


def test_locked_reference_tolerance_only_after_confirmations(payload):
    payload["snapshots"][-1]["score"] = 0.29
    assert replay(payload)["summary"][PARENT]["selected"] == 1
    payload["snapshots"][-1]["score"] = 0.28
    assert replay(payload)["summary"][PARENT]["selected"] == 0
    for row in payload["snapshots"]:
        row["score"] = 0.30
    assert replay(payload)["summary"][PARENT]["selected"] == 0


def test_machine_readable_standard_matches_runtime():
    import yaml

    from dao_vang.labels.specs.distribution_short_v3 import SPEC, TIMING

    root = Path(__file__).resolve().parents[3]
    config = yaml.safe_load(
        (root / "configs/distribution_v3_research_standard.yaml").read_text("utf-8")
    )
    assert config["version"] == SPEC.version
    assert config["engine_version"] == SPEC.engine_version
    assert config["live_eligible"] is False
    objective = config["objective"]
    assert objective["horizon_hours"] == SPEC.horizon_hours
    assert objective["bar_minutes"] == SPEC.bar_minutes
    assert objective["success_target_from_weighted_average"] == SPEC.target
    assert objective["hard_stop_from_weighted_average"] == SPEC.stop
    assert objective["cost_per_side_on_traded_notional"] == SPEC.cost_per_side
    execution = config["execution_policy"]
    assert execution["policy_id"] == SPEC.policy_id
    assert tuple(execution["entry_offsets_from_entry1"]) == SPEC.offsets
    assert tuple(execution["allocation_weights"]) == SPEC.notional_weights
    assert execution["scale_in_window_hours"] == SPEC.scale_in_hours
    assert execution["intrabar_rule"] == SPEC.intrabar_rule
    assert execution["funding_rule"] == SPEC.funding_rule
    timing = config["timing_policy"]
    assert timing["version"] == TIMING.version
    assert timing["min_peak_price_return_24h"] == TIMING.min_armed_peak_return_24h
    assert timing["min_episode_age_hours"] == TIMING.min_episode_age_hours
    assert timing["consecutive_confirmations"] == TIMING.confirmations
    assert timing["model_probability_threshold"] == TIMING.score_threshold
    assert (
        timing["post_confirmation_score_tolerance"]
        == TIMING.post_confirmation_score_tolerance
    )
    assert timing["max_confirmation_gap_minutes"] == TIMING.max_confirmation_gap_minutes
    assert timing["episode_gap_hours"] == TIMING.episode_gap_hours
    assert timing["symbol_cooldown_hours"] == TIMING.cooldown_hours


def test_selector_matches_locked_challenger_on_multisymbol_sequence(payload):
    import random
    import runpy

    import pandas as pd

    root = Path(__file__).resolve().parents[3]
    reference = runpy.run_path(str(root / "scripts/forward48_timing_backtest.py"))
    rng = random.Random(703)
    start = normalize_input(payload)["snapshots"][0]["feature_time"]
    rows = []
    for hour in range(120):
        for symbol in ("AAAUSDT", "BBBUSDT", "CCCUSDT"):
            if hour % 30 in range(10, 18):
                continue  # new episodes, cooldown and latching
            rows.append(
                {
                    "symbol": symbol,
                    "feature_time": start + timedelta(hours=hour),
                    "price_ret_24h": rng.choice([0.16, 0.22, 0.35]),
                    "probability": rng.choice([0.15, 0.28, 0.30, 0.40, 0.55]),
                    "threshold": 0.39,
                    "distance_from_high_24h": -0.02,
                    "price_ret_5m": 0.01,
                }
            )
    frame = pd.DataFrame(rows)
    frame["episode_id"] = reference["_episode_ids"](frame)
    policy = reference["TimingPolicy"](
        min_peak_pump_24h=0.30, confirmations=2, min_episode_age_hours=4
    )
    expected = reference["select_signals"](frame, policy)
    timing = Timing()
    selected = []
    for row in rows:
        reason, _ = timing.decide(
            {**row, "score": row["probability"], "is_stablecoin": False}
        )
        if reason == "selected":
            selected.append((row["symbol"], row["feature_time"]))
    assert selected
    assert selected == list(
        expected[["symbol", "feature_time"]].itertuples(index=False, name=None)
    )
