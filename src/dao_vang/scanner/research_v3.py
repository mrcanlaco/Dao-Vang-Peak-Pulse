"""Persistent observation-only v3 lane. Never submits orders or Telegram alerts."""

from __future__ import annotations

import json
import math
import os
import sqlite3
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dao_vang.experiments.distribution_v3 import (
    Episode,
    Timing,
    canonical,
    champion_gate,
    digest,
    scout_gate,
    time_value,
)
from dao_vang.experiments.distribution_v3_market import boundary, file_hash
from dao_vang.labels.engine_v3 import Bar, evaluate
from dao_vang.labels.specs.distribution_short_v3 import SPEC, TIMING
from dao_vang.scanner.watchlist import _is_stablecoin

MODEL_SHA = "1410707d5fc658278cc294d98cf9fccfbae52ffb1d3d9983b9aa7b773b437459"
RUNTIME_VERSION = "v3_shadow_runtime_v2"


def prepare_price_source(database, data_dir: Path, *, symbols: list[str] | None = None,
                         since: datetime | None = None, now: datetime | None = None) -> str:
    """Avoid the old view's nondeterministic available_time-only tie breaker."""
    view = database.execute(
        "SELECT sql FROM duckdb_views() WHERE view_name='kline'"
    ).fetchone()
    if view is None:
        return "kline"
    glob = str(data_dir.resolve() / "normalized" / "klines" / "**/*.parquet").replace(
        "'", "''"
    )
    if "normalized/klines/" not in view[0].replace("\\", "/"):
        raise ValueError("unsupported v3 price source")
    source = f"'{glob}'"
    if symbols is not None and now is not None:
        from dao_vang.scanner.research_v3_backfill import source_files

        files = sorted({path for symbol in symbols for path in source_files(
            data_dir, "klines", symbol, now, collected_since=since)})
        if not files:
            raise ValueError("v3 price sources missing")
        source = "[" + ",".join("'" + path.replace("'", "''") + "'" for path in files) + "]"
    database.execute(f"""
        CREATE OR REPLACE TEMP VIEW v3_runtime_prices AS
        SELECT DISTINCT symbol, market, interval, close_time, open, high, low, close,
            quality_status, available_time, collected_at
        FROM read_parquet({source}, union_by_name=true)
        WHERE interval='5m' AND market='USD-M Futures'
        QUALIFY dense_rank() OVER (
            PARTITION BY symbol, close_time
            ORDER BY available_time DESC NULLS LAST, collected_at DESC NULLS LAST
        )=1
    """)
    return "v3_runtime_prices"


def _dump_timing(timing: Timing) -> dict:
    episodes = {symbol: asdict(episode) for symbol, episode in timing.episodes.items()}
    for episode in episodes.values():
        if not math.isfinite(episode["peak"]):
            episode["peak"] = None
    return {"episodes": episodes, "last_entry": timing.last_entry}


def _load_timing(value: dict) -> Timing:
    timing = Timing()
    for symbol, episode in value.get("episodes", {}).items():
        episode = dict(episode)
        episode["start"] = time_value(episode["start"])
        episode["previous"] = time_value(episode["previous"])
        episode["peak"] = episode["peak"] if episode["peak"] is not None else -math.inf
        timing.episodes[symbol] = Episode(**episode)
    timing.last_entry = {
        s: time_value(t) for s, t in value.get("last_entry", {}).items()
    }
    return timing


def atomic_snapshot(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(canonical(payload), encoding="utf-8")
    os.replace(temporary, path)


def observe(database, *, storage: Path, model_path: Path, now: datetime,
            discovery: dict | None = None, settings=None) -> dict:
    """One bounded cycle: persist timing and inputs atomically; no fake backfill."""
    import joblib
    import pandas as pd

    from dao_vang.experiments.train_distribution_v2 import (
        SERVING_FEATURE_COLS,
        _predict_calibrated,
    )

    if file_hash(model_path) != MODEL_SHA:
        raise ValueError("v3 reference model checksum mismatch")
    bundle = joblib.load(model_path)
    if list(bundle["feature_columns"]) != list(SERVING_FEATURE_COLS):
        raise ValueError("v3 reference feature schema mismatch")
    storage.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(storage / "observations.sqlite") as ledger:
        ledger.executescript("""
            CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS observations (
                id TEXT PRIMARY KEY, symbol TEXT NOT NULL, timestamp TEXT NOT NULL,
                selected INTEGER NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outcomes (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
        """)
        ledger.execute("BEGIN IMMEDIATE")
        previous = ledger.execute("SELECT payload FROM state WHERE id=1").fetchone()
        state = (
            json.loads(previous[0])
            if previous
            else {
                "activated_at": now.isoformat(),
                "timing": {},
                "last_seen": {},
                "model_checksum": MODEL_SHA,
                "runtime_version": RUNTIME_VERSION,
                "contract_checksum": SPEC.checksum,
            }
        )
        # One explicit coverage migration. Historical decisions/outcomes remain
        # immutable, but broader discovery starts a fresh timing episode cohort.
        if (state.get("runtime_version") == "v3_shadow_runtime_v1"
                and state.get("model_checksum") == MODEL_SHA
                and state.get("contract_checksum") == SPEC.checksum):
            state.update(previous_activated_at=state["activated_at"], activated_at=now.isoformat(),
                         timing={}, last_seen={}, runtime_version=RUNTIME_VERSION)
        if (
            state.get("model_checksum") != MODEL_SHA
            or state.get("contract_checksum") != SPEC.checksum
            or state.get("runtime_version") != RUNTIME_VERSION
        ):
            raise ValueError(
                "v3 runtime identity changed; use a new evidence directory"
            )
        timing = _load_timing(state["timing"])
        start = max(time_value(state["activated_at"]), now - timedelta(minutes=90))
        columns = ", ".join(f"f.{column}" for column in SERVING_FEATURE_COLS)
        live_backfill = discovery is not None and discovery.get("feature_source") == "v3_live_features"
        feature_source = "v3_live_features" if live_backfill else "feature_results"
        no_live_features = live_backfill and not database.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name='v3_live_features'"
        ).fetchone()
        if no_live_features:
            # No successful warmup yet: still maintain existing outcomes/state.
            feature_source = "feature_results"
        if live_backfill:
            # Retain every unresolved entry's full path, even after a long
            # restart, while avoiding the entire market's Parquet metadata.
            open_paths = [json.loads(item) for item, outcome in ledger.execute("""
                SELECT o.payload,r.payload FROM observations o LEFT JOIN outcomes r ON o.id=r.id
                WHERE o.selected=1
            """).fetchall() if outcome is None or json.loads(outcome)["status"] == "open"]
            needed_symbols = set((discovery or {}).get("collection_symbols", [])) if not no_live_features else set()
            needed_symbols.update(item["symbol"] for item in open_paths)
            prices = prepare_price_source(
                database, storage.parent, symbols=sorted(needed_symbols), now=now,
                since=min([start, *[time_value(item["source_time"]) for item in open_paths]]) - timedelta(minutes=5),
            ) if needed_symbols else "kline"
        else:
            prices = prepare_price_source(database, storage.parent)
        frame = database.execute(
            f"""
            SELECT f.symbol, f.feature_time, {columns}, CAST(k.close AS DOUBLE) AS price
            FROM {feature_source} f JOIN {prices} k
              ON k.symbol=f.symbol AND k.close_time=f.feature_time
             AND k.interval='5m' AND k.market='USD-M Futures'
            WHERE f.feature_time>=? AND f.feature_time<?
              AND {"false" if no_live_features else "true"}
              AND EXTRACT(MINUTE FROM f.feature_time)=4
              AND f.price_ret_24h>=? AND k.quality_status='valid'
            ORDER BY f.feature_time, f.symbol
        """,
            [start, now, TIMING.min_return_24h],
        ).fetchdf()
        if frame.duplicated(["symbol", "feature_time"]).any():
            raise ValueError("ambiguous v3 feature/entry join")
        if not frame.empty:
            _, scores = _predict_calibrated(
                bundle["model"], bundle["calibrator"], frame, SERVING_FEATURE_COLS
            )
            for (_, row), score in zip(frame.iterrows(), scores, strict=True):
                symbol = str(row["symbol"])
                source_time = row["feature_time"].to_pydatetime()
                when = boundary(source_time)
                if discovery is not None:
                    first_seen = discovery.get("first_seen", {}).get(symbol)
                    if (symbol not in discovery.get("collection_symbols", [])
                            or first_seen is None or source_time < time_value(first_seen)):
                        continue
                    if live_backfill:
                        readiness = next((item for item in discovery.get("items", []) if item["symbol"] == symbol), None)
                        if readiness is not None and readiness.get("pipeline_stage") == "BACKFILLING":
                            continue
                if symbol in state["last_seen"] and when <= time_value(
                    state["last_seen"][symbol]
                ):
                    continue
                price = float(row["price"])
                if (
                    not math.isfinite(float(score))
                    or not 0 <= score <= 1
                    or not math.isfinite(price)
                    or price <= 0
                ):
                    raise ValueError("invalid v3 score or entry price")
                features = {
                    key: float(row[key])
                    if pd.notna(row[key]) and math.isfinite(float(row[key]))
                    else None
                    for key in SERVING_FEATURE_COLS
                }
                snapshot = {
                    "symbol": symbol,
                    "feature_time": when,
                    "source_time": source_time,
                    "observed_at": now,
                    "price": price,
                    "score": float(score),
                    "is_stablecoin": _is_stablecoin(symbol),
                    **features,
                }
                reason, episode = timing.decide(snapshot)
                selected = reason == "selected"
                item = {
                    **snapshot,
                    "episode_id": episode,
                    "selected": selected,
                    "reason": reason,
                    "scout": selected and scout_gate(snapshot) == "selected",
                    "scout_reason": scout_gate(snapshot),
                    "champion": selected and champion_gate(snapshot) == "selected",
                    "champion_reason": champion_gate(snapshot),
                    "model_checksum": MODEL_SHA,
                    "runtime_version": RUNTIME_VERSION,
                    "contract": SPEC.version,
                    "simulated": True,
                    "evidence_kind": "forward_observed_not_pit_certified",
                    "entry_plan": [
                        {
                            "leg": i + 1,
                            "price": price * (1 + offset),
                            "notional_weight": weight,
                        }
                        for i, (offset, weight) in enumerate(
                            zip(SPEC.offsets, SPEC.notional_weights, strict=True)
                        )
                    ],
                }
                identity = digest(
                    {
                        "symbol": symbol,
                        "time": when,
                        "model": MODEL_SHA,
                        "runtime": RUNTIME_VERSION,
                    }
                )
                ledger.execute(
                    "INSERT INTO observations VALUES (?, ?, ?, ?, ?)",
                    [identity, symbol, when.isoformat(), selected, canonical(item)],
                )
                if settings and getattr(settings, "research_v3_telegram_enabled", False) and selected:
                    try:
                        from dao_vang.alerts.telegram import TelegramNotifier
                        from dao_vang.config.settings import TelegramConfig

                        v3_bot_token = getattr(settings, "research_v3_bot_token", None) or settings.telegram.bot_token
                        v3_chat_id = (
                            getattr(settings, "research_v3_chat_id", None)
                            or getattr(settings.telegram, "shadow_chat_id", None)
                            or settings.telegram.chat_id
                        )
                        tel_cfg = TelegramConfig(
                            bot_token=v3_bot_token,
                            chat_id=v3_chat_id,
                            shadow_chat_id=v3_chat_id,
                            api_base=settings.telegram.api_base,
                            timeout_seconds=settings.telegram.timeout_seconds,
                            language=settings.telegram.language,
                        )
                        notifier = TelegramNotifier(tel_cfg, web_base_url=getattr(settings.web, "public_url", None))
                        notifier.send_v3_alert(
                            symbol=symbol,
                            entry_price=price,
                            probability=float(score),
                            pump_pct=float(snapshot.get("price_ret_24h", 0.0)),
                            distance_from_high=float(snapshot.get("distance_from_high_24h", 0.0)),
                            funding_percentile=float(snapshot.get("funding_percentile_30d", 0.0) or 0.0),
                            feature_time=when.isoformat(),
                            is_champion=bool(item.get("champion")),
                            is_scout=bool(item.get("scout")),
                            web_url=getattr(settings.web, "public_url", None),
                            operating_mode=getattr(settings.scanner, "operating_mode", "research"),
                            shadow_chat_id=v3_chat_id,
                        )
                    except Exception:
                        pass
                state["last_seen"][symbol] = when.isoformat()
        pending = ledger.execute("""
            SELECT o.id, o.payload FROM observations o WHERE o.selected=1 ORDER BY o.timestamp DESC
        """).fetchall()
        for identity, text in pending:
            item = json.loads(text)
            old = ledger.execute(
                "SELECT payload FROM outcomes WHERE id=?", [identity]
            ).fetchone()
            if old and json.loads(old[0])["status"] in {
                "target",
                "stop",
                "stop_ambiguous",
                "timeout",
                "incomplete_final",
            }:
                continue
            entry, source = (
                time_value(item["feature_time"]),
                time_value(item["source_time"]),
            )
            path = database.execute(
                f"""
                SELECT close_time, CAST(open AS DOUBLE), CAST(high AS DOUBLE), CAST(low AS DOUBLE), CAST(close AS DOUBLE)
                FROM {prices} WHERE symbol=? AND interval='5m' AND market='USD-M Futures'
                  AND quality_status='valid' AND close_time>? AND close_time<=? AND close_time<? ORDER BY close_time
            """,
                [item["symbol"], source, source + timedelta(hours=48), now],
            ).fetchall()
            result = evaluate(
                signal_time=entry,
                signal_price=item["price"],
                bars=[
                    Bar(boundary(t), op, hi, lo, close) for t, op, hi, lo, close in path
                ],
                funding=[],
                funding_coverage_through=None,
            ).to_dict()
            result["engine_status"] = result["status"]
            if result["status"] == "incomplete":
                result["status"] = (
                    "incomplete_final" if now >= entry + timedelta(hours=49) else "open"
                )
            result.update(updated_at=now, funding_verified=False, simulated=True)
            ledger.execute(
                "INSERT OR REPLACE INTO outcomes VALUES (?, ?)",
                [identity, canonical(result)],
            )
        state["timing"] = _dump_timing(timing)
        ledger.execute("INSERT OR REPLACE INTO state VALUES (1, ?)", [canonical(state)])
        recent = ledger.execute("""
            SELECT o.id, o.payload, r.payload FROM observations o LEFT JOIN outcomes r ON o.id=r.id
            ORDER BY o.selected DESC, o.timestamp DESC LIMIT 100
        """).fetchall()
        counts = ledger.execute(
            "SELECT count(*), coalesce(sum(selected),0) FROM observations"
        ).fetchone()
        payload = {
            "status": "running",
            "runtime_version": RUNTIME_VERSION,
            "previous_activated_at": state.get("previous_activated_at"),
            "updated_at": now,
            "activated_at": state["activated_at"],
            "contract": asdict(SPEC),
            "timing": asdict(TIMING),
            "model_checksum": MODEL_SHA,
            "score_kind": "reference_model_not_v3_calibrated_probability",
            "orders_enabled": False,
            "telegram_enabled": bool(settings and getattr(settings, "research_v3_telegram_enabled", False)),
            "funding_verified": False,
            "promotion_eligible": False,
            "candidate_count": counts[0],
            "entry_count": counts[1],
            "items": [
                {
                    "id": identity,
                    **json.loads(item),
                    "outcome": json.loads(outcome) if outcome else None,
                }
                for identity, item, outcome in recent
            ],
        }
    atomic_snapshot(storage / "snapshot.json", payload)
    return payload


def run_cycle(database, *, data_dir: Path, model_path: Path,
              discovery: dict | None = None, settings=None) -> None:
    """Publish failures rather than leaving an apparently healthy old snapshot."""
    now, storage = datetime.now(timezone.utc), data_dir / "research_v3"
    try:
        if discovery is not None:
            from dao_vang.scanner.research_v3_discovery import enrich

            if settings is not None and discovery.get("status") == "running":
                from dao_vang.scanner.research_v3_backfill import publish_stages, warmup

                discovery = warmup(database, settings, discovery, now=now)
                discovery = publish_stages(discovery, storage, now)
            discovery = enrich(database, discovery, now=now)
            atomic_snapshot(storage / "discovery.json", discovery)
        result = observe(database, storage=storage, model_path=model_path,
                         now=datetime.now(timezone.utc), discovery=discovery, settings=settings)
        if discovery is not None and discovery.get("backfill_version"):
            from dao_vang.scanner.research_v3_backfill import publish_stages

            publish_stages(discovery, storage, datetime.now(timezone.utc), result)
    except Exception as exc:
        atomic_snapshot(
            storage / "snapshot.json",
            {
                "status": "error",
                "updated_at": now,
                "error_type": type(exc).__name__,
                "orders_enabled": False,
                "items": [],
                "promotion_eligible": False,
            },
        )
        raise
