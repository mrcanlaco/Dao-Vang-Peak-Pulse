from datetime import datetime, timedelta, timezone

from dao_vang.scanner.research_v3 import _outcome_is_terminal

NOW = datetime(2026, 9, 3, tzinfo=timezone.utc)
ENTRY = datetime(2026, 9, 1, tzinfo=timezone.utc)


def test_stopped_observation_remains_open_until_post_stop_resolves():
    assert not _outcome_is_terminal(
        {"status": "stop", "post_stop": {"status": "incomplete_after_stop"}},
        now=NOW,
        entry_time=ENTRY,
    )
    assert _outcome_is_terminal(
        {"status": "stop", "post_stop": {"status": "target_after_stop"}},
        now=NOW,
        entry_time=ENTRY,
    )
    assert _outcome_is_terminal(
        {"status": "stop", "post_stop": {"status": "timeout_after_stop"}},
        now=NOW,
        entry_time=ENTRY,
    )


def test_legacy_stop_without_dual_result_is_replayed():
    assert not _outcome_is_terminal(
        {"status": "stop"},
        now=NOW,
        entry_time=ENTRY,
    )
    assert _outcome_is_terminal(
        {"status": "target"},
        now=NOW,
        entry_time=ENTRY,
    )


def test_incomplete_final_is_terminal_only_after_original_horizon():
    assert not _outcome_is_terminal(
        {"status": "incomplete_final"},
        now=ENTRY + timedelta(hours=48, minutes=30),
        entry_time=ENTRY,
    )
    assert _outcome_is_terminal(
        {"status": "incomplete_final"},
        now=ENTRY + timedelta(hours=49),
        entry_time=ENTRY,
    )

