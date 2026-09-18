"""Persistent observation-only v3 lane; optional durable research notifications, no orders."""

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
from dao_vang.labels.dual_outcomes_v3 import evaluate_dual
from dao_vang.labels.engine_v3 import Bar
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
        from dao_vang.scanner.research_v3_sources import SourceCatalog

        catalog = SourceCatalog(data_dir)
        files = sorted({path for symbol in symbols for path in source_files(
            data_dir, "klines", symbol, now, collected_since=since, catalog=catalog)})
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


def _outcome_is_terminal(payload: dict, *, now: datetime, entry_time: datetime) -> bool:
    """Keep stopped rows open until their independent post-stop path resolves."""

    status = payload.get("status")
    if status in {"target", "timeout"}:
        return True
    if status == "incomplete_final":
        return now >= entry_time + timedelta(hours=49)
    if status in {"stop", "stop_ambiguous"}:
        post_stop = payload.get("post_stop") or {}
        # Old rows have no post_stop object and must be replayed once under the
        # dual contract.  A successful post-stop target or original-horizon
        # timeout is terminal; gaps/incomplete paths are retried for backfill.
        return post_stop.get("status") in {
            "target_after_stop",
            "timeout_after_stop",
        }
    return False


def observe(database, *, storage: Path, model_path: Path, now: datetime,
            discovery: dict | None = None, settings=None,
            pattern_artifact: Path | None = None) -> dict:
    """One bounded cycle: persist timing and inputs atomically; no fake backfill."""
    import joblib
    import pandas as pd

    from dao_vang.experiments.train_distribution_v2 import (
        SERVING_FEATURE_COLS,
        _predict_calibrated,
    )

    pattern_model = None
    pattern_error: str | None = None
    selected_pattern_artifact = pattern_artifact or getattr(
        settings, "research_v3_pattern_artifact", None
    )
    if selected_pattern_artifact:
        try:
            from dao_vang.experiments.pattern_research_v3 import load_pattern_model

            selected_pattern_artifact = Path(selected_pattern_artifact)
            if selected_pattern_artifact.exists():
                pattern_model = load_pattern_model(selected_pattern_artifact)
            else:
                pattern_error = "pattern_artifact_missing"
        except Exception as exc:
            # Pattern metadata is advisory.  An invalid artifact must not
            # suppress the frozen champion lane or make the cycle fail.
            pattern_error = f"pattern_artifact_invalid:{type(exc).__name__}"

    dispatcher = None
    if settings and getattr(settings, "research_v3_telegram_enabled", False):
        try:
            from dao_vang.alerts.notification_dispatcher import NotificationDispatcher
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
            notifier = TelegramNotifier(
                tel_cfg,
                web_base_url=getattr(settings.web, "public_url", None),
            )
            dispatcher = NotificationDispatcher(
                notifier,
                storage_path=storage / "telegram_notifications.sqlite",
                enabled=True,
                operating_mode=getattr(settings.scanner, "operating_mode", "research"),
                shadow_chat_id=v3_chat_id,
            )
            # Recover failed sends after a restart before adding lifecycle
            # replies.  Outbox keys keep this idempotent.
            dispatcher.retry_pending()
        except Exception as exc:
            # A notification transport failure must not stop research
            # observation or hide the candidate from the snapshot.
            pattern_error = pattern_error or f"notification_dispatcher_unavailable:{type(exc).__name__}"

    # Stage notification payloads while observations/outcomes are inside the
    # SQLite transaction.  They are dispatched only after the transaction
    # commits, so a Telegram message can never refer to a rolled-back row.
    notification_events: list[dict] = []

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
                if pattern_model is not None:
                    from dao_vang.experiments.pattern_research_v3 import (
                        classify_snapshot,
                    )

                    pattern = classify_snapshot(snapshot, pattern_model)
                else:
                    pattern = {
                        "pattern_id": "unknown",
                        "pattern_type": "unknown",
                        "stage": "unknown",
                        "status": "unknown",
                        "nearest_pattern": None,
                        "distance": None,
                        "radius": None,
                        "discrepancies": [],
                        "missing_features": list(SERVING_FEATURE_COLS),
                        "unknown_reason": pattern_error or "pattern_artifact_unavailable",
                        "quality_status": "unconfirmed",
                        "model_version": None,
                    }
                reason, episode = timing.decide(snapshot)
                selected = reason == "selected"
                pump_val = float(snapshot.get("price_ret_24h", 0.0) or 0.0)
                dist_val = float(snapshot.get("distance_from_high_24h", 0.0) or 0.0)
                fund_pct = float(snapshot.get("funding_percentile_30d", 0.0) or 0.0)
                fund_chg = float(snapshot.get("funding_change_8h", 0.0) or 0.0)
                fund_persistence_raw = snapshot.get("funding_persistence_7d")
                fund_persistence = (
                    float(fund_persistence_raw)
                    if fund_persistence_raw is not None and math.isfinite(float(fund_persistence_raw))
                    else None
                )
                score_val = float(score)
                c_pump = pump_val >= 0.25
                c_rev = dist_val <= -0.02
                c_fund = fund_pct >= 0.80
                c_chg = fund_chg > 0.0
                c_score = score_val >= TIMING.score_threshold
                met_count = sum([c_pump, c_rev, c_fund, c_chg, c_score])
                progress_dict = {
                    "score": round((met_count / 5.0) * 100),
                    "met_count": met_count,
                    "total_count": 5,
                    "criteria": {
                        "pump": {"current": pump_val, "target": 0.25, "passed": c_pump},
                        "reversal": {"current": dist_val, "target": -0.02, "passed": c_rev},
                        "funding": {"current": fund_pct, "target": 0.80, "passed": c_fund},
                        "funding_persistence": {
                            "current": fund_persistence,
                            "target": 0.0,
                            "passed": fund_persistence is not None and fund_persistence > 0.0,
                        },
                        "funding_change": {"current": fund_chg, "target": 0.0, "passed": c_chg},
                        "score": {"current": score_val, "target": TIMING.score_threshold, "passed": c_score},
                    },
                }
                item = {
                    **snapshot,
                    "episode_id": episode,
                    "selected": selected,
                    "reason": reason,
                    "scout": selected and scout_gate(snapshot) == "selected",
                    "scout_reason": scout_gate(snapshot),
                    "champion": selected and champion_gate(snapshot) == "selected",
                    "champion_reason": champion_gate(snapshot),
                    "progress": progress_dict,
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
                    # Keep a compact top-level schema for API/UI clients while
                    # preserving the complete nested explanation object.
                    "pattern": pattern,
                    "pattern_id": pattern["pattern_id"],
                    "pattern_type": pattern["pattern_type"],
                    "pattern_stage": pattern["stage"],
                    "pattern_status": pattern["status"],
                    "nearest_pattern": pattern.get("nearest_pattern"),
                    "pattern_distance": pattern.get("distance"),
                    "pattern_discrepancies": pattern.get("discrepancies", []),
                    "pattern_quality": pattern.get("quality_status", "unconfirmed"),
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
                if dispatcher is not None and item["champion"]:
                    notification_events.append(
                        {
                            **item,
                            "event_type": "signal",
                            "id": identity,
                            "signal_id": identity,
                            "event_key": f"{identity}:signal",
                            "entry_price": price,
                            "conditions": progress_dict["criteria"],
                            "selection_attestation": {
                                "eligible": True,
                                "policy_version": TIMING.version,
                                "source_id": identity,
                            },
                            "quality_validated": item.get("pattern_quality") == "high_quality",
                            "operating_mode": getattr(settings.scanner, "operating_mode", "research"),
                            "shadow_chat_id": getattr(settings, "research_v3_chat_id", None)
                            or getattr(settings.telegram, "shadow_chat_id", None),
                            "web_url": getattr(settings.web, "public_url", None),
                        }
                    )
                # Telegram dispatch is owned by the durable notification
                # dispatcher.  The old inline send was removed to prevent a
                # duplicate after scanner restarts; this observation remains
                # the source record consumed by that dispatcher.
                state["last_seen"][symbol] = when.isoformat()
        pending = ledger.execute("""
            SELECT o.id, o.payload FROM observations o WHERE o.selected=1 ORDER BY o.timestamp DESC
        """).fetchall()
        for identity, text in pending:
            item = json.loads(text)
            old = ledger.execute(
                "SELECT payload FROM outcomes WHERE id=?", [identity]
            ).fetchone()
            if old and _outcome_is_terminal(
                json.loads(old[0]),
                now=now,
                entry_time=time_value(item["feature_time"]),
            ):
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
            result = evaluate_dual(
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
            if dispatcher is not None and item.get("champion"):
                fills = result.get("fills") or []
                last_fill = fills[-1] if fills else {}
                post_stop = result.get("post_stop") or {}
                actual_status = result.get("engine_status", result.get("status"))
                base_event = {
                    "id": identity,
                    "signal_id": identity,
                    "symbol": item["symbol"],
                    "feature_time": item["feature_time"],
                    "event_time": result.get("exit_time") or now,
                    "average_entry": last_fill.get("average_entry"),
                    "filled_legs": len(fills),
                    "actual_fill": actual_status in {"target", "stop", "stop_ambiguous", "timeout"},
                    "eligible": result.get("eligible"),
                    "exclusion_reason": result.get("exclusion_reason"),
                    "funding_verified": bool(result.get("funding_verified", False)),
                    "contract": result.get("contract"),
                    "contract_checksum": result.get("contract_checksum"),
                    "outcome_contract": result.get("outcome_contract"),
                    "operating_mode": getattr(settings.scanner, "operating_mode", "research"),
                    "shadow_chat_id": getattr(settings, "research_v3_chat_id", None)
                    or getattr(settings.telegram, "shadow_chat_id", None),
                    "web_url": getattr(settings.web, "public_url", None),
                    "pattern_id": item.get("pattern_id"),
                    "pattern_type": item.get("pattern_type"),
                    "pattern_stage": item.get("pattern_stage"),
                    "pattern_status": item.get("pattern_status"),
                    "pattern_quality": item.get("pattern_quality"),
                    "evidence_kind": item.get("evidence_kind"),
                }
                for fill in fills[1:]:
                    # Entry2/Entry3 are lifecycle events in their own right.
                    # Stable leg keys make retries/restarts idempotent.  They
                    # are staged before the terminal event so replies mirror
                    # the actual fill chronology.
                    notification_events.append(
                        {
                            **base_event,
                            "event_type": "entry_fill",
                            "status": "entry_fill",
                            "event_time": fill.get("timestamp"),
                            "average_entry": fill.get("average_entry"),
                            "entry_price": fill.get("price"),
                            "filled_legs": fill.get("leg"),
                            "actual_fill": True,
                            "event_key": f"{identity}:fill:{fill.get('leg')}",
                        }
                    )
                if actual_status in {"target", "stop", "stop_ambiguous", "timeout"}:
                    notification_events.append(
                        {
                            **base_event,
                            "event_type": actual_status,
                            "status": actual_status,
                            "exit_price": result.get("exit_price"),
                            "event_key": f"{identity}:actual:{actual_status}",
                        }
                    )
                if post_stop.get("status") in {"target_after_stop", "timeout_after_stop"}:
                    notification_events.append(
                        {
                            **base_event,
                            "event_type": "post_stop",
                            "status": post_stop.get("status"),
                            "price_only_post_stop": True,
                            "stop_average_entry": post_stop.get("frozen_average_entry"),
                            "frozen_average_entry": post_stop.get("frozen_average_entry"),
                            "frozen_target_price": post_stop.get("frozen_target_price"),
                            "target_time": post_stop.get("target_time"),
                            "horizon_time": post_stop.get("horizon_time"),
                            "contract": post_stop.get("contract"),
                            "contract_checksum": post_stop.get("contract_checksum"),
                            "event_time": post_stop.get("target_time")
                            or post_stop.get("horizon_time")
                            or now,
                            "event_key": f"{identity}:post_stop:{post_stop.get('status')}",
                        }
                    )
        state["timing"] = _dump_timing(timing)
        ledger.execute("INSERT OR REPLACE INTO state VALUES (1, ?)", [canonical(state)])
        recent = ledger.execute("""
            SELECT o.id, o.payload, r.payload
            FROM (
                SELECT id, payload, selected, timestamp, symbol,
                       row_number() OVER (PARTITION BY symbol ORDER BY selected DESC, timestamp DESC) as rn
                FROM observations
            ) o
            LEFT JOIN outcomes r ON o.id=r.id
            WHERE o.rn=1
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
    if dispatcher is not None:
        for event in notification_events:
            try:
                if event.get("event_type") == "signal":
                    dispatcher.dispatch_signal(event)
                else:
                    dispatcher.dispatch_outcome(event)
            except Exception as exc:
                # Outbox implementations normally persist failures; retain
                # scanner progress even if an adapter itself is unavailable.
                pattern_error = pattern_error or f"notification_dispatch_failed:{type(exc).__name__}"
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
                         now=datetime.now(timezone.utc), discovery=discovery, settings=settings,
                         pattern_artifact=getattr(settings, "research_v3_pattern_artifact", None))
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
