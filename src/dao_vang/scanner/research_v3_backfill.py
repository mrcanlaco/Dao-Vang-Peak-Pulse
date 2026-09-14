"""Bounded, restartable warmup; historical inputs never become historical decisions.

Reuses collector envelopes, normalizers and feature builders. Only the current
closed-bar feature is published, with its real materialization time. The shared
PIT timeline and the hourly Timing state machine are deliberately untouched.
Late hourly samples are allowed only after the first successful warmup.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.funding import FundingCollector
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.collectors.open_interest import OpenInterestCollector
from dao_vang.data.collectors.ratios import GlobalRatioCollector, TopRatioCollector
from dao_vang.data.collectors.taker import TakerRatioCollector
from dao_vang.data.pipeline import NORMALIZER_MAP
from dao_vang.data.quality import (
    assess_funding,
    assess_global_ratio,
    assess_kline,
    assess_open_interest,
    assess_taker_volume,
    assess_top_ratio,
)
from dao_vang.data.storage.parquet import write_normalized_to_parquet
from dao_vang.data.storage.writer import write_jsonl_atomic
from dao_vang.domain.errors import RateLimitError
from dao_vang.experiments.distribution_v3 import canonical, digest, time_value
from dao_vang.features.builder import build_features
from dao_vang.features.builders.funding import build_funding_features_sql
from dao_vang.scanner.research_v3 import atomic_snapshot

STEP = timedelta(minutes=5)
MS = timedelta(milliseconds=1)
VERSION = "discovery_backfill_v1"
# Price/OI need 288 preceding bars; ratios need 48. Funding's longest
# serving window is 30 days, calculated on a separate regular 5m grid.
SOURCES = {
    "klines": (KlinesCollector, "open_time", timedelta(hours=25)),
    "open_interest": (OpenInterestCollector, "period_start", timedelta(hours=25)),
    "taker_ratio": (TakerRatioCollector, "period_start", timedelta(hours=1)),
    "global_ratio": (GlobalRatioCollector, "period_start", timedelta(hours=5)),
    "top_ratio": (TopRatioCollector, "period_start", timedelta(hours=5)),
    "funding": (FundingCollector, "event_time", timedelta(days=31)),
}
ASSESS = {"klines": assess_kline, "funding": assess_funding,
          "open_interest": assess_open_interest, "taker_ratio": assess_taker_volume,
          "global_ratio": assess_global_ratio, "top_ratio": assess_top_ratio}


def closed_end(now: datetime) -> datetime:
    return datetime.fromtimestamp(int(now.timestamp()) // 300 * 300, timezone.utc) - MS


def transition(job: dict, stage: str, now: datetime, **details) -> None:
    if job.get("stage") != stage:
        job["transitions"] = (job.get("transitions", []) + [{"stage": stage, "at": now}])[-50:]
    job.update(stage=stage, updated_at=now, **details)


class Jobs:
    def __init__(self, storage: Path):
        storage.mkdir(parents=True, exist_ok=True)
        self.path = storage / "backfill.sqlite"
        with sqlite3.connect(self.path) as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS jobs (symbol TEXT PRIMARY KEY, payload TEXT NOT NULL)")

    def load(self, symbol: str) -> dict:
        with sqlite3.connect(self.path) as conn:
            row = conn.execute("SELECT payload FROM jobs WHERE symbol=?", [symbol]).fetchone()
        return json.loads(row[0]) if row else {"symbol": symbol, "version": VERSION, "attempts": 0}

    def save(self, job: dict) -> None:
        with sqlite3.connect(self.path) as conn:
            conn.execute("INSERT OR REPLACE INTO jobs VALUES (?,?)", [job["symbol"], canonical(job)])


class DeferredClient(BinanceClient):
    """Let the durable job own retries, including Retry-After across restarts."""

    def __init__(self, base_url: str):
        super().__init__(base_url=base_url, timeout_seconds=8, max_retries=0)
        self.error: Exception | None = None

    def get(self, endpoint, params=None):
        self.error = None
        time.sleep(0.15)
        try:
            return super().get(endpoint, params)
        except Exception as exc:
            self.error = exc
            raise


def source_files(data_dir: Path, kind: str, symbol: str, now: datetime,
                 collected_since: datetime | None = None) -> list[str]:
    """Prune scanner envelopes BEFORE DuckDB opens their Parquet footers.

    Scanner filenames encode collection time and symbol. A file collected
    before our lookback cannot contain a closed candle inside it. Partition
    dates alone are unsafe: an initial 30d download is stored on its START date.
    Unknown/import/backfill filenames remain eligible, preserving reuse.
    """
    cutoff = (collected_since or now - SOURCES[kind][2] - timedelta(days=1)).timestamp()
    result = []
    for path in (data_dir / "normalized" / kind).rglob("*.parquet"):
        parts = path.stem.split("_", 3)
        if len(parts) == 4 and parts[0] == "scan" and parts[1].isdigit() and parts[2].isdigit():
            if parts[3] != symbol or int(parts[1]) < cutoff:
                continue
        result.append(path.resolve().as_posix())
    return result


def mount_source(conn, data_dir: Path, kind: str, symbol: str, now: datetime) -> bool:
    """Current knowledge, preserving availability and collection provenance."""
    paths = source_files(data_dir, kind, symbol, now)
    if not paths:
        return False
    _, key, lookback = SOURCES[kind]
    # Values are parameters of a materialized temporary table, never identifiers.
    conn.execute(f"""
        CREATE OR REPLACE TEMP TABLE bf_{kind} AS
        SELECT DISTINCT * FROM read_parquet(?, union_by_name=true, hive_partitioning=false)
        WHERE symbol=? AND market='USD-M Futures'
          AND {key}>=? AND {key}<=? AND collected_at<=? AND available_time<=?
          AND quality_status IN ('valid', 'warning')
          {"AND interval='5m'" if kind != 'funding' else ''}
        QUALIFY dense_rank() OVER (PARTITION BY symbol,{key}
            ORDER BY available_time DESC NULLS LAST, collected_at DESC NULLS LAST)=1
    """, [paths, symbol, now - lookback - timedelta(days=1), now, now, now])
    duplicates = conn.execute(f"SELECT count(*)-count(DISTINCT {key}) FROM bf_{kind}").fetchone()[0]
    if duplicates:
        raise ValueError(f"ambiguous_{kind}")
    return True


def gaps(points: list[datetime], start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Exact missing 5m ranges, including internal holes; no latest-only shortcut."""
    present = {int(t.timestamp() * 1000) for t in points}
    missing = []
    cursor = start
    while cursor <= end:
        if int(cursor.timestamp() * 1000) in present:
            cursor += STEP
            continue
        first = cursor
        while cursor <= end and int(cursor.timestamp() * 1000) not in present and cursor - first < STEP * 499:
            cursor += STEP
        missing.append((first, cursor - MS))
    return missing


def source_gaps(conn, kind: str, exists: bool, end: datetime) -> list[tuple[datetime, datetime]]:
    _, key, lookback = SOURCES[kind]
    start = end + MS - lookback
    points = [r[0] for r in conn.execute(f"SELECT {key} FROM bf_{kind} ORDER BY {key}").fetchall()] if exists else []
    if kind == "taker_ratio":
        # The frozen serving schema uses only the contemporaneous taker ratio,
        # not the research-only taker trend windows. Require current + latest
        # hourly sample, never block on irrelevant provider holes yesterday.
        hourly = end.replace(minute=4, second=59, microsecond=999000)
        if hourly > end:
            hourly -= timedelta(hours=1)
        required = sorted({end - STEP + MS, hourly - STEP + MS} - set(points))
        ranges = []
        for stamp in required:
            if ranges and ranges[-1][1] + MS == stamp:
                ranges[-1] = (ranges[-1][0], stamp + STEP - MS)
            else:
                ranges.append((stamp, stamp + STEP - MS))
        return ranges
    if kind != "funding":
        # Exclude the currently open candle/derivative period.
        return gaps(points, start, end - STEP + MS)
    # Funding is irregular (1/4/8h). Prefix/suffix and >12h holes are fetched;
    # successful empty ranges are not treated as complete history.
    points = [t for t in points if start <= t <= end]
    if not points:
        return [(start, end)]
    result = []
    if points[0] - start > timedelta(hours=12):
        result.append((start, points[0] - MS))
    result.extend((a + MS, b - MS) for a, b in zip(points, points[1:]) if b-a > timedelta(hours=12))
    if end - points[-1] > timedelta(hours=12):
        result.append((points[-1] + MS, end))
    return result


def collect_range(settings, client, kind: str, symbol: str, start: datetime, end: datetime) -> int:
    """Atomic raw file is the checkpoint even if the process dies before SQLite."""
    identity = {"symbol": symbol, "kind": kind, "start": start, "end": end}
    request_start, request_end = start, end
    if kind == "taker_ratio":
        # Binance filters this endpoint by period END but returns period START.
        # Verified with adjacent single-period production requests: requesting
        # 08:25..08:29:59 returns timestamp 08:20; 08:30..08:34:59 returns 08:25.
        # Shift request bounds only. Never shift or fabricate response timestamps.
        request_start, request_end = start + STEP, end + STEP
        identity["request_contract"] = "taker_period_end_v1"
    run_id = "v3bf_" + digest(identity)[:24]
    partition = f"date={request_start.date().isoformat()}"
    # Failed schema/quality data must never enter the shared normalizer's inbox.
    cache = settings.paths.data_dir / "research_v3" / "backfill_cache"
    raw = cache / "raw" / kind / partition / f"{run_id}.jsonl"
    shared_raw = settings.paths.data_dir / "raw" / kind / partition / f"{run_id}.jsonl"
    normalized = settings.paths.data_dir / "normalized" / kind / partition / f"{run_id}.parquet"
    if not raw.exists():
        config = settings.model_copy(deep=True)
        config.paths.data_dir = cache
        config.binance.symbol, config.binance.interval = symbol, "5m"
        manifest = SOURCES[kind][0](client, config).collect(request_start, request_end, run_id)
        if manifest.error_count:
            raise client.error or RuntimeError(f"{kind}_collection_failed")
        if not raw.exists():
            if kind == "funding":
                return 0
            raise ValueError(f"{kind}_empty_response")
    try:
        envelopes = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines()]
        items = []
        for envelope in envelopes:
            items.extend(NORMALIZER_MAP[kind](envelope, "1.0.0"))
        if not items:
            raise ValueError(f"{kind}_empty_response")
        for item in items:
            assessed = ASSESS[kind](item)
            if assessed.quality_status in {"invalid", "quarantined"}:
                raise ValueError(f"{kind}_invalid_payload")
    except Exception:
        # Keep evidence outside the scanner inbox and let the next retry fetch
        # a corrected response instead of getting stuck on a poisoned cache.
        raw.replace(raw.with_suffix(f".{time.time_ns()}.invalid"))
        raise
    if not normalized.exists():
        write_normalized_to_parquet(normalized, items)
    if not shared_raw.exists():
        write_jsonl_atomic(shared_raw, envelopes)
    return len(items)


def materialize(conn, *, symbol: str, end: datetime, now: datetime, first_seen: datetime) -> dict:
    """Reuse builders on regular current-as-of inputs, publish one closed bar.

    No derived history is inserted into feature_results or the observations
    ledger. Missing derivatives remain visible as a quality failure instead of
    silently relying on the builders' fallback zeros/ratios.
    """
    start = end - timedelta(hours=24)
    conn.execute("""
        CREATE OR REPLACE TEMP TABLE bf_prices AS
        SELECT * FROM bf_klines WHERE close_time BETWEEN ? AND ?
          AND close>0 AND open>0 AND low>0 AND high>=greatest(open,close,low)
          AND low<=least(open,close,high) AND volume_base>=0 AND volume_quote>=0 AND trade_count>=0
    """, [start, end])
    count = conn.execute("SELECT count(*), min(close_time), max(close_time) FROM bf_prices").fetchone()
    if count != (289, start, end):
        raise ValueError(f"history_24h_incomplete:{count[0]}/289")
    # Join period_start + 5m - 1ms to the corresponding closed candle.
    # Collection time was checked at mount; no historical availability is invented.
    conn.execute("""
        CREATE OR REPLACE TEMP TABLE bf_timeline AS
        SELECT k.symbol,k.close_time AS feature_time,k.open,k.high,k.low,k.close,k.volume_base,
          oi.open_interest_value, tv.buy_volume,tv.sell_volume,tv.buy_sell_ratio,
          gr.long_short_ratio AS global_long_short_ratio,
          tr.long_short_ratio AS top_long_short_ratio,
          NULL::DOUBLE AS top_long_short_position_ratio, NULL::DOUBLE AS funding_rate_last_known
        FROM bf_prices k
        LEFT JOIN bf_open_interest oi ON oi.period_start=k.open_time
        LEFT JOIN bf_taker_ratio tv ON tv.period_start=k.open_time
        LEFT JOIN bf_global_ratio gr ON gr.period_start=k.open_time
        LEFT JOIN bf_top_ratio tr ON tr.period_start=k.open_time
    """)
    missing = conn.execute("""
        SELECT count(*) FILTER (WHERE open_interest_value IS NULL OR open_interest_value<=0),
          count(*) FILTER (WHERE feature_time=? AND (buy_volume IS NULL OR sell_volume IS NULL OR buy_volume<0 OR sell_volume<0)),
          count(*) FILTER (WHERE feature_time>? AND
            (global_long_short_ratio IS NULL OR top_long_short_ratio IS NULL
             OR global_long_short_ratio<=0 OR top_long_short_ratio<=0))
        FROM bf_timeline
    """, [end, end - timedelta(hours=4)]).fetchone()
    if any(missing):
        raise ValueError(f"derivative_history_incomplete:oi={missing[0]},taker={missing[1]},ratios={missing[2]}")
    # A regular funding-only grid supplies the full 30d windows without
    # downloading 30d of redundant price/OI candles.
    conn.execute("""
        CREATE OR REPLACE TEMP TABLE bf_funding_grid AS
        SELECT ? AS symbol,g.feature_time,
          CASE WHEN g.feature_time-f.event_time<=INTERVAL '12 hours'
               THEN f.funding_rate ELSE NULL END AS funding_rate_last_known
        FROM generate_series(?, ?, INTERVAL '5 minutes') g(feature_time)
        ASOF LEFT JOIN bf_funding f ON g.feature_time>=f.event_time
    """, [symbol, end - timedelta(days=30) + STEP, end])
    funding_rows, latest_funding = conn.execute("""
        SELECT count(funding_rate_last_known),last(funding_rate_last_known ORDER BY feature_time)
        FROM bf_funding_grid
    """).fetchone()
    if latest_funding is None:
        raise ValueError("funding_stale_or_missing")
    build_features(conn, "bf_timeline", "bf_features")
    funding_sql = build_funding_features_sql("bf_funding_grid")
    conn.execute(f"CREATE OR REPLACE TEMP TABLE bf_funding_features AS WITH {funding_sql} SELECT * FROM funding_features")
    if funding_rows < 8640:
        # Short listing history cannot masquerade as a 30d percentile. Preserve
        # the serving model's missing-value policy; Scout fails its normal gate.
        conn.execute("UPDATE bf_funding_features SET funding_percentile_30d=NULL, funding_zscore_30d=NULL")
    if funding_rows < 2016:
        conn.execute("UPDATE bf_funding_features SET funding_percentile_7d=NULL, funding_persistence_7d=NULL")
    funding_cols = [row[0] for row in conn.execute("DESCRIBE bf_funding_features").fetchall() if row[0] not in {"symbol", "feature_time"}]
    replacements = ",".join(f"u.{name} AS {name}" for name in funding_cols)
    conn.execute(f"""
        CREATE OR REPLACE TEMP TABLE bf_current AS
        SELECT f.* REPLACE ({replacements}), ?::TIMESTAMPTZ AS materialized_at,
          ?::TIMESTAMPTZ AS discovery_first_seen
        FROM bf_features f JOIN bf_funding_features u USING(symbol,feature_time)
        WHERE f.feature_time=?
    """, [now, first_seen, end])
    conn.execute("CREATE TABLE IF NOT EXISTS v3_live_features AS SELECT * FROM bf_current WHERE false")
    # First successful materialization wins; restarting/retrying cannot rewrite
    # the feature values already consumed by an hourly observation.
    conn.execute("""INSERT INTO v3_live_features
        SELECT c.* FROM bf_current c WHERE NOT EXISTS
        (SELECT 1 FROM v3_live_features f WHERE f.symbol=c.symbol AND f.feature_time=c.feature_time)
    """)
    return {"price_bars": count[0], "required_price_bars": 289,
            "funding_grid_bars": funding_rows, "required_funding_grid_bars": 8640,
            "warning": "funding_history_short" if funding_rows < 8640 else None,
            "checked_at": now, "feature_time": end}


def attach(discovery: dict, jobs: Jobs) -> dict:
    items = []
    for item in discovery.get("items", []):
        job = jobs.load(item["symbol"])
        if job.get("detected_at") and time_value(job["detected_at"]) != time_value(item["first_seen"]):
            job = {"symbol": item["symbol"], "version": VERSION, "stage": "DETECTED"}
        items.append({**item, "pipeline_stage": job.get("stage", "DETECTED"), "backfill": job})
    return {**discovery, "backfill_version": VERSION, "feature_source": "v3_live_features",
            "items": items}


def warmup(conn, settings, discovery: dict, *, now: datetime, max_requests: int = 24,
           budget_seconds: float = 45, client=None) -> dict:
    storage = settings.paths.data_dir / "research_v3"
    jobs = Jobs(storage)
    client = client or DeferredClient(str(settings.binance.base_url))
    end = closed_end(time_value(discovery["updated_at"]))
    started, requests = time.monotonic(), 0
    cooldown = jobs.load("__rate_limit__").get("next_retry_at")
    symbols = list(discovery.get("first_seen", {}))
    symbols = [s for s in symbols if s in discovery.get("collection_symbols", [])]
    # Least recently attempted first prevents a problematic symbol starving peers.
    symbols.sort(key=lambda s: (bool(jobs.load(s).get("ready_at")), jobs.load(s).get("updated_at", "")))
    for symbol in symbols:
        job = jobs.load(symbol)
        if job.get("detected_at") and time_value(job["detected_at"]) != time_value(discovery["first_seen"][symbol]):
            job = {"symbol": symbol, "version": VERSION, "attempts": job["attempts"]}
        if "stage" not in job:
            transition(job, "DETECTED", now, detected_at=discovery["first_seen"][symbol])
            jobs.save(job)
        retry = job.get("next_retry_at")
        if retry and time_value(retry) > now:
            continue
        transition(job, "BACKFILLING", now, error=None, next_retry_at=None)
        jobs.save(job)
        atomic_snapshot(storage / "discovery.json", attach(discovery, jobs))
        try:
            for kind in SOURCES:
                exists = mount_source(conn, settings.paths.data_dir, kind, symbol, now)
                downloaded = False
                for start, stop in source_gaps(conn, kind, exists, end):
                    if (kind == "funding" and job.get("funding_checked_from")
                            and start >= time_value(job["funding_checked_from"])
                            and stop <= time_value(job["funding_checked_through"])):
                        continue
                    if (requests >= max_requests or time.monotonic()-started >= budget_seconds
                            or (cooldown and time_value(cooldown) > now)):
                        raise InterruptedError("cycle_budget_or_rate_limit")
                    requests += 1
                    job["attempts"] += 1
                    job["source"] = kind
                    jobs.save(job)
                    collect_range(settings, client, kind, symbol, start, stop)
                    downloaded = True
                if kind == "funding":
                    job.update(funding_checked_from=end+MS-SOURCES[kind][2], funding_checked_through=end)
                    jobs.save(job)
                # New envelopes have collection timestamps later than cycle start.
                asof = max(now, datetime.now(timezone.utc))
                if (downloaded or not exists) and not mount_source(conn, settings.paths.data_dir, kind, symbol, asof):
                    raise ValueError(f"{kind}_missing")
            quality = materialize(conn, symbol=symbol, end=end, now=max(now, datetime.now(timezone.utc)),
                                  first_seen=time_value(discovery["first_seen"][symbol]))
            # Preserve the existing hourly sampling when a live scan runs late.
            # Only a source close AFTER warmup completed can be caught up; never
            # manufacture confirmations from the history that warmed this coin.
            hourly = end.replace(minute=4, second=59, microsecond=999000)
            if hourly > end:
                hourly -= timedelta(hours=1)
            if job.get("ready_at") and time_value(job["ready_at"]) <= hourly < end:
                try:
                    materialize(conn, symbol=symbol, end=hourly,
                                now=max(now, datetime.now(timezone.utc)),
                                first_seen=time_value(discovery["first_seen"][symbol]))
                    job["hourly_feature_time"] = hourly
                    job["hourly_quality_error"] = None
                except ValueError as exc:
                    # Current data can be ready while an earlier closed window
                    # still has a hole. Do not score that incomplete hour.
                    job["hourly_quality_error"] = str(exc)[:240]
            transition(job, "DATA_READY", now, quality=quality, error=None,
                       ready_at=job.get("ready_at") or quality["checked_at"], feature_time=end,
                       failures=0, deferred_reason=None)
        except InterruptedError:
            job["deferred_reason"] = "cycle_budget_or_rate_limit"
        except Exception as exc:
            delay = min(3600, 60 * 2 ** min(job.get("failures", 0), 6))
            if isinstance(exc, RateLimitError):
                delay = max(delay, exc.retry_after_seconds)
                cooldown = (now + timedelta(seconds=delay)).isoformat()
                jobs.save({"symbol": "__rate_limit__", "next_retry_at": cooldown})
            transition(job, "BACKFILLING", now, error=str(exc)[:240],
                       failures=job.get("failures", 0)+1, next_retry_at=now+timedelta(seconds=delay))
        job["updated_at"] = max(now, datetime.now(timezone.utc))
        jobs.save(job)
    result = attach(discovery, jobs)
    atomic_snapshot(storage / "discovery.json", result)
    return result


def publish_stages(discovery: dict, storage: Path, now: datetime, observations: dict | None = None) -> dict:
    jobs = Jobs(storage)
    latest = {}
    for item in (observations or {}).get("items", []):
        symbol = item["symbol"]
        if symbol not in latest or item["feature_time"] > latest[symbol]["feature_time"]:
            latest[symbol] = item
    for item in discovery.get("items", []):
        job = jobs.load(item["symbol"])
        if job.get("stage") not in {"DATA_READY", "SCORING", "CONFIRMATION", "ENTRY", "REJECT"}:
            continue
        stage = "SCORING"
        observation = latest.get(item["symbol"])
        details = {}
        if observation and time_value(observation["source_time"]) >= time_value(job["detected_at"]):
            stage = "ENTRY" if observation["selected"] else "CONFIRMATION"
            if observation["reason"] in {"score_below_reference_threshold", "symbol_cooldown", "stablecoin"}:
                stage = "REJECT"
            details = {"last_score": observation["score"], "decision_reason": observation["reason"],
                       "last_observation_at": observation["feature_time"]}
        transition(job, stage, now, **details)
        jobs.save(job)
    result = attach(discovery, jobs)
    atomic_snapshot(storage / "discovery.json", result)
    return result
