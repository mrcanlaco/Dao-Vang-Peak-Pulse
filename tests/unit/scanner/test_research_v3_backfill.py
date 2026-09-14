"""Real collectors -> raw -> parquet -> features -> hourly observer integration."""

import json
from datetime import timedelta

import duckdb
import pytest

from dao_vang.config.settings import AppSettings
from dao_vang.domain.errors import RateLimitError
from dao_vang.scanner import research_v3
from dao_vang.scanner import research_v3_backfill as bf
from dao_vang.scanner.research_v3_discovery import discover
from tests.unit.scanner.test_research_v3 import START, setup  # noqa: F401
from tests.unit.scanner.test_research_v3_discovery import ticker


class Market:
    def __init__(self):
        self.calls = []
        self.error = None
        self.fail_symbol = None
        self.rate_limit = False
        self.hole = None

    def get(self, endpoint, params):
        self.calls.append((endpoint, dict(params)))
        if params["symbol"] == self.fail_symbol:
            self.error = RateLimitError("429", 600) if self.rate_limit else ValueError("source_unavailable")
            raise self.error
        step = 8*3600*1000 if "fundingRate" in endpoint else 300000
        first = ((params["startTime"]+step-1)//step)*step
        result = []
        for ts in range(first, params["endTime"]+1, step):
            if ts == self.hole:
                continue
            symbol = params["symbol"]
            if "klines" in endpoint:
                p = 100 * 1.35 ** ((ts/1000-START.timestamp())/86400)
                result.append([ts, str(p), str(p*1.01), str(p*.99), str(p), "100", ts+299999, "10000", 50, "45", "4500", "0"])
            elif "fundingRate" in endpoint:
                result.append({"symbol": symbol, "fundingTime": ts, "fundingRate": str(.001+(ts//step % 5)*.0001), "markPrice": "100"})
            elif "openInterestHist" in endpoint:
                result.append({"symbol": symbol, "timestamp": ts, "sumOpenInterest": "100", "sumOpenInterestValue": "10000"})
            elif "taker" in endpoint:
                result.append({"timestamp": ts, "buyVol": "45", "sellVol": "55", "buySellRatio": str(45/55)})
            else:
                result.append({"symbol": symbol, "timestamp": ts, "longAccount": "0.6", "shortAccount": "0.4", "longShortRatio": "1.5"})
        return result[:params["limit"]]


@pytest.fixture
def market_env(tmp_path, monkeypatch):
    settings = AppSettings()
    settings.paths.data_dir = tmp_path
    # Collection receipt times are genuine fixture times, after historical bars.
    for name in ("klines", "funding", "open_interest", "taker", "ratios"):
        monkeypatch.setattr(f"dao_vang.data.collectors.{name}.system_now", lambda: START+timedelta(minutes=6))
    return settings, Market()


def discovery(settings, now=START+timedelta(minutes=10, seconds=5), symbols=("TESTUSDT",)):
    return discover([ticker(s, now=now) for s in symbols], storage=settings.paths.data_dir / "research_v3", now=now)


def run(conn, env, data, now=None, **kwargs):
    settings, client = env
    return bf.warmup(conn, settings, data, now=now or START+timedelta(minutes=10, seconds=5), client=client, **kwargs)


def test_new_coin_backfills_and_materializes_only_current_closed_bar(market_env):
    settings, client = market_env
    with duckdb.connect() as conn:
        data = run(conn, market_env, discovery(settings))
        job = data["items"][0]["backfill"]
        assert job["stage"] == "DATA_READY", job
        assert job["quality"]["price_bars"] == 289
        assert job["quality"]["funding_grid_bars"] == 8640
        assert conn.execute("SELECT count(*) FROM v3_live_features").fetchone()[0] == 1
        assert conn.execute("SELECT price_ret_24h FROM v3_live_features").fetchone()[0] == pytest.approx(.35)
        assert len(client.calls) == 6
        assert [t["stage"] for t in job["transitions"]] == ["DETECTED", "BACKFILLING", "DATA_READY"]
        before = list(client.calls)
        repeated = run(conn, market_env, data)
        assert repeated["items"][0]["backfill"]["stage"] == "DATA_READY", repeated["items"][0]["backfill"].get("error")
        assert client.calls == before
        assert conn.execute("SELECT count(*) FROM v3_live_features").fetchone()[0] == 1


def test_partial_restart_resumes_without_duplicate_downloads(market_env):
    settings, client = market_env
    db_path = str(settings.paths.data_dir / "test.duckdb")
    data = discovery(settings)
    with duckdb.connect(db_path) as conn:
        result = run(conn, market_env, data, max_requests=2)
        assert result["items"][0]["pipeline_stage"] == "BACKFILLING"
        assert len(client.calls) == 2
    # New database connection and Jobs object, same disk checkpoints.
    with duckdb.connect(db_path) as conn:
        result = run(conn, market_env, data)
        assert result["items"][0]["pipeline_stage"] == "DATA_READY", result["items"][0]["backfill"].get("error")
    assert len(client.calls) == 6


def test_error_isolated_and_retry_persisted(market_env):
    settings, client = market_env
    client.fail_symbol = "BADUSDT"
    data = discovery(settings, symbols=("BADUSDT", "GOODUSDT"))
    with duckdb.connect() as conn:
        result = run(conn, market_env, data)
        by_symbol = {i["symbol"]: i for i in result["items"]}
        assert by_symbol["BADUSDT"]["backfill"]["error"] == "source_unavailable"
        assert by_symbol["GOODUSDT"]["pipeline_stage"] == "DATA_READY"
        attempts = len(client.calls)
        run(conn, market_env, data, now=START+timedelta(minutes=10, seconds=30))
        assert len(client.calls) == attempts
        client.fail_symbol = None
        result = run(conn, market_env, data, now=START+timedelta(minutes=12))
        assert all(i["pipeline_stage"] == "DATA_READY" for i in result["items"])


def test_rate_limit_cooldown_applies_to_peers_and_restart(market_env):
    settings, client = market_env
    client.fail_symbol, client.rate_limit = "BADUSDT", True
    data = discovery(settings, symbols=("BADUSDT", "GOODUSDT"))
    with duckdb.connect() as conn:
        run(conn, market_env, data)
    assert len(client.calls) == 1
    with duckdb.connect() as conn:
        result = run(conn, market_env, data, now=START+timedelta(minutes=15))
    assert len(client.calls) == 1
    assert all(i["pipeline_stage"] == "BACKFILLING" for i in result["items"])
    assert bf.time_value(bf.Jobs(settings.paths.data_dir / "research_v3").load("__rate_limit__")["next_retry_at"]) == START+timedelta(minutes=20, seconds=5)


def test_internal_hole_is_not_misreported_as_24h_return(market_env):
    settings, client = market_env
    client.hole = int((START-timedelta(hours=3)).timestamp()*1000)
    data = discovery(settings)
    with duckdb.connect() as conn:
        result = run(conn, market_env, data)
        assert result["items"][0]["pipeline_stage"] == "BACKFILLING"
        assert "history_24h_incomplete" in result["items"][0]["backfill"]["error"]
        assert not conn.execute("SELECT 1 FROM information_schema.tables WHERE table_name='v3_live_features'").fetchone()
        client.hole = None
        result = run(conn, market_env, data, now=START+timedelta(minutes=12))
        assert result["items"][0]["pipeline_stage"] == "DATA_READY", result["items"][0]["backfill"].get("error")
        # Six initial source requests + five single-bar repairs (funding unaffected).
        assert len(client.calls) == 11


def test_late_collected_history_is_usable_now_but_cannot_replay_confirmations(market_env, setup):  # noqa: F811
    conn, args = setup
    settings, _ = market_env
    research_v3.observe(conn, **args, now=START)
    legacy = conn.execute("SELECT * FROM feature_results").fetchall()
    # Discovery before the first source close. Warmup publishes that close only.
    data = discovery(settings, now=START+timedelta(minutes=1))
    for hour in range(5):
        now = START+timedelta(hours=hour, minutes=6)
        data = discovery(settings, now=now)
        data = run(conn, market_env, data, now=now)
        assert data["items"][0]["pipeline_stage"] == "DATA_READY", data
        result = research_v3.observe(conn, **args, now=now, discovery=data)
        assert result["candidate_count"] == hour+1
        assert result["entry_count"] == int(hour == 4)
        repeat = research_v3.observe(conn, **args, now=now+timedelta(minutes=2), discovery=data)
        assert repeat["candidate_count"] == hour+1
    assert conn.execute("SELECT * FROM feature_results").fetchall() == legacy
    stages = bf.publish_stages(data, args["storage"], now, result)
    assert stages["items"][0]["pipeline_stage"] == "ENTRY"
    assert json.loads((args["storage"] / "discovery.json").read_text())["items"][0]["backfill"]["last_score"] == .5


def test_range_planner_keeps_existing_bars_and_repairs_prefix_and_holes():
    times = [START+bf.STEP*i for i in range(5)]
    assert bf.gaps(times[2:3]+times[4:], times[0], times[-1]) == [
        (times[0], times[2]-bf.MS), (times[3], times[4]-bf.MS)]


def test_raw_checkpoint_survives_crash_before_normalization(market_env, monkeypatch):
    settings, client = market_env
    write = bf.write_normalized_to_parquet
    monkeypatch.setattr(bf, "write_normalized_to_parquet", lambda *args: (_ for _ in ()).throw(OSError("disk_busy")))
    with duckdb.connect() as conn:
        data = discovery(settings)
        result = run(conn, market_env, data)
        assert result["items"][0]["backfill"]["error"] == "disk_busy"
        assert len(client.calls) == 1
        monkeypatch.setattr(bf, "write_normalized_to_parquet", write)
        result = run(conn, market_env, data, now=START+timedelta(minutes=12))
        assert result["items"][0]["pipeline_stage"] == "DATA_READY"
        assert len(client.calls) == 6


def test_invalid_payload_cannot_poison_shared_scanner_inbox(market_env, monkeypatch):
    settings, client = market_env
    get = client.get

    def malformed(endpoint, params):
        rows = get(endpoint, params)
        if "klines" in endpoint:
            rows[0][2] = "0"
        return rows

    monkeypatch.setattr(client, "get", malformed)
    with duckdb.connect() as conn:
        result = run(conn, market_env, discovery(settings))
    assert result["items"][0]["backfill"]["error"] == "klines_invalid_payload"
    assert not list((settings.paths.data_dir / "raw").rglob("*.jsonl"))
    assert list((settings.paths.data_dir / "research_v3/backfill_cache").rglob("*.invalid"))


def test_delayed_warmup_does_not_recreate_missed_hourly_snapshots(market_env, setup):  # noqa: F811
    conn, args = setup
    settings, _ = market_env
    research_v3.observe(conn, **args, now=START)
    discovery(settings, now=START+timedelta(minutes=1))
    now = START+timedelta(hours=1, minutes=31)
    data = run(conn, market_env, discovery(settings, now=now), now=now)
    assert data["items"][0]["pipeline_stage"] == "DATA_READY"
    result = research_v3.observe(conn, **args, now=now, discovery=data)
    assert result["candidate_count"] == 0
    now = START+timedelta(hours=2, minutes=6)
    data = run(conn, market_env, discovery(settings, now=now), now=now)
    result = research_v3.observe(conn, **args, now=now, discovery=data)
    assert result["candidate_count"] == 1
    assert result["entry_count"] == 0


def test_short_funding_history_is_explicit_and_scout_cannot_use_30d_percentile(market_env, monkeypatch):
    settings, client = market_env
    get = client.get

    def recent_funding(endpoint, params):
        rows = get(endpoint, params)
        if "fundingRate" in endpoint:
            rows = [r for r in rows if r["fundingTime"] > (START-timedelta(days=3)).timestamp()*1000]
        return rows

    monkeypatch.setattr(client, "get", recent_funding)
    with duckdb.connect() as conn:
        data = discovery(settings)
        result = run(conn, market_env, data)
        assert result["items"][0]["backfill"]["quality"]["warning"] == "funding_history_short"
        assert conn.execute("SELECT funding_percentile_30d, funding_persistence_7d FROM v3_live_features").fetchone() == (None, None)
        calls = len(client.calls)
        run(conn, market_env, data)
        assert len(client.calls) == calls


def test_file_pruning_uses_collection_time_not_partition_start(tmp_path):
    directory = tmp_path / "normalized/funding/date=2026-07-26"
    directory.mkdir(parents=True)
    recent = int((START-timedelta(days=20)).timestamp())
    old = int((START-timedelta(days=60)).timestamp())
    names = [f"scan_{recent}_1_TESTUSDT.parquet", f"scan_{recent}_1_OTHERUSDT.parquet",
             f"scan_{old}_1_TESTUSDT.parquet", "import_unknown.parquet", "v3bf_checkpoint.parquet"]
    for name in names:
        (directory / name).touch()
    selected = bf.source_files(tmp_path, "funding", "TESTUSDT", START)
    assert {bf.Path(p).name for p in selected} == {names[0], names[3], names[4]}


def test_other_symbol_files_are_not_opened_by_parquet_reader(market_env):
    settings, _ = market_env
    directory = settings.paths.data_dir / "normalized/klines/date=2026-09-14"
    directory.mkdir(parents=True)
    # If the reader glob opens unrelated symbols this deliberately invalid
    # Parquet footer fails the entire coin, as the original broad scan did.
    (directory / f"scan_{int(START.timestamp())}_1_OTHERUSDT.parquet").write_text("unrelated")
    with duckdb.connect() as conn:
        result = run(conn, market_env, discovery(settings))
        assert result["items"][0]["pipeline_stage"] == "DATA_READY"


