"""Read-only market adapter for identical locked-Entry1 retrospective audits.

This is NOT a replay of the candidate universe or a new timing backtest. It
preserves the old Entry1 keys to isolate execution semantics, including old
incomplete events. Funding observations alone do not attest coverage.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path

import duckdb
import pandas as pd

from dao_vang.experiments.distribution_v3 import (
    PARENT,
    SCOUT,
    EvidenceLedger,
    canonical,
    digest,
    scout_gate,
    time_value,
)
from dao_vang.labels.engine_v3 import Bar, Funding, evaluate
from dao_vang.labels.specs.distribution_short_v3 import SPEC

ADAPTER_VERSION = "locked_market_audit_v1.2"
MARKET = "USD-M Futures"


def file_hash(path: Path) -> str:
    result = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def boundary(value: datetime) -> datetime:
    """Convert Binance inclusive millisecond close to exclusive bar boundary.

    No flooring/nearest rounding: unknown timestamp conventions must fail.
    """
    shifted = value + timedelta(milliseconds=1)
    if shifted.microsecond or int(shifted.timestamp()) % 300:
        raise ValueError("expected Binance 5m inclusive close ending .999")
    return shifted


def keys(rows: list[dict], column: str) -> list[tuple[str, datetime]]:
    result = [(row["symbol"], time_value(row[column])) for row in rows]
    if len(set(result)) != len(result):
        raise ValueError("duplicate locked signal keys")
    return result


def load_locked(lock_dir: Path) -> tuple[list[dict], dict, dict]:
    report_path = lock_dir / "forward48_timing_locked_forward_report.json"
    keys_path = lock_dir / "forward48_timing_august_locked_signal_keys.csv"
    signals_path = lock_dir / "forward48_timing_august_signals_live.csv"
    model_path = lock_dir / "forward48_timing_research_model.joblib"
    report = json.loads(report_path.read_text("utf-8"))
    locked = report["immutable_inputs"]
    if locked.get("august_labels_used_for_model_or_policy_selection") is not False:
        raise ValueError("report does not declare August-free selection")
    if file_hash(keys_path) != locked["signal_keys_sha256_before_outcome_load"]:
        raise ValueError("locked key checksum mismatch")
    if file_hash(model_path) != locked["model_sha256"]:
        raise ValueError("locked model checksum mismatch")
    rows = read_csv(signals_path)
    if set(keys(rows, "feature_time")) != set(
        keys(read_csv(keys_path), "feature_time")
    ):
        raise ValueError("signal rows differ from locked keys")
    if len(rows) != report["august"]["signals"]:
        raise ValueError("signal count differs from locked report")
    expected = dict(
        min_peak_pump_24h=0.3,
        confirmations=2,
        min_episode_age_hours=4,
        min_probability_peak_drop=0.0,
        min_drawdown_from_high=0.0,
        require_ret5_nonpositive=False,
        probability_tolerance=0.1,
    )
    if locked["selected_policy"] != expected or not math.isclose(
        locked["threshold"], 0.39
    ):
        raise ValueError("unexpected locked timing policy")
    provenance = {
        "dataset_id": "august_opened_locked_entry1",
        "model_id": model_path.stem,
        "model_checksum": file_hash(model_path),
        "feature_schema": "locked_25_features",
        "score_label_version": "distribution_short_v2_48h_research_entry1",
        "data_source": "local_live_duckdb",
        "evidence_kind": "retrospective",
        "pit_verified": False,
        "pit_notice": "historical feature availability/collection is not certified",
        "source_hashes": {
            p.name: file_hash(p) for p in (report_path, keys_path, signals_path)
        },
    }
    return rows, report, provenance


def stabilize_source(
    connection, table: str, source_db: Path | None
) -> tuple[str, dict]:
    """Resolve collector revisions deterministically without rewriting live views.

    Existing views rank only available_time. Ties with different collection times
    otherwise select arbitrary OHLC. This retrospective adapter chooses newest
    available_time THEN newest collected_at, and rejects conflicting exact ties.
    It does not pretend the latest collected revision was available at Entry1.
    """
    view = connection.execute(
        "SELECT sql FROM duckdb_views() WHERE view_name=?", [table]
    ).fetchone()
    if view is None:
        return table, {"source": "base_table"}
    if source_db is None or "read_parquet(" not in view[0]:
        raise ValueError(
            "view-backed market source needs explicit normalized source path"
        )
    folder = "klines" if table == "kline" else "funding"
    if f"normalized/{folder}/" not in view[0].replace("\\", "/"):
        raise ValueError("unsupported parquet-backed market view")
    glob = str(source_db.resolve().parent / "normalized" / folder / "**/*.parquet")
    quoted = glob.replace("'", "''")
    temporal = "close_time" if table == "kline" else "funding_time"
    columns = (
        "symbol, market, interval, open_time, close_time, open, high, low, close, "
        "quality_status, available_time, collected_at"
        if table == "kline"
        else "symbol, market, interval, funding_time, funding_rate, mark_price, "
        "quality_status, available_time, collected_at"
    )
    source = f"v3_source_{table}"
    connection.execute(f"""
        CREATE TEMP TABLE {source}_ranked AS
        SELECT {columns},
            dense_rank() OVER (
                PARTITION BY symbol, market, {temporal}
                ORDER BY available_time DESC NULLS LAST, collected_at DESC NULLS LAST
            ) AS revision_rank
        FROM read_parquet('{quoted}', union_by_name=true) raw
        WHERE market='USD-M Futures'
          {"AND interval='5m'" if table == "kline" else ""}
          AND EXISTS (
              SELECT 1 FROM v3_locked_keys s WHERE s.symbol=raw.symbol
                AND raw.{temporal}>=s.source_time
                AND raw.{temporal}<=s.source_time+INTERVAL '48' HOUR+INTERVAL '1' MILLISECOND
          )
    """)
    connection.execute(f"""
        CREATE TEMP TABLE {source} AS
        SELECT DISTINCT {columns} FROM {source}_ranked WHERE revision_rank=1
    """)
    conflict = connection.execute(f"""
        SELECT symbol, {temporal}, count(*) FROM {source}
        GROUP BY symbol, {temporal} HAVING count(*)>1 LIMIT 1
    """).fetchone()
    if conflict:
        raise ValueError(f"conflicting same-rank {table} revisions: {conflict}")
    raw_count = connection.execute(f"SELECT count(*) FROM {source}_ranked").fetchone()[
        0
    ]
    chosen_count = connection.execute(f"SELECT count(*) FROM {source}").fetchone()[0]
    return source, {
        "source": "normalized_parquet_collector_revisions",
        "raw_rows": raw_count,
        "selected_rows": chosen_count,
        "superseded_or_identical_rows": raw_count - chosen_count,
        "revision_rule": "available_time_desc_then_collected_at_desc_reject_conflicting_ties",
    }


def load_paths(
    connection, rows: list[dict], source_db: Path | None = None
) -> tuple[dict, dict]:
    """Snapshot OHLC and observed funding without changing the source database."""
    reference = pd.DataFrame(
        [
            {
                "symbol": row["symbol"],
                "source_time": time_value(row["feature_time"]),
                "key": str(index),
            }
            for index, row in enumerate(rows)
        ]
    )
    connection.register("v3_locked_keys", reference)
    kline_source, kline_revisions = stabilize_source(connection, "kline", source_db)
    funding_source, funding_revisions = stabilize_source(
        connection, "funding", source_db
    )
    paths = {str(i): {"bars": [], "funding": [], "audit": {}} for i in range(len(rows))}
    entry_rows = connection.execute(
        f"""
        SELECT s.key, CAST(k.close AS DOUBLE), k.quality_status, k.available_time,
               k.collected_at
        FROM v3_locked_keys s JOIN {kline_source} k
          ON k.symbol=s.symbol AND k.close_time=s.source_time
         AND k.interval='5m' AND k.market=?
        ORDER BY s.key
    """,
        [MARKET],
    ).fetchall()
    counts = Counter(row[0] for row in entry_rows)
    for index, row in enumerate(rows):
        if counts[str(index)] != 1:
            raise ValueError("entry OHLC join must be exactly one row per locked key")
    for key, price, quality, available, collected in entry_rows:
        if quality != "valid" or not math.isclose(
            price, float(rows[int(key)]["entry_price"]), rel_tol=1e-10
        ):
            raise ValueError("source entry close/quality differs from locked entry")
        paths[key]["audit"].update(
            entry_available_time=available, entry_collected_at=collected
        )
    price_rows = connection.execute(
        f"""
        SELECT s.key, k.open_time, k.close_time, CAST(k.open AS DOUBLE),
               CAST(k.high AS DOUBLE), CAST(k.low AS DOUBLE), CAST(k.close AS DOUBLE),
               k.quality_status
        FROM v3_locked_keys s JOIN {kline_source} k
          ON k.symbol=s.symbol AND k.interval='5m' AND k.market=?
         AND k.close_time>s.source_time
         AND k.close_time<=s.source_time+INTERVAL '48' HOUR
        ORDER BY s.key, k.close_time
    """,
        [MARKET],
    ).fetchall()
    for key, opened, closed, op, high, low, close, quality in price_rows:
        if quality != "valid":
            paths[key]["audit"]["invalid_price_rows"] = (
                paths[key]["audit"].get("invalid_price_rows", 0) + 1
            )
            continue  # missing intervals are explicitly excluded by the engine
        end = boundary(closed)
        if end - opened != timedelta(minutes=5):
            raise ValueError("invalid source bar duration")
        paths[key]["bars"].append(Bar(end, op, high, low, close))
    funding_rows = connection.execute(
        f"""
        SELECT s.key, f.funding_time, CAST(f.funding_rate AS DOUBLE),
               CAST(f.mark_price AS DOUBLE), f.quality_status, f.interval
        FROM v3_locked_keys s JOIN {funding_source} f
          ON f.symbol=s.symbol AND f.market=?
         AND f.funding_time>s.source_time+INTERVAL '1' MILLISECOND
         AND f.funding_time<=s.source_time+INTERVAL '48' HOUR+INTERVAL '1' MILLISECOND
        ORDER BY s.key, f.funding_time
    """,
        [MARKET],
    ).fetchall()
    for key, when, rate, mark, quality, interval in funding_rows:
        if when.microsecond or int(when.timestamp()) % 300:
            paths[key]["audit"].setdefault(
                "unaligned_funding_not_simulated", []
            ).append({"timestamp": when, "rate": rate, "mark_price": mark})
            continue  # never round settlements across a fill/exit boundary
        if quality != "valid" or mark is None or mark <= 0 or rate is None:
            paths[key]["audit"]["invalid_funding_rows"] = (
                paths[key]["audit"].get("invalid_funding_rows", 0) + 1
            )
            continue
        paths[key]["funding"].append(Funding(when, rate, mark))
    return paths, {
        "kline_revision_audit": kline_revisions,
        "funding_revision_audit": funding_revisions,
        "entry_exact_matches": len(entry_rows),
        "price_rows": len(price_rows),
        "observed_funding_rows": len(funding_rows),
        "unaligned_funding_rows_not_simulated": sum(
            len(path["audit"].get("unaligned_funding_not_simulated", []))
            for path in paths.values()
        ),
        "funding_coverage_attested": False,
        "funding_notice": "No collection-completeness manifest or PIT settlement schedule; do not infer zero/missing payments",
        "source_time_mapping": "Binance inclusive close +1ms; funding timestamps unchanged",
        "source_slice_checksum": digest(
            {"entries": entry_rows, "prices": price_rows, "funding": funding_rows}
        ),
    }


def mean(rows: list[dict], column: str) -> float | None:
    return sum(row[column] for row in rows) / len(rows) if rows else None


def audit_locked_market(
    *, live_db: Path, lock_dir: Path, old_events: Path, output_dir: Path
) -> dict:
    rows, old_report, provenance = load_locked(lock_dir)
    old = [row for row in read_csv(old_events) if row["template_id"] == "compact_0_3_6"]
    old_keys = keys(old, "signal_time")
    if set(old_keys) != set(keys(rows, "feature_time")):
        raise ValueError("old compact comparison must cover the exact locked keys")
    old_by_key = dict(zip(old_keys, old, strict=True))
    provenance["source_hashes"][old_events.name] = file_hash(old_events)
    with duckdb.connect(str(live_db), read_only=True) as connection:
        connection.execute("BEGIN TRANSACTION")
        paths, coverage = load_paths(connection, rows, live_db)
    provenance["market_slice_checksum"] = coverage["source_slice_checksum"]
    events, decisions, evaluations, comparison = [], [], [], []
    for index, row in enumerate(rows):
        source_time = time_value(row["feature_time"])
        snapshot = {
            "symbol": row["symbol"],
            "source_feature_time": source_time,
            "feature_time": boundary(source_time),
            "signal_price": float(row["entry_price"]),
            "score": float(row["probability"]),
            **{
                key: float(row[key]) if row[key] else None
                for key in (
                    "funding_percentile_30d",
                    "funding_persistence_7d",
                    "funding_change_8h",
                )
            },
        }
        event = {"snapshot": snapshot, "provenance": provenance}
        event_id = digest(event)
        events.append({"event_id": event_id, **event})
        in_scout = scout_gate(snapshot) == "selected"
        for lane in (PARENT, SCOUT):
            decisions.append(
                {
                    "event_id": event_id,
                    "lane": lane,
                    "selected": lane == PARENT or in_scout,
                    "reason": "locked_entry1"
                    if lane == PARENT
                    else scout_gate(snapshot),
                }
            )
        path = paths[str(index)]
        for diagnostic in (False, True):
            outcome = evaluate(
                signal_time=snapshot["feature_time"],
                signal_price=snapshot["signal_price"],
                bars=path["bars"],
                funding=path["funding"],
                funding_coverage_through=None,
                entry1_only=diagnostic,
            )
            evaluations.append({"event_id": event_id, **outcome.to_dict()})
            if diagnostic:
                continue
            prior = old_by_key[row["symbol"], source_time]
            resolved = outcome.exit_time is not None
            comparison.append(
                {
                    "event_id": event_id,
                    "symbol": row["symbol"],
                    "source_feature_time": source_time,
                    "in_scout": in_scout,
                    "old_status": prior["status"],
                    "old_complete": prior["complete_path"].lower() == "true",
                    "old_net_with_legacy_funding": float(prior["net_return_planned"]),
                    "old_price_pnl_after_cost": float(prior["net_return_planned"])
                    - float(prior["funding_return_planned"]),
                    "new_status": outcome.status,
                    "new_price_resolved": resolved,
                    "new_filled_legs": len(outcome.fills),
                    "new_average_entry": outcome.fills[-1].average_entry,
                    "new_price_pnl_after_cost": outcome.gross_return_planned
                    - outcome.costs_planned
                    if outcome.gross_return_planned is not None
                    and outcome.costs_planned is not None
                    else None,
                    "observed_funding_cash_flow_not_complete": sum(
                        p.cash_flow for p in outcome.funding_payments
                    ),
                    "new_net_return_planned": outcome.net_return_planned,
                    "exclusion_reason": outcome.exclusion_reason,
                    "path_audit": path["audit"],
                }
            )
    summary = {}
    for lane in (PARENT, SCOUT):
        selected = [row for row in comparison if lane == PARENT or row["in_scout"]]
        paired = [
            row for row in selected if row["old_complete"] and row["new_price_resolved"]
        ]
        resolved = [row for row in selected if row["new_price_resolved"]]
        summary[lane] = {
            "locked_entries": len(selected),
            "price_resolved": len(resolved),
            "price_status_counts": dict(Counter(row["new_status"] for row in selected)),
            "fully_costed_funding_verified": 0,
            "verified_net_ev": None,
            "paired_price_resolved": len(paired),
            "old_target_rate_on_paired": sum(
                row["old_status"] == "target" for row in paired
            )
            / len(paired)
            if paired
            else None,
            "new_target_rate_on_paired_price_only": sum(
                row["new_status"] == "target" for row in paired
            )
            / len(paired)
            if paired
            else None,
            "old_mean_price_pnl_after_cost_on_paired": mean(
                paired, "old_price_pnl_after_cost"
            ),
            "new_mean_price_pnl_after_cost_on_paired": mean(
                paired, "new_price_pnl_after_cost"
            ),
            "changed_outcome_keys": [
                row["symbol"] + ":" + row["source_feature_time"].isoformat()
                for row in paired
                if row["old_status"] != row["new_status"]
            ],
        }
    result = {
        "run_id": digest(
            {
                "provenance": provenance,
                "adapter": ADAPTER_VERSION,
                "contract": asdict(SPEC),
            }
        ),
        "adapter_version": ADAPTER_VERSION,
        "provenance": provenance,
        "contract": asdict(SPEC),
        "contract_checksum": SPEC.checksum,
        "live_eligible": False,
        "promotion_eligible": False,
        "scope": "locked_entry_execution_comparison_not_universe_timing_replay",
        "original_candidate_count_not_replayed": old_report["coverage"][
            "hourly_feature_candidates"
        ],
        "coverage": coverage,
        "summary": summary,
        "events": events,
        "decisions": decisions,
        "evaluations": evaluations,
        "comparison": comparison,
        "source_paths": {
            key: {
                "bars": [asdict(bar) for bar in path["bars"]],
                "funding": [asdict(payment) for payment in path["funding"]],
                "audit": path["audit"],
            }
            for key, path in paths.items()
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    EvidenceLedger(output_dir / "evidence.sqlite").save(result)
    # Content-addressed artifacts: never overwrite an earlier audit.
    report_path = output_dir / f"{result['run_id']}.json"
    text = canonical(result)
    if report_path.exists() and report_path.read_text("utf-8") != text:
        raise ValueError("immutable market report conflict")
    if not report_path.exists():
        report_path.write_text(text, encoding="utf-8")
    return result
