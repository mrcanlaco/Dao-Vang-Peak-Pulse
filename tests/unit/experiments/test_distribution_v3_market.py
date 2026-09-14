import json
import sqlite3
from datetime import datetime, timedelta, timezone

import duckdb
import pytest

from dao_vang.experiments.distribution_v3_market import (
    PARENT,
    SCOUT,
    audit_locked_market,
    boundary,
    file_hash,
    load_locked,
    load_paths,
)

END = datetime(2026, 8, 1, 0, 4, 59, 999000, tzinfo=timezone.utc)


@pytest.fixture
def market(tmp_path):
    db = tmp_path / "market.duckdb"
    lock = tmp_path / "lock"
    lock.mkdir()
    (lock / "forward48_timing_research_model.joblib").write_text(
        "not-unpickled", "utf-8"
    )
    keys_path = lock / "forward48_timing_august_locked_signal_keys.csv"
    keys_path.write_text(f"symbol,feature_time\nTESTUSDT,{END.isoformat()}\n", "utf-8")
    (lock / "forward48_timing_august_signals_live.csv").write_text(
        "symbol,feature_time,entry_price,probability,funding_percentile_30d,funding_persistence_7d,funding_change_8h\n"
        f"TESTUSDT,{END.isoformat()},100,0.45,0.85,0.01,0.001\n",
        "utf-8",
    )
    report = {
        "immutable_inputs": {
            "model_sha256": file_hash(lock / "forward48_timing_research_model.joblib"),
            "signal_keys_sha256_before_outcome_load": file_hash(keys_path),
            "august_labels_used_for_model_or_policy_selection": False,
            "threshold": 0.39,
            "selected_policy": dict(
                min_peak_pump_24h=0.3,
                confirmations=2,
                min_episode_age_hours=4,
                min_probability_peak_drop=0.0,
                min_drawdown_from_high=0.0,
                require_ret5_nonpositive=False,
                probability_tolerance=0.1,
            ),
        },
        "august": {"signals": 1},
        "coverage": {"hourly_feature_candidates": 5},
    }
    (lock / "forward48_timing_locked_forward_report.json").write_text(
        json.dumps(report), "utf-8"
    )
    old = tmp_path / "old.csv"
    old.write_text(
        "symbol,signal_time,template_id,status,complete_path,net_return_planned,funding_return_planned\n"
        f"TESTUSDT,{END.isoformat()},compact_0_3_6,target,True,0.038,0\n",
        "utf-8",
    )
    with duckdb.connect(str(db)) as conn:
        conn.execute("""CREATE TABLE kline (
            symbol VARCHAR, market VARCHAR, interval VARCHAR, open_time TIMESTAMPTZ,
            close_time TIMESTAMPTZ, open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
            quality_status VARCHAR, available_time TIMESTAMPTZ, collected_at TIMESTAMPTZ
        )""")
        conn.execute("""CREATE TABLE funding (
            symbol VARCHAR, market VARCHAR, funding_time TIMESTAMPTZ,
            funding_rate DOUBLE, mark_price DOUBLE, quality_status VARCHAR, interval INTEGER
        )""")
        for i, low, close in [(0, 99, 100), (1, 79, 80)]:
            closed = END + timedelta(minutes=i * 5)
            conn.execute(
                "INSERT INTO kline VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    "TESTUSDT",
                    "USD-M Futures",
                    "5m",
                    closed + timedelta(milliseconds=1, minutes=-5),
                    closed,
                    100,
                    101,
                    low,
                    close,
                    "valid",
                    closed + timedelta(seconds=1),
                    END + timedelta(days=20),
                ],
            )
    return dict(
        live_db=db, lock_dir=lock, old_events=old, output_dir=tmp_path / "output"
    )


def test_real_adapter_retains_denominator_and_never_certifies_missing_funding(market):
    before = file_hash(market["live_db"])
    result = audit_locked_market(**market)
    assert file_hash(market["live_db"]) == before
    assert result["coverage"]["entry_exact_matches"] == 1
    for lane in (PARENT, SCOUT):
        row = result["summary"][lane]
        assert row["paired_price_resolved"] == 1
        assert row["new_target_rate_on_paired_price_only"] == 1
        assert row["new_mean_price_pnl_after_cost_on_paired"] == pytest.approx(0.03964)
        assert row["verified_net_ev"] is None
    assert result["evaluations"][0]["label"] is None
    assert result["provenance"]["pit_verified"] is False
    assert not result["promotion_eligible"]
    assert len(result["source_paths"]["0"]["bars"]) == 1
    assert audit_locked_market(**market)["run_id"] == result["run_id"]
    with sqlite3.connect(market["output_dir"] / "evidence.sqlite") as conn:
        assert conn.execute("SELECT count(*) FROM v3_runs").fetchone()[0] == 1


@pytest.mark.parametrize(
    "filename",
    [
        "forward48_timing_research_model.joblib",
        "forward48_timing_august_locked_signal_keys.csv",
    ],
)
def test_tampered_lock_fails_before_any_output(market, filename):
    (market["lock_dir"] / filename).write_text("tampered", "utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        audit_locked_market(**market)
    assert not market["output_dir"].exists()


def test_duplicate_entry_join_fails(market):
    with duckdb.connect(str(market["live_db"])) as conn:
        conn.execute("INSERT INTO kline SELECT * FROM kline WHERE close_time=?", [END])
    with pytest.raises(ValueError, match="exactly one"):
        audit_locked_market(**market)


def test_gap_retains_incomplete_event_and_denominator(market):
    with duckdb.connect(str(market["live_db"])) as conn:
        conn.execute(
            "UPDATE kline SET quality_status='invalid' WHERE close_time>?", [END]
        )
    result = audit_locked_market(**market)
    assert result["summary"][PARENT]["locked_entries"] == 1
    assert result["summary"][PARENT]["paired_price_resolved"] == 0
    assert result["summary"][PARENT]["new_target_rate_on_paired_price_only"] is None
    assert result["comparison"][0]["path_audit"]["invalid_price_rows"] == 1


def test_unaligned_funding_is_audited_not_rounded(market):
    when = boundary(END) + timedelta(milliseconds=3)
    with duckdb.connect(str(market["live_db"])) as conn:
        conn.execute(
            "INSERT INTO funding VALUES (?, ?, ?, ?, ?, ?, ?)",
            ["TESTUSDT", "USD-M Futures", when, 0.001, 100, "valid", None],
        )
    result = audit_locked_market(**market)
    assert result["coverage"]["unaligned_funding_rows_not_simulated"] == 1
    assert result["source_paths"]["0"]["funding"] == []
    excluded = result["source_paths"]["0"]["audit"]["unaligned_funding_not_simulated"]
    assert excluded[0]["timestamp"] == when
    assert result["summary"][PARENT]["verified_net_ev"] is None


def test_interval_and_market_do_not_cross_contaminate_entry_join(market):
    with duckdb.connect(str(market["live_db"])) as conn:
        conn.execute(
            "INSERT INTO kline SELECT symbol, 'Spot', interval, open_time, close_time, open, high, low, close, quality_status, available_time, collected_at FROM kline"
        )
    rows, _, _ = load_locked(market["lock_dir"])
    with duckdb.connect(str(market["live_db"]), read_only=True) as conn:
        _, coverage = load_paths(conn, rows)
    assert coverage["entry_exact_matches"] == 1
    assert coverage["price_rows"] == 1


def test_inclusive_close_mapping_is_exact_and_rejects_other_conventions():
    assert boundary(END) == datetime(2026, 8, 1, 0, 5, tzinfo=timezone.utc)
    with pytest.raises(ValueError):
        boundary(END + timedelta(milliseconds=1))
    with pytest.raises(ValueError):
        boundary(END - timedelta(minutes=1))


def parquet_view_with_revision(market, *, exact_tie=False):
    folder = market["live_db"].parent / "normalized" / "klines"
    folder.mkdir(parents=True)
    with duckdb.connect(str(market["live_db"])) as conn:
        conn.execute(
            """
            INSERT INTO kline SELECT symbol, market, interval, open_time, close_time,
                open, high, low, 81, quality_status, available_time,
                collected_at + CAST(? AS INTERVAL)
            FROM kline WHERE close_time>?
        """,
            ["0 seconds" if exact_tie else "1 second", END],
        )
        conn.sql("SELECT * FROM kline").write_parquet(str(folder / "revisions.parquet"))
        conn.execute("DROP TABLE kline")
        path = str(folder / "*.parquet").replace("'", "''").replace("\\", "/")
        conn.execute(f"""
            CREATE VIEW kline AS SELECT * FROM read_parquet('{path}')
            QUALIFY row_number() OVER (
                PARTITION BY symbol, close_time ORDER BY available_time DESC
            )=1
        """)


def test_parquet_revisions_select_latest_collection_deterministically(market):
    parquet_view_with_revision(market)
    first = audit_locked_market(**market)
    second = audit_locked_market(**market)
    assert first["run_id"] == second["run_id"]
    assert first["source_paths"]["0"]["bars"][0]["close"] == 81
    assert (
        first["coverage"]["kline_revision_audit"]["superseded_or_identical_rows"] == 1
    )


def test_conflicting_exact_revision_ties_fail_instead_of_selecting_randomly(market):
    parquet_view_with_revision(market, exact_tie=True)
    with pytest.raises(ValueError, match="conflicting same-rank kline"):
        audit_locked_market(**market)
    assert not market["output_dir"].exists()
