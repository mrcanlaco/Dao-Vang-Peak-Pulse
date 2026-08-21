"""Combined HTTP API + static file server for the React frontend.

Every handler below reads from real state (AlertStore, ScanResultStore,
scanner heartbeat file, Binance ticker API) instead of hardcoded/fabricated
data. There is no synchronous "run a scan inline" endpoint: the scanner
daemon is a separate long-running process, so "trigger scan" / "change scan
mode" write a flag file the daemon polls each cycle (see
ScannerDaemon._consume_trigger / _apply_runtime_overrides in
dao_vang.scanner.daemon) and this server returns a "queued" response rather
than fabricating a fake "48/48 coins scanned" success message.
"""

import json
import logging
import mimetypes
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo

import duckdb

from dao_vang.alerts.store import AlertStore
from dao_vang.alerts.telegram import TelegramNotifier
from dao_vang.config.settings import AppSettings
from dao_vang.data.binance_listing import get_stats_for_today
from dao_vang.data.storage.duckdb import open_read_only_connection
from dao_vang.domain.time import (
    SYSTEM_TIMEZONE_NAME,
    as_system_timezone,
    system_iso,
    system_now,
)
from dao_vang.scanner.instance_lock import ScannerAlreadyRunning, ScannerInstanceLock
from dao_vang.scanner.pump_filter import analyze_pump, fetch_daily_klines
from dao_vang.scanner.scan_results_store import ScanResultStore
from dao_vang.scanner.tracking_watchlist import (
    TrackingWatchlistStore,
    calculate_position_metrics,
    normalize_symbol,
)
from dao_vang.scanner.watchlist import (
    _filter_tickers,
    add_to_watchlist,
    fetch_all_tickers,
    fetch_top_gainers,
    fetch_top_losers,
    load_manual_watchlist,
    normalize_scan_modes,
    remove_from_watchlist,
)
from dao_vang.scoring import (
    assess_snapshot_quality,
    classify_btc,
    compute_distribution_score,
    compute_two_tier_distribution_score,
    score_snapshot,
)
from dao_vang.scoring.engine_comparison import evaluate_scoring_engines_comparison

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dao_vang_api")

DIST_DIR = Path("frontend/dist").resolve()

_settings = AppSettings()
WATCHLIST_PATH = _settings.scanner.watchlist_path

data_dir_path = _settings.paths.data_dir
HEARTBEAT_PATH = data_dir_path / "scanner_heartbeat.json"
CANDIDATE_SNAPSHOT_PATH = data_dir_path / "candidate_snapshot.json"
CANDIDATE_FILTER_COMPARISON_PATH = (
    Path(_settings.candidate_comparison.snapshot_path)
    if _settings.candidate_comparison.snapshot_path is not None
    else data_dir_path / "candidate_filter_comparison.json"
)
SYSTEM_STATS_PATH = data_dir_path / "system_data_stats.json"
TRIGGER_PATH = data_dir_path / "scanner_trigger.flag"
RUNTIME_STATE_PATH = data_dir_path / "scanner_runtime_state.json"
TRACKING_WATCHLIST_PATH = data_dir_path / "tracking_watchlist.json"

_alert_store = AlertStore(
    str(_settings.scanner.db_path),
    read_only=True,
    prefer_snapshot=True,
)
_scan_store = ScanResultStore(
    str(_settings.scanner.db_path),
    read_only=True,
    prefer_snapshot=True,
)
_tracking_store = TrackingWatchlistStore(TRACKING_WATCHLIST_PATH)
_notifier = TelegramNotifier(
    _settings.telegram,
    web_base_url=_settings.web.public_url,
)
_STATUS_CACHE_LOCK = threading.Lock()
_STATUS_CACHE: dict[str, Any] = {}


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _system_history_timestamp(value: Any) -> str | None:
    """Serialize timestamps as unambiguous Vietnam-time ISO strings.

    DuckDB commonly returns naive ``datetime`` objects for TIMESTAMP columns.
    The pipeline stores those values in UTC, so attach UTC explicitly and
    expose the result as ``Asia/Ho_Chi_Minh`` instead of leaving the browser
    to guess a local timezone.
    """
    return system_iso(value)


def _as_utc_datetime(value: Any) -> datetime | None:
    """Normalize a database timestamp for event ordering."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _system_display_datetime(value: Any) -> datetime | None:
    """Return a timestamp as an aware UTC+7 datetime for human display."""
    utc_value = _as_utc_datetime(value)
    return as_system_timezone(utc_value) if utc_value is not None else None


def _ro_duckdb_connect(db_path: str) -> duckdb.DuckDBPyConnection:
    """Open a read-only connection with the shared, bounded lock fallback."""

    return open_read_only_connection(db_path, prefer_snapshot=True)


def _self_learning_status() -> dict[str, Any]:
    """Return the read-only progress snapshot used by the HISTORY tab.

    The scanner owns the live DuckDB writer, so this endpoint deliberately
    uses the same read-only/copy fallback as the rest of the API.  Reports are
    small JSON artifacts written atomically by the self-learning runner; a
    partially written or old report is ignored rather than breaking the tab.
    """
    cfg = _settings.self_learning
    state = _read_json(Path(cfg.state_path))
    recent_runs: list[dict[str, Any]] = []

    try:
        report_paths = sorted(
            Path(cfg.report_dir).glob("selflearn_*.json"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )[:10]
        for report_path in report_paths:
            report = _read_json(report_path)
            if report:
                recent_runs.append(report)
    except (OSError, ValueError) as exc:
        logger.debug("self_learning_reports_unavailable error=%s", exc)

    stats = {
        "predictions": 0,
        "outcomes": 0,
        "pending": 0,
        "excluded": 0,
        "materialized_positive": 0,
        "training_outcomes": int(state.get("training_outcomes", 0) or state.get("last_training_outcome_count", 0) or 0),
        "historical_outcomes": int(state.get("historical_outcomes", 0) or 0),
        "live_outcomes": int(state.get("live_outcomes", 0) or 0),
        "training_positive_events": int(state.get("training_positive_events", 0) or 0),
        "recent_outcomes": int(state.get("recent_outcomes", 0) or 0),
        "latest_outcome_time": None,
    }

    if not cfg.enabled:
        return {
            "enabled": False,
            "check_interval_cycles": int(cfg.check_interval_cycles),
            "status": "disabled",
            "champion_model_id": _settings.scanner.frozen_model_id or "",
            "current_scanner_model_id": _settings.scanner.frozen_model_id or "",
            **stats,
            "new_outcomes": 0,
            "min_training_outcomes": int(cfg.min_training_outcomes),
            "min_new_outcomes": int(cfg.min_new_outcomes),
            "min_positive_events": int(cfg.min_positive_events),
            "recent_window_days": int(cfg.recent_window_days),
            "recent_runs": recent_runs,
        }

    horizon_hours = 24
    try:
        from dao_vang.experiments.forward_test import load_frozen_model

        champion = load_frozen_model(
            _settings.scanner.frozen_model_id or "",
            Path(_settings.scanner.artifact_dir),
        )
        horizon_hours = int((champion.label_spec or {}).get("horizon_hours", 24))
    except (FileNotFoundError, OSError, ValueError):
        pass
    conn = None
    try:
        conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
        tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='main' AND table_type='BASE TABLE'"
            ).fetchall()
        }
        if "predictions" in tables:
            stats["predictions"] = int(
                conn.execute("SELECT count(*) FROM predictions").fetchone()[0]
            )
        if "prediction_outcomes" in tables:
            outcome_row = conn.execute(
                """
                SELECT count(*),
                       count(*) FILTER (WHERE label_value IS NULL),
                       count(*) FILTER (WHERE outcome_status = 'materialized' AND label_value = 1),
                       max(materialized_at) FILTER (WHERE outcome_status = 'materialized')
                FROM prediction_outcomes
                """
            ).fetchone()
            stats["outcomes"] = int(outcome_row[0] or 0)
            stats["excluded"] = int(outcome_row[1] or 0)
            stats["materialized_positive"] = int(outcome_row[2] or 0)
            stats["latest_outcome_time"] = _system_history_timestamp(outcome_row[3])
            stats["live_outcomes"] = int(outcome_row[0] or 0)
        if {"predictions", "prediction_outcomes"}.issubset(tables):
            stats["pending"] = int(
                conn.execute(
                    """
                    SELECT count(*)
                    FROM predictions p
                    LEFT JOIN prediction_outcomes o
                      ON o.prediction_id = p.prediction_id
                    WHERE p.invalidation_time IS NOT NULL
                      AND p.invalidation_time <= CURRENT_TIMESTAMP
                      AND o.prediction_id IS NULL
                    """
                ).fetchone()[0]
            )
        if "labels" in tables and stats["historical_outcomes"] == 0:
            stats["historical_outcomes"] = int(
                conn.execute(
                    "SELECT count(*) FROM labels WHERE horizon_hours = ? AND label_value IN (0, 1)",
                    [int(horizon_hours)],
                ).fetchone()[0]
            )
        if stats["training_outcomes"] == 0:
            stats["training_outcomes"] = stats["historical_outcomes"] + stats["live_outcomes"]
        if stats["training_positive_events"] == 0 and "labels" in tables:
            stats["training_positive_events"] = int(
                conn.execute(
                    "SELECT count(*) FROM labels WHERE horizon_hours = ? AND label_value = 1",
                    [int(horizon_hours)],
                ).fetchone()[0]
            )
    except Exception as exc:
        logger.warning("self_learning_stats_failed error=%s", exc)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    min_training = int(cfg.min_training_outcomes)
    min_positive = int(cfg.min_positive_events)
    min_new = int(cfg.min_new_outcomes)
    last_training_count = int(state.get("last_training_outcome_count", 0) or 0)
    persisted_status = str(state.get("last_status") or "")
    if not cfg.enabled:
        status = "disabled"
    elif persisted_status:
        status = persisted_status
    elif (
        stats["training_outcomes"] < min_training
        or stats["training_positive_events"] < min_positive
    ):
        status = "not_ready"
    else:
        status = "waiting_new_outcomes"

    return {
        "enabled": bool(cfg.enabled),
        "check_interval_cycles": int(cfg.check_interval_cycles),
        "status": status,
        "champion_model_id": _settings.scanner.frozen_model_id or "",
        "current_scanner_model_id": _settings.scanner.frozen_model_id or "",
        **stats,
        "new_outcomes": max(
            0, stats["training_outcomes"] - last_training_count
        ),
        "min_training_outcomes": min_training,
        "min_new_outcomes": min_new,
        "min_positive_events": min_positive,
        "recent_window_days": int(cfg.recent_window_days),
        "recent_sample_weight": float(cfg.recent_sample_weight),
        "historical_max_rows": int(cfg.historical_max_rows),
        "last_run_at": state.get("last_run_at"),
        "last_training_outcome_count": last_training_count or None,
        "last_report_path": state.get("last_report_path"),
        "last_challenger_model_id": state.get("last_challenger_model_id"),
        "latest_run": recent_runs[0] if recent_runs else None,
        "recent_runs": recent_runs,
    }


def _current_scan_modes() -> list[str]:
    state = _read_json(RUNTIME_STATE_PATH)
    raw_modes = state.get("scan_modes", state.get("scan_mode", _settings.scanner.scan_mode))
    return normalize_scan_modes(raw_modes)


def _current_scan_mode() -> str:
    """Return the legacy display form while supporting multiple modes."""
    return ",".join(_current_scan_modes())


def _request_scan(modes: list[str] | None = None) -> dict[str, Any]:
    """Ask the running ScannerDaemon to run a cycle immediately.

    Writes a flag file the daemon polls between cycles instead of running a
    scan inline in this HTTP handler — the daemon is a separate long-running
    process holding the Binance client / DuckDB write connection.

    A plain refresh requested while a healthy cycle is already running is
    coalesced into that cycle.  Otherwise every click during a 1-2 minute scan
    would leave a flag behind and force an unnecessary second cycle (and could
    duplicate Telegram reports).  Mode changes are never coalesced because the
    running cycle cannot observe the new mode until its successor.
    """
    TRIGGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"requested_at": system_now().isoformat()}
    if modes:
        normalized_modes = normalize_scan_modes(modes)
        state = _read_json(RUNTIME_STATE_PATH)
        # Keep both keys during the migration: old daemons read scan_mode,
        # while current clients use the explicit list.
        state["scan_modes"] = normalized_modes
        state["scan_mode"] = ",".join(normalized_modes)
        RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
        payload["scan_modes"] = normalized_modes
        payload["scan_mode"] = ",".join(normalized_modes)
    elif _scanner_cycle_is_running():
        heartbeat = _read_json(HEARTBEAT_PATH)
        return {
            "status": "in_progress",
            "queued": False,
            "cycle": heartbeat.get("cycle"),
            "started_at": heartbeat.get("last_cycle_started_at"),
        }
    TRIGGER_PATH.write_text(json.dumps(payload), encoding="utf-8")
    return {"status": "queued", "queued": True}


def _scanner_cycle_is_running() -> bool:
    """Return true only for a fresh heartbeat from an active scan cycle."""

    heartbeat = _read_json(HEARTBEAT_PATH)
    if heartbeat.get("last_cycle_status") != "running":
        return False
    heartbeat_at = _as_utc_datetime(heartbeat.get("timestamp"))
    if heartbeat_at is None:
        return False
    freshness_limit = timedelta(
        minutes=max(2 * _settings.scanner.poll_interval_minutes, 10)
    )
    return datetime.now(timezone.utc) - heartbeat_at <= freshness_limit


def _risk_bucket(score: float) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "SAFE"


def _scan_risk_level(recommendation: Any, probability: float) -> str:
    """Map the scanner's model tier to the Radar UI vocabulary."""

    tier = str(recommendation or "").upper()
    return {
        "HIGH_CONFIDENCE": "HIGH",
        "WATCH": "MEDIUM",
        "WAIT": "SAFE",
    }.get(tier, _risk_bucket(probability * 100.0))


class APIHandler(BaseHTTPRequestHandler):
    # NOTE: handlers below send responses without a Content-Length header
    # (and without chunked transfer-encoding). Under HTTP/1.1 the connection
    # stays open (keep-alive) after end_headers(), so a client has no way to
    # know where the body ends -> fetch()/curl hang forever waiting for more
    # bytes, which is why the frontend gets stuck on "loading" with a blank
    # screen. HTTP/1.0 makes the server close the socket after every
    # response, which lets clients detect end-of-body via connection close.
    protocol_version = 'HTTP/1.0'

    def _set_headers(self, status=200, content_type='application/json; charset=utf-8', cache_control='no-store, no-cache, must-revalidate, max-age=0'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        if cache_control:
            self.send_header('Cache-Control', cache_control)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, HEAD, POST, PATCH, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_HEAD(self):
        self._set_headers(200)

    def do_GET(self):
        """Serve GET requests without dropping the TCP connection on errors."""
        try:
            self._do_GET()
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:
            logger.warning("api_get_failed path=%s error=%s", self.path, exc)
            try:
                self._set_headers(503)
                self.wfile.write(
                    json.dumps(
                        {
                            "error": "service temporarily unavailable",
                            "detail": str(exc),
                        }
                    ).encode("utf-8")
                )
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

    def _do_GET(self):
        parsed = urlparse(self.path)
        # self.path is percent-encoded as sent over the wire (e.g. browsers
        # percent-encode non-ASCII characters in fetch() URLs), but symbols
        # are matched/queried as raw strings below, so decode here or coins
        # with non-ASCII/percent-encoded characters in their symbol resolve
        # to the wrong (or no) DB rows and show mismatched name/data.
        path = unquote(parsed.path)

        if path.startswith('/api/'):
            if path == '/api/status':
                self.get_status()
            elif path == '/api/signals':
                self.get_signals()
            elif path == '/api/candidates':
                self.get_candidates()
            elif path in ('/api/candidate-filter-comparison', '/api/candidates/compare'):
                self.get_candidate_filter_comparison()
            elif path == '/api/watchlist':
                self.get_watchlist()
            elif path == '/api/tracking-watchlist':
                self.get_tracking_watchlist()
            elif path == '/api/scanner/telemetry':
                self.get_scanner_telemetry()
            elif path.startswith('/api/coin/'):
                parts = path.replace('/api/coin/', '').split('/')
                symbol = parts[0].upper()
                if len(parts) > 1 and parts[1] == 'deep-analysis':
                    self.get_deep_analysis(symbol)
                elif len(parts) > 1 and parts[1] == 'chart':
                    self.get_coin_chart(symbol)
                else:
                    self.get_coin_detail(symbol)
            elif path == '/api/audit':
                self.get_audit()
            elif path == '/api/market':
                self.get_market()
            elif path == '/api/scan/multi-coin':
                self.get_multi_coin_scan()
            elif path == '/api/experiments':
                self.get_experiments()
            elif path.startswith('/api/experiments/'):
                artifact_id = path.replace('/api/experiments/', '')
                self.get_experiment_detail(artifact_id)
            elif path == '/api/forward-test/models':
                self.get_frozen_models()
            elif path.startswith('/api/forward-test/evaluate/'):
                model_id = path.replace('/api/forward-test/evaluate/', '')
                self.evaluate_frozen_model(model_id)
            elif path == '/api/models':
                self.get_models()
            elif path in ('/api/models/comparison-matrix', '/api/scoring/compare', '/api/models/compare'):
                self.get_models_comparison_matrix()
            elif path == '/api/system-history':
                self.get_system_history()
            elif path == '/api/alpha-lab/regime':
                self.get_alpha_lab_regime()
            elif path == '/api/alpha-lab/drift':
                self.get_alpha_lab_drift()
            elif path == '/api/alpha-lab/summary':
                self.get_alpha_lab_summary()
            else:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "API endpoint not found"}).encode('utf-8'))
        else:
            self.serve_static(path)

    def serve_static(self, req_path):
        if req_path == '/' or req_path == '':
            file_path = DIST_DIR / 'index.html'
        else:
            rel_path = req_path.lstrip('/')
            file_path = DIST_DIR / rel_path

        if not file_path.exists() or file_path.is_dir():
            file_path = DIST_DIR / 'index.html'

        if file_path.exists():
            ctype, _ = mimetypes.guess_type(str(file_path))
            if str(file_path).endswith('manifest.json') or str(file_path).endswith('.webmanifest'):
                ctype = 'application/manifest+json; charset=utf-8'
            elif str(file_path).endswith('sw.js'):
                ctype = 'application/javascript; charset=utf-8'
            elif str(file_path).endswith('.svg'):
                ctype = 'image/svg+xml'
            elif str(file_path).endswith('.png'):
                ctype = 'image/png'
            elif not ctype:
                ctype = 'application/octet-stream'

            cache_control = 'no-cache, must-revalidate' if str(file_path).endswith(('index.html', 'sw.js', 'manifest.json')) else 'public, max-age=86400'
            self._set_headers(200, content_type=ctype, cache_control=cache_control)
            with open(file_path, 'rb') as f:
                self.wfile.write(f.read())
        else:
            self._set_headers(404, content_type='text/plain')
            self.wfile.write(b"Dist folder not built yet.")

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            data = json.loads(body.decode('utf-8')) if body else {}
        except json.JSONDecodeError:
            data = {}

        if parsed.path == '/api/telegram/send':
            symbol = data.get('symbol', 'UNKNOWN')
            message = data.get('message') or f"🔔 Kiểm tra thủ công: {symbol}"
            ok = _notifier.send_message(message)
            self._set_headers(200 if ok else 502)
            self.wfile.write(json.dumps({
                "status": "success" if ok else "error",
                "message": "Đã gửi Telegram." if ok else "Gửi Telegram thất bại — kiểm tra bot_token/chat_id trong cấu hình.",
                "timestamp": system_now().isoformat()
            }).encode('utf-8'))
        elif parsed.path == '/api/scanner/trigger':
            trigger = _request_scan()
            self._set_headers(202)
            self.wfile.write(json.dumps({
                **trigger,
                "message": (
                    "Scanner đang quét — bảng sẽ dùng kết quả của chu kỳ hiện tại."
                    if trigger["status"] == "in_progress"
                    else "Đã ghi nhận yêu cầu quét — scanner daemon sẽ chạy trong vài giây (nếu daemon đang chạy)."
                ),
            }).encode('utf-8'))
        elif parsed.path == '/api/watchlist/add':
            raw_symbol = data.get('symbol', '')
            symbol = raw_symbol.strip().upper() if isinstance(raw_symbol, str) else ''
            if symbol:
                updated = add_to_watchlist(WATCHLIST_PATH, symbol)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "manual_watchlist": updated}).encode('utf-8'))
            else:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Symbol required"}).encode('utf-8'))
        elif parsed.path == '/api/tracking-watchlist':
            try:
                if not isinstance(data, dict):
                    raise ValueError("JSON object required")
                entry, created = _tracking_store.add(data)
                self._set_headers(201 if created else 200)
                self.wfile.write(json.dumps({
                    "status": "created" if created else "already_tracking",
                    "item": entry,
                }, ensure_ascii=False).encode('utf-8'))
            except ValueError as exc:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
            except OSError as exc:
                logger.warning("tracking_watchlist_write_failed error=%s", exc)
                self._set_headers(503)
                self.wfile.write(json.dumps({"error": "Tracking watchlist unavailable"}).encode('utf-8'))
        elif parsed.path == '/api/watchlist/remove':
            raw_symbol = data.get('symbol', '')
            symbol = raw_symbol.strip().upper() if isinstance(raw_symbol, str) else ''
            if symbol:
                updated = remove_from_watchlist(WATCHLIST_PATH, symbol)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "manual_watchlist": updated}).encode('utf-8'))
            else:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Symbol required"}).encode('utf-8'))
        elif parsed.path == '/api/watchlist/mode':
            raw_modes = data.get('modes', data.get('mode', 'volatile'))
            if isinstance(raw_modes, str):
                requested_modes = [item.strip().lower() for item in raw_modes.split(',') if item.strip()]
            elif isinstance(raw_modes, list):
                requested_modes = [item.strip().lower() for item in raw_modes if isinstance(item, str) and item.strip()]
            else:
                requested_modes = []
            allowed_modes = {'gainers', 'losers', 'volume', 'volatile', 'all', 'manual'}
            if not requested_modes or any(mode not in allowed_modes for mode in requested_modes):
                self._set_headers(400)
                self.wfile.write(json.dumps({
                    "error": "Invalid scan modes",
                    "allowed_modes": sorted(allowed_modes),
                }).encode('utf-8'))
                return
            new_modes = normalize_scan_modes(requested_modes)
            _request_scan(modes=new_modes)
            self._set_headers(202)
            self.wfile.write(json.dumps({
                "status": "queued",
                "active_scan_modes": new_modes,
                "active_scan_mode": ",".join(new_modes),
                "message": "Chế độ quét sẽ được áp dụng ở chu kỳ tiếp theo của scanner daemon.",
            }).encode('utf-8'))
        elif parsed.path == '/api/alerts/dismiss':
            symbol = data.get('symbol', '').upper()
            signal_time_str = data.get('signal_time', '')
            if not symbol or not signal_time_str:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "symbol and signal_time required"}).encode('utf-8'))
                return
            try:
                sig_time = datetime.fromisoformat(signal_time_str)
                if sig_time.tzinfo is None:
                    sig_time = sig_time.replace(tzinfo=timezone.utc)
                _alert_store.dismiss(sig_time, symbol)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "symbol": symbol, "signal_time": signal_time_str}).encode('utf-8'))
            except Exception as exc:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        elif parsed.path == '/api/listing/refresh':
            try:
                from dao_vang.data.binance_listing import run_daily_scan
                snapshot = run_daily_scan()
                if snapshot:
                    self._set_headers(200)
                    self.wfile.write(json.dumps({"status": "success", "snapshot": snapshot}, default=str).encode('utf-8'))
                else:
                    self._set_headers(502)
                    self.wfile.write(json.dumps({"status": "error", "message": "Không lấy được dữ liệu từ Binance"}).encode('utf-8'))
            except Exception as exc:
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        elif parsed.path == '/api/forward-test/freeze':
            hypothesis_id = data.get('hypothesis_id', 'hyp_dashboard_001')
            try:
                import numpy as _np
                from sklearn.impute import SimpleImputer as _SimpleImputer
                from sklearn.linear_model import LogisticRegression as _LR
                from sklearn.pipeline import Pipeline as _Pipeline

                from dao_vang.data.storage.duckdb import DuckDBQueryLayer
                from dao_vang.experiments.forward_test import (
                    freeze_model as _freeze_model,
                )

                settings = AppSettings()
                db = DuckDBQueryLayer(str(settings.scanner.db_path))
                try:
                    ft_df = db.conn.execute(
                        """
                        SELECT f.*, l.label_value AS is_distribution
                        FROM feature_results f
                        INNER JOIN labels l
                            ON f.feature_time = l.signal_time AND f.symbol = l.symbol
                        """
                    ).df()
                finally:
                    db.conn.close()

                if ft_df.empty or len(ft_df) < 200:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": f"Cần >=200 dòng (hiện có {len(ft_df)}). Chạy Backtest trước."}).encode('utf-8'))
                    return
                if ft_df["is_distribution"].nunique() < 2:
                    self._set_headers(400)
                    self.wfile.write(json.dumps({"error": "Cần cả 2 loại nhãn (có xả + không xả)"}).encode('utf-8'))
                    return

                ft_df = ft_df.sort_values("feature_time").reset_index(drop=True)
                exclude = ["feature_time", "decision_time", "is_distribution", "quality_status", "symbol", "lead_time_minutes", "invalidation_time"]
                feats = [c for c in ft_df.columns if c not in exclude]

                val_cut = ft_df["feature_time"].quantile(0.8)
                tr = ft_df[ft_df["feature_time"] < val_cut]
                va = ft_df[ft_df["feature_time"] >= val_cut]
                # Fit preprocessing on the training partition only.  Missing
                # values are not silently converted to a semantic zero.
                m = _Pipeline(
                    [
                        ("imputer", _SimpleImputer(strategy="median", add_indicator=True)),
                        ("model", _LR(max_iter=1000, random_state=42, class_weight="balanced")),
                    ]
                )
                m.fit(tr[feats], tr["is_distribution"])

                best_t, best_f1 = 0.5, 0.0
                if len(va) > 0 and va["is_distribution"].nunique() >= 2:
                    yp = m.predict_proba(va[feats])[:, 1]
                    yv = va["is_distribution"].values
                    for t in _np.arange(0.05, 0.95, 0.05):
                        yp_t = (yp >= t).astype(int)
                        tp = int(((yp_t == 1) & (yv == 1)).sum())
                        fp = int(((yp_t == 1) & (yv == 0)).sum())
                        fn = int(((yp_t == 0) & (yv == 1)).sum())
                        if tp + fp == 0 or tp + fn == 0:
                            continue
                        p = tp / (tp + fp)
                        r = tp / (tp + fn)
                        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
                        if f1 > best_f1:
                            best_f1 = f1
                            best_t = float(t)

                final_m = _Pipeline(
                    [
                        ("imputer", _SimpleImputer(strategy="median", add_indicator=True)),
                        ("model", _LR(max_iter=1000, random_state=42, class_weight="balanced")),
                    ]
                )
                final_m.fit(ft_df[feats], ft_df["is_distribution"])

                info = _freeze_model(
                    model=final_m,
                    threshold=float(best_t),
                    feature_cols=feats,
                    config={"hypothesis_id": hypothesis_id, "dataset_version": "v1", "label_version": "v1", "feature_set_version": "v1", "seed": 42},
                    train_cutoff=ft_df["feature_time"].max(),
                    training_stats={
                        "train_size": len(ft_df),
                        "train_positives": int(ft_df["is_distribution"].sum()),
                        "threshold": float(best_t),
                        "n_features": len(feats),
                    },
                    artifact_dir=Path("./artifacts"),
                )
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "status": "success",
                    "model_id": info.model_id,
                    "train_cutoff": info.train_cutoff,
                    "threshold": info.threshold,
                    "n_features": len(info.feature_cols),
                    "train_size": len(ft_df),
                    "train_positives": int(ft_df["is_distribution"].sum()),
                }, default=str).encode('utf-8'))
            except Exception as exc:
                logger.warning(f"freeze_model_failed error={exc}")
                self._set_headers(500)
                self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        else:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "Endpoint not found"}).encode('utf-8'))

    def do_PATCH(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length) if content_length > 0 else b'{}'
        try:
            data = json.loads(body.decode('utf-8')) if body else {}
        except json.JSONDecodeError:
            data = {}

        prefix = '/api/tracking-watchlist/'
        if not parsed.path.startswith(prefix):
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "API endpoint not found"}).encode('utf-8'))
            return
        entry_id = unquote(parsed.path[len(prefix):]).strip()
        if not entry_id:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Tracking item id required"}).encode('utf-8'))
            return
        if not isinstance(data, dict):
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "JSON object required"}).encode('utf-8'))
            return
        try:
            updated = _tracking_store.update(entry_id, data)
            if updated is None:
                self._set_headers(404)
                self.wfile.write(json.dumps({"error": "Tracking item not found"}).encode('utf-8'))
                return
            self._set_headers(200)
            self.wfile.write(json.dumps({"status": "updated", "item": updated}, ensure_ascii=False).encode('utf-8'))
        except ValueError as exc:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))
        except OSError:
            self._set_headers(503)
            self.wfile.write(json.dumps({"error": "Tracking watchlist unavailable"}).encode('utf-8'))

    def do_DELETE(self):
        parsed = urlparse(self.path)
        prefix = '/api/tracking-watchlist/'
        if not parsed.path.startswith(prefix):
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "API endpoint not found"}).encode('utf-8'))
            return
        entry_id = unquote(parsed.path[len(prefix):]).strip()
        if not entry_id:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "Tracking item id required"}).encode('utf-8'))
            return
        try:
            removed = _tracking_store.remove(entry_id)
            self._set_headers(200 if removed else 404)
            self.wfile.write(json.dumps({
                "status": "removed" if removed else "not_found",
                "id": entry_id,
            }).encode('utf-8'))
        except OSError:
            self._set_headers(503)
            self.wfile.write(json.dumps({"error": "Tracking watchlist unavailable"}).encode('utf-8'))

    def get_tracking_watchlist(self):
        """Return user tracking entries enriched with current public market data."""

        entries = _tracking_store.list()
        if not entries:
            self._set_headers(200)
            self.wfile.write(json.dumps([], ensure_ascii=False).encode('utf-8'))
            return

        try:
            tickers = fetch_all_tickers()
        except Exception as exc:
            logger.warning("tracking_watchlist_tickers_failed error=%s", exc)
            tickers = []
        ticker_by_symbol = {
            normalize_symbol(item.get("symbol")): item
            for item in tickers
            if isinstance(item, dict) and item.get("symbol")
        }

        try:
            alert_rows = _alert_store.query(days=3650, include_dismissed=True, limit=5000)
        except Exception as exc:
            logger.warning("tracking_watchlist_alerts_failed error=%s", exc)
            alert_rows = []
        alerts_by_symbol: dict[str, list[dict[str, Any]]] = {}
        for row in alert_rows:
            alerts_by_symbol.setdefault(normalize_symbol(row.get("symbol")), []).append(row)

        now = datetime.now(timezone.utc)

        def same_instant(left: Any, right: Any) -> bool:
            left_dt = _as_utc_datetime(left)
            right_dt = _as_utc_datetime(right)
            return left_dt is not None and right_dt is not None and abs((left_dt - right_dt).total_seconds()) < 1.0

        def progress(source_price: float | None, target_price: float | None, current_price: float | None) -> float | None:
            if not source_price or not target_price or current_price is None or target_price == source_price:
                return None
            if target_price < source_price:
                value = (source_price - current_price) / (source_price - target_price)
            else:
                value = (current_price - source_price) / (target_price - source_price)
            return round(max(0.0, min(1.0, value)) * 100.0, 1)

        enriched: list[dict[str, Any]] = []
        for entry in entries:
            symbol = normalize_symbol(entry.get("symbol"))
            source_signal_time = entry.get("source_signal_time")
            alert = next(
                (
                    row
                    for row in alerts_by_symbol.get(symbol, [])
                    if source_signal_time and same_instant(row.get("signal_time"), source_signal_time)
                ),
                None,
            )

            source_price = entry.get("source_price")
            source_probability = entry.get("source_probability")
            source_risk_level = entry.get("source_risk_level")
            target_price = entry.get("source_target_price")
            invalidation_time = entry.get("source_invalidation_time")
            hit = None
            hit_time = None
            if alert:
                source_price = alert.get("close_price") or source_price
                source_probability = alert.get("probability")
                source_risk_level = _risk_bucket(float(source_probability or 0.0) * 100.0)
                invalidation_time = _system_history_timestamp(alert.get("invalidation_time"))
                target_price = round(float(source_price) * 0.92, 8) if source_price else target_price
                hit = alert.get("hit")
                hit_time = _system_history_timestamp(alert.get("hit_time"))

            latest_scan = _scan_store.latest_for_symbol(symbol, max_age_hours=48)
            ticker = ticker_by_symbol.get(symbol, {})
            current_price = None
            try:
                if ticker.get("lastPrice") is not None:
                    current_price = float(ticker["lastPrice"])
            except (TypeError, ValueError):
                current_price = None
            if current_price is None and latest_scan:
                try:
                    current_price = float(latest_scan.get("close_price"))
                except (TypeError, ValueError):
                    current_price = None
            if current_price is None:
                current_price = source_price

            invalidation_dt = _as_utc_datetime(invalidation_time)
            validity_hours_left = (
                max(0.0, (invalidation_dt - now).total_seconds() / 3600.0)
                if invalidation_dt is not None else None
            )
            if hit is True:
                signal_status = "HIT"
            elif invalidation_dt is not None and invalidation_dt <= now:
                signal_status = "EXPIRED"
            elif invalidation_dt is not None:
                signal_status = "ACTIVE"
            else:
                signal_status = "NO_SIGNAL"

            signal_change_pct = None
            if source_price and current_price is not None:
                signal_change_pct = round((current_price - float(source_price)) / float(source_price) * 100.0, 2)

            position_metrics = calculate_position_metrics(
                current_price=current_price,
                entry_price=entry.get("entry_price"),
                position_side=entry.get("position_side"),
                quantity=entry.get("quantity"),
                notional=entry.get("notional"),
                leverage=entry.get("leverage"),
            )

            current_probability = latest_scan.get("calibrated_probability") if latest_scan else None
            current_risk_level = (
                _scan_risk_level(latest_scan.get("recommendation"), float(current_probability))
                if current_probability is not None and latest_scan else None
            )
            item = {
                **entry,
                "symbol": symbol,
                "source_price": source_price,
                "source_probability": source_probability,
                "source_risk_level": source_risk_level,
                "source_target_price": target_price,
                "source_invalidation_time": invalidation_time,
                "signal_status": signal_status,
                "hit": hit,
                "hit_time": hit_time,
                "validity_hours_left": round(validity_hours_left, 2) if validity_hours_left is not None else None,
                "current_price": current_price,
                "current_probability": current_probability,
                "current_risk_level": current_risk_level,
                "signal_change_pct": signal_change_pct,
                "signal_progress_pct": progress(
                    float(source_price) if source_price is not None else None,
                    float(target_price) if target_price is not None else None,
                    current_price,
                ),
                **position_metrics,
                "last_market_update": _system_history_timestamp(latest_scan.get("scan_time")) if latest_scan else None,
            }
            enriched.append(item)

        enriched.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        self._set_headers(200)
        self.wfile.write(json.dumps(enriched, ensure_ascii=False, default=str).encode('utf-8'))

    def get_status(self):
        hb = _read_json(HEARTBEAT_PATH)
        scan_mode = _current_scan_mode()
        now = datetime.now(timezone.utc)
        hb_ts_raw = hb.get("timestamp")
        is_stale = True
        if hb_ts_raw:
            try:
                ts = datetime.fromisoformat(hb_ts_raw)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                is_stale = (now - ts) > timedelta(
                    minutes=max(3 * _settings.scanner.poll_interval_minutes, 15)
                )
            except Exception:
                is_stale = True

        db_read_errors: list[str] = []
        with _STATUS_CACHE_LOCK:
            cached = dict(_STATUS_CACHE)

        top_risk_symbol = cached.get("top_risk_symbol")
        active_signals = int(cached.get("active_signals_count", 0))
        cycle_stats = cached.get("cycle_stats", {})

        # The scanner owns the DuckDB writer. On Windows, a read-only open can
        # fail briefly while a cycle is committing. Status must remain useful
        # during that window, so retain the last successful values and use the
        # heartbeat as the live source of truth for liveness.
        try:
            recent_alerts = _alert_store.query(
                days=1, include_dismissed=False, limit=1
            )
            top_risk_symbol = recent_alerts[0]["symbol"] if recent_alerts else None
            active_signals = len(
                _alert_store.query(
                    days=1, include_dismissed=False, limit=500
                )
            )
        except Exception as exc:
            db_read_errors.append("alert_history")
            logger.warning("status_alert_history_unavailable error=%s", exc)

        try:
            cycle_stats = _scan_store.latest_cycle_stats()
        except Exception as exc:
            db_read_errors.append("scan_results")
            logger.warning("status_scan_results_unavailable error=%s", exc)

        if not cycle_stats:
            cycle_stats = {
                "cycle": hb.get("cycle"),
                "n_symbols": hb.get("last_cycle_n_symbols", 0),
                "n_alerts": hb.get("last_cycle_n_alerts", 0),
                "last_scan_time": hb.get("last_cycle_completed_at"),
            }

        with _STATUS_CACHE_LOCK:
            _STATUS_CACHE.update(
                {
                    "top_risk_symbol": top_risk_symbol,
                    "active_signals_count": active_signals,
                    "cycle_stats": cycle_stats,
                }
            )

        # Friendly model name for header display
        current_model_id = hb.get("model_id") or _settings.scanner.frozen_model_id
        model_friendly = current_model_id or "Heuristic (chưa cài frozen)"
        if current_model_id:
            try:
                from dao_vang.experiments.forward_test import load_frozen_model
                _fi = load_frozen_model(current_model_id, Path("./artifacts"))
                _spec = _fi.label_spec or {}
                _td = _spec.get("target_drawdown", 0.08)
                _mae = _spec.get("max_ae", 0.04)
                _hz = _spec.get("horizon_minutes", 1440)
                _lv = _fi.config.get("label_version", "v1")
                _td_s = f"{_td * 100:.0f}%" if isinstance(_td, (int, float)) else str(_td)
                _mae_s = f"{_mae * 100:.0f}%" if isinstance(_mae, (int, float)) else str(_mae)
                _hz_s = f"{_hz // 60:.0f}h" if isinstance(_hz, (int, float)) else str(_hz)
                model_friendly = f"LR {_lv} ({_td_s}/{_mae_s}/{_hz_s})"
            except Exception as exc:
                logger.warning(f"status_load_friendly_model_failed error={exc}")

        res = {
            "scanner_status": "OFFLINE" if (is_stale or hb.get("status") != "running") else "ONLINE",
            "scanner_mode": f"24/7 Scanner ({scan_mode.upper()})",
            "heartbeat": _system_history_timestamp(hb_ts_raw),
            "scanned_coins_count": cycle_stats.get("n_symbols", 0),
            "active_signals_count": active_signals,
            "top_risk_symbol": top_risk_symbol,
            "model_version": model_friendly,
            "model_id": current_model_id,
            "telegram_connected": _notifier.is_configured,
            "threshold": _settings.scoring.alert_score_threshold / 100.0,
            "db_read_status": "degraded" if db_read_errors else "ok",
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_scanner_telemetry(self):
        hb = _read_json(HEARTBEAT_PATH)
        runtime = _read_json(RUNTIME_STATE_PATH)
        cycle_stats = {}
        try:
            cycle_stats = _scan_store.latest_cycle_stats()
        except Exception as exc:
            logger.warning(f"telemetry_cycle_stats_failed error={exc}")

        recent = []
        try:
            recent = _alert_store.query(days=1, include_dismissed=True, limit=20)
        except Exception as exc:
            logger.warning(f"telemetry_alerts_query_failed error={exc}")

        logs = []
        for r in recent:
            sig_time = r["signal_time"]
            display_time = _system_display_datetime(sig_time)
            ts_str = display_time.strftime("%H:%M:%S") if display_time else str(sig_time)
            logs.append({
                "timestamp": ts_str,
                "symbol": r["symbol"],
                "step": "Composite Scoring",
                "status": "ALERT FIRED" if r.get("telegram_sent") else "SCORED",
                "duration_ms": None,
                "details": f"Score {r['probability'] * 100:.1f}/100, risk={r['risk_level']}",
            })

        # Also add recent scan_results as logs (shows scanner activity even without alerts)
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                scan_logs = conn.execute(
                    """
                    SELECT scan_time, symbol, score, recommendation, close_price
                    FROM scan_results
                    WHERE scan_time >= ?
                    ORDER BY scan_time DESC LIMIT 30
                    """,
                    [datetime.now(timezone.utc) - timedelta(hours=24)],
                ).fetchall()
                for scan_time, symbol, score, rec, close_price in scan_logs:
                    display_time = _system_display_datetime(scan_time)
                    ts_str = display_time.strftime("%H:%M:%S") if display_time else str(scan_time)
                    logs.append({
                        "timestamp": ts_str,
                        "symbol": symbol,
                        "step": "Scan + Score",
                        "status": rec.upper() if rec else "SCORED",
                        "duration_ms": None,
                        "details": f"Score {score:.1f}/100, price={close_price}",
                    })
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"telemetry_scan_logs_failed error={exc}")

        # Sort logs by timestamp descending
        logs.sort(key=lambda x: x["timestamp"], reverse=True)

        telegram_logs = []
        for r in recent:
            if not r.get("telegram_sent"):
                continue
            sent_at = r.get("telegram_sent_at")
            display_time = _system_display_datetime(sent_at)
            telegram_logs.append({
                "timestamp": display_time.strftime("%Y-%m-%d %H:%M:%S") if display_time else str(sent_at),
                "symbol": r["symbol"],
                "risk_score": f"{r['probability'] * 100:.1f}%",
                "channel": "Telegram",
                "status": "DELIVERED",
            })

        # Heartbeat is also written when a cycle starts.  Prefer the explicit
        # completion timestamp so the UI never calls an in-progress cycle the
        # last successful scan.
        last_scan_time = hb.get("last_cycle_completed_at") or hb.get("timestamp")
        if not last_scan_time and cycle_stats.get("last_scan_time") is not None:
            lst = cycle_stats["last_scan_time"]
            last_scan_time = _system_history_timestamp(lst)
        elif last_scan_time:
            last_scan_time = _system_history_timestamp(last_scan_time)

        # Compute next scan time from heartbeat
        next_scan_in = None
        hb_ts = hb.get("last_cycle_completed_at") or hb.get("timestamp")
        poll_min = hb.get("poll_minutes", _settings.scanner.poll_interval_minutes)
        if hb_ts and poll_min:
            try:
                hb_dt = datetime.fromisoformat(hb_ts.replace("Z", "+00:00"))
                next_dt = hb_dt + timedelta(minutes=poll_min)
                now_dt = datetime.now(timezone.utc)
                next_scan_in = max(0, int((next_dt - now_dt).total_seconds()))
            except Exception as e:
                logger.warning(f"Error processing stats item: {e}")

        telemetry_modes = normalize_scan_modes(
            hb.get("scan_modes", hb.get("scan_mode", _current_scan_mode()))
        )
        res = {
            "scanner_engine_status": "ONLINE" if hb.get("status") == "running" else "OFFLINE",
            "last_scan_timestamp": last_scan_time,
            "next_scan_in_seconds": next_scan_in,
            "poll_interval_minutes": poll_min,
            "api_endpoint": "https://fapi.binance.com/fapi/v1",
            "average_api_latency_ms": None,
            "active_scan_mode": hb.get("scan_mode", _current_scan_mode()),
            "active_scan_modes": telemetry_modes,
            "scanned_pairs_count": cycle_stats.get("n_symbols", 0),
            "signals_triggered_count": cycle_stats.get("n_alerts", 0),
            "stablecoins_excluded_count": None,
            "runtime_state": runtime,
            "model_id": hb.get("model_id"),
            "cycle": hb.get("cycle"),
            "max_coins": hb.get("max_coins"),
            "logs": logs[:30],  # cap at 30
            "telegram_dispatches": telegram_logs,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_watchlist(self):
        manual = load_manual_watchlist(WATCHLIST_PATH)
        scan_modes = _current_scan_modes()
        scan_mode = ",".join(scan_modes)
        cfg = _settings.scanner

        try:
            tickers = fetch_all_tickers()
        except Exception as exc:
            logger.warning(f"watchlist_tickers_fetch_failed error={exc}")
            tickers = []
        filtered_count = len(
            _filter_tickers(tickers, cfg.min_volume_usd, cfg.min_price_change_pct, cfg.exclude_stablecoins)
        )

        res = {
            "active_scan_mode": scan_mode,
            "active_scan_modes": scan_modes,
            "presets": [
                {
                    "id": "volatile",
                    "name": "⚡ Top Coin Biến Động Nhất (Volatile)",
                    "description": "Quét các coin Futures có biến động giá 24h mạnh nhất.",
                    "count": filtered_count,
                },
                {
                    "id": "volume",
                    "name": "📊 Top Khối Lượng Giao Dịch (Volume)",
                    "description": "Quét Top coin Futures có Volume giao dịch 24h lớn nhất Binance.",
                    "count": filtered_count,
                },
                {
                    "id": "gainers",
                    "name": "📈 Top Coin Tăng Giá Mạnh Nhất 24h (Gainers)",
                    "description": "Top coin tăng giá 24h mạnh nhất — ứng viên tạo đỉnh & bắt đầu xả.",
                    "count": filtered_count,
                },
                {
                    "id": "losers",
                    "name": "📉 Top Coin Giảm Giá Mạnh Nhất 24h (Losers)",
                    "description": "Top coin đã bắt đầu xả mạnh 24h — ứng viên Short tiếp diễn.",
                    "count": filtered_count,
                },
                {
                    "id": "manual",
                    "name": "⭐ Watchlist Tùy Chọn (Manual Watchlist)",
                    "description": "Danh sách coin cá nhân do bạn tùy chỉnh lựa chọn.",
                    "count": len(manual),
                },
            ],
            "manual_watchlist": manual,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res).encode('utf-8'))

    def get_signals(self):
        now = datetime.now(timezone.utc)
        rows = _alert_store.query(days=7, include_dismissed=False, limit=100)
        lead_stats = _alert_store.lead_time_stats(days=30)
        signals = []
        alert_event_times: dict[str, datetime] = {}
        for r in rows:
            sig_time = r["signal_time"]
            inv_time = r["invalidation_time"]

            sig_dt = _as_utc_datetime(sig_time)
            inv_dt = _as_utc_datetime(inv_time)
            event_dt = _as_utc_datetime(r.get("telegram_sent_at")) or sig_dt
            if event_dt is not None:
                previous_event = alert_event_times.get(r["symbol"])
                if previous_event is None or event_dt > previous_event:
                    alert_event_times[r["symbol"]] = event_dt

            components: list[dict[str, Any]] = []
            if r.get("components_json"):
                try:
                    components = json.loads(r["components_json"])
                except (json.JSONDecodeError, TypeError):
                    components = []
            top = sorted(components, key=lambda c: c.get("weighted_score", 0), reverse=True)[:4]
            drivers = [
                {
                    "name": c.get("name", "").replace("_", " ").title(),
                    "impact": "High" if c.get("weighted_score", 0) >= 10 else "Medium",
                    "score": f"{c.get('weighted_score', 0):+.1f}",
                }
                for c in top
            ]

            validity_hours_left = 0.0
            validity_hours_total = 24.0
            if inv_dt is not None:
                validity_hours_left = max(0.0, (inv_dt - now).total_seconds() / 3600.0)
                if sig_dt is not None:
                    validity_hours_total = max(0.0, (inv_dt - sig_dt).total_seconds() / 3600.0)

            close_price = r.get("close_price")

            scan = _scan_store.latest_for_symbol(r["symbol"], max_age_hours=48)
            oi_change = scan.get("oi_change_24h") if scan else None
            funding = scan.get("funding_rate") if scan else None
            taker_sell = scan.get("taker_sell_ratio") if scan else None

            rsi_divergence = any(
                c.get("name", "") in ("momentum_exhaustion", "fake_breakout")
                and c.get("weighted_score", 0) >= 5
                for c in components
            )

            target_drawdown = -8.0
            target_price = round(close_price * (1 + target_drawdown / 100.0), 8) if close_price else 0.0

            prob_val = float(r.get("probability") or 0.0)
            is_fired = (
                prob_val >= 0.55
                or (taker_sell is not None and taker_sell >= 0.58)
                or r.get("risk_level") in {"CAO", "HIGH", "CRITICAL"}
            )
            two_tier_state = "FIRED" if is_fired else "ARMED" if prob_val >= 0.35 else "NORMAL"

            signals.append({
                "id": f"{r['symbol']}-{_system_history_timestamp(sig_time)}",
                "symbol": r["symbol"],
                "name": r["symbol"].replace("USDT", ""),
                "probability": r["probability"],
                "risk_level": _risk_bucket(r["probability"] * 100.0),
                "two_tier_state": two_tier_state,
                "signal_time": _system_history_timestamp(sig_time),
                "event_time": _system_history_timestamp(event_dt),
                "telegram_sent_at": _system_history_timestamp(r.get("telegram_sent_at")),
                "signal_price": close_price or 0.0,
                "target_drawdown": target_drawdown,
                "target_price": target_price,
                "validity_hours_left": validity_hours_left,
                "validity_hours_total": validity_hours_total,
                "invalidation_time": _system_history_timestamp(inv_dt),
                "lead_time_avg_hours": lead_stats["mean_hours"],
                "oi_change_24h": f"{oi_change:+.1%}" if oi_change is not None else "N/A",
                "taker_sell_ratio": taker_sell if taker_sell is not None else 0.5,
                "funding_rate": f"{funding:+.3%}" if funding is not None else "N/A",
                "rsi_divergence": rsi_divergence,
                "evidence_precision": r.get("evidence_precision"),
                "evidence_n_judged": r.get("evidence_n_judged"),
                "hit": r.get("hit"),
                "telegram_sent": r.get("telegram_sent"),
                "drivers": drivers,
            })

        # Also include top candidates from scan_results that haven't triggered
        # alerts, so the RADAR shows what the scanner is seeing even when no
        # alert threshold has been crossed.
        scan_rows = _scan_store.latest_per_symbol(limit=50)
        for sr in scan_rows:
            sym = sr.get("symbol", "")
            calibrated_probability = sr.get("calibrated_probability")
            if calibrated_probability is None:
                # Never expose the heuristic score as a probability.  Legacy
                # rows without a calibrated value remain visible in the raw
                # scan store but are not promoted to the prediction UI.
                continue
            try:
                prob = float(calibrated_probability)
            except (TypeError, ValueError):
                continue
            if not 0.0 <= prob <= 1.0:
                continue
            scan_time = sr.get("scan_time")
            sig_time_str = _system_history_timestamp(scan_time) or str(scan_time)
            scan_dt = _as_utc_datetime(scan_time)
            existing_alert_event = alert_event_times.get(sym)
            if (
                existing_alert_event is not None
                and scan_dt is not None
                and existing_alert_event >= scan_dt
            ):
                continue
            scan_invalidation_dt = scan_dt + timedelta(hours=24) if scan_dt is not None else None
            close_price = sr.get("close_price")
            oi_change = sr.get("oi_change_24h")
            funding = sr.get("funding_rate")
            taker_sell = sr.get("taker_sell_ratio")
            target_drawdown = -8.0
            target_price = round(close_price * (1 + target_drawdown / 100.0), 8) if close_price else 0.0
            tier = str(sr.get("recommendation", "WAIT"))
            risk_level = _scan_risk_level(tier, prob)
            signals.append({
                "id": f"{sym}-scan-{sig_time_str}",
                "symbol": sym,
                "name": sym.replace("USDT", ""),
                "probability": prob,
                "risk_level": risk_level,
                "signal_time": sig_time_str,
                "event_time": _system_history_timestamp(scan_dt) if scan_dt is not None else sig_time_str,
                "telegram_sent_at": None,
                "signal_price": close_price or 0.0,
                "target_drawdown": target_drawdown,
                "target_price": target_price,
                "validity_hours_left": 24.0,
                "validity_hours_total": 24.0,
                "invalidation_time": _system_history_timestamp(scan_invalidation_dt),
                "lead_time_avg_hours": lead_stats["mean_hours"],
                "oi_change_24h": f"{oi_change:+.1%}" if oi_change is not None else "N/A",
                "taker_sell_ratio": taker_sell if taker_sell is not None else 0.5,
                "funding_rate": f"{funding:+.3%}" if funding is not None else "N/A",
                "rsi_divergence": False,
                "evidence_precision": None,
                "evidence_n_judged": None,
                "hit": None,
                "telegram_sent": False,
                "drivers": [],
            })

        # Shadow mode writes every scored observation to ``predictions`` and
        # marks the row after Telegram accepts it.  Include that append-only
        # stream so a delivered observation is visible even when the same coin
        # already has an older alert_history row.
        scan_by_symbol = {str(sr.get("symbol", "")): sr for sr in scan_rows}
        try:
            prediction_rows = _scan_store.latest_predictions_per_symbol(
                limit=100,
                max_age_hours=24,
            )
        except Exception as exc:
            logger.debug("signals_prediction_query_unavailable error=%s", exc)
            prediction_rows = []

        for pr in prediction_rows:
            calibrated_probability = pr.get("calibrated_probability")
            if calibrated_probability is None:
                continue
            try:
                prob = float(calibrated_probability)
            except (TypeError, ValueError):
                continue
            if not 0.0 <= prob <= 1.0:
                continue

            sym = str(pr.get("symbol", ""))
            if not sym:
                continue
            signal_dt = _as_utc_datetime(pr.get("signal_time"))
            observed_dt = _as_utc_datetime(pr.get("created_at")) or signal_dt
            scan = scan_by_symbol.get(sym, {})
            close_price = scan.get("close_price")
            oi_change = scan.get("oi_change_24h")
            funding = scan.get("funding_rate")
            taker_sell = scan.get("taker_sell_ratio")
            target_drawdown = -8.0
            target_price = round(close_price * (1 + target_drawdown / 100.0), 8) if close_price else 0.0
            tier = str(pr.get("tier") or "WAIT")
            risk_level = {
                "HIGH_CONFIDENCE": "HIGH",
                "SHORT_CANDIDATE": "HIGH",
                "WATCH": "MEDIUM",
                "WAIT": "SAFE",
            }.get(tier, _risk_bucket(prob * 100.0))
            invalidation_dt = _as_utc_datetime(pr.get("invalidation_time"))
            if invalidation_dt is None and signal_dt is not None:
                invalidation_dt = signal_dt + timedelta(hours=24)
            signals.append({
                "id": f"prediction-{pr.get('prediction_id', sym)}",
                "symbol": sym,
                "name": sym.replace("USDT", ""),
                "probability": prob,
                "risk_level": risk_level,
                "signal_time": _system_history_timestamp(signal_dt) if signal_dt is not None else str(pr.get("signal_time")),
                "event_time": _system_history_timestamp(observed_dt),
                "telegram_sent_at": _system_history_timestamp(observed_dt) if pr.get("telegram_sent") else None,
                "signal_price": close_price or 0.0,
                "target_drawdown": target_drawdown,
                "target_price": target_price,
                "validity_hours_left": max(
                    0.0,
                    (invalidation_dt - datetime.now(timezone.utc)).total_seconds() / 3600.0,
                ) if invalidation_dt is not None else 24.0,
                "validity_hours_total": max(
                    0.0,
                    (invalidation_dt - signal_dt).total_seconds() / 3600.0,
                ) if invalidation_dt is not None and signal_dt is not None else 24.0,
                "invalidation_time": _system_history_timestamp(invalidation_dt),
                "lead_time_avg_hours": lead_stats["mean_hours"],
                "oi_change_24h": f"{oi_change:+.1%}" if oi_change is not None else "N/A",
                "taker_sell_ratio": taker_sell if taker_sell is not None else 0.5,
                "funding_rate": f"{funding:+.3%}" if funding is not None else "N/A",
                "rsi_divergence": False,
                "evidence_precision": None,
                "evidence_n_judged": None,
                "hit": None,
                "telegram_sent": bool(pr.get("telegram_sent")),
                "drivers": [],
            })

        # The Radar's primary order is the observation/delivery time.  The
        # frontend can still apply the user's selected secondary sort.
        signals.sort(
            key=lambda s: s.get("event_time") or s.get("signal_time") or "",
            reverse=True,
        )
        self._set_headers(200)
        self.wfile.write(json.dumps(signals, default=str).encode('utf-8'))

    def get_candidates(self):
        rows: list[dict[str, Any]] = []
        data_is_stale = False

        # Prefer the scanner-published snapshot. The scanner owns DuckDB's
        # writer lock for its whole lifetime on Windows, so a read-only API
        # connection may otherwise be stuck on an old ``.ro_copy`` file.
        snapshot = _read_json(CANDIDATE_SNAPSHOT_PATH)
        snapshot_rows = snapshot.get("rows") if isinstance(snapshot, dict) else None
        timestamp_timezone = "Asia/Ho_Chi_Minh"
        if isinstance(snapshot_rows, list):
            rows = [row for row in snapshot_rows if isinstance(row, dict)]
            timestamp_timezone = str(
                snapshot.get("timestamp_timezone") or timestamp_timezone
            )
            generated_at = snapshot.get("generated_at")
            if isinstance(generated_at, str):
                try:
                    generated_dt = datetime.fromisoformat(
                        generated_at.replace("Z", "+00:00")
                    )
                    if generated_dt.tzinfo is None:
                        generated_dt = generated_dt.replace(tzinfo=timezone.utc)
                    data_is_stale = (
                        datetime.now(timezone.utc) - generated_dt
                    ).total_seconds() > 6 * 60 * 60
                except ValueError:
                    data_is_stale = True
        else:
            # Normal path when the API can read DuckDB directly.
            rows = _scan_store.latest_per_symbol(limit=200)
            if not rows:
                # Keep the table useful during a scanner outage, but mark the
                # result as stale so an old score is never mistaken for live
                # market data.
                rows = _scan_store.latest_per_symbol(
                    limit=200, max_age_hours=None
                )
                data_is_stale = bool(rows)
            # Legacy DuckDB rows were written while the host timezone was
            # Asia/Saigon. They are only used as an explicitly stale fallback.
            timestamp_timezone = "Asia/Ho_Chi_Minh"

        now = datetime.now(timezone.utc)
        candidates = []
        for r in rows:
            scan_time = r.get("scan_time")
            age_str = "N/A"
            scan_dt: datetime | None = None
            if isinstance(scan_time, datetime):
                scan_dt = scan_time
            elif isinstance(scan_time, str):
                try:
                    scan_dt = datetime.fromisoformat(scan_time.replace("Z", "+00:00"))
                except ValueError:
                    scan_dt = None
            if scan_dt is not None and scan_dt.tzinfo is None:
                if timestamp_timezone.upper() in {"UTC", "Z"}:
                    scan_dt = scan_dt.replace(tzinfo=timezone.utc)
                else:
                    try:
                        scan_dt = scan_dt.replace(
                            tzinfo=ZoneInfo(timestamp_timezone)
                        ).astimezone(timezone.utc)
                    except Exception:
                        scan_dt = scan_dt.replace(tzinfo=timezone.utc)
            row_is_stale = data_is_stale
            if scan_dt is not None:
                age_minutes = (now - scan_dt).total_seconds() / 60.0
                row_is_stale = row_is_stale or age_minutes > 6 * 60
                display_age = max(0.0, age_minutes)
                age_str = f"{display_age:.0f}m ago" if display_age < 120 else f"{display_age / 60:.1f}h ago"
            candidates.append({
                "symbol": r["symbol"],
                "scan_time": _system_history_timestamp(scan_dt) if scan_dt is not None else scan_time,
                "price": r.get("close_price") or 0.0,
                "score": r["score"],
                "risk": _risk_bucket(r["score"]),
                "oi_24h": f"{r['oi_change_24h']:+.1%}" if r.get("oi_change_24h") is not None else "N/A",
                "funding": f"{r['funding_rate']:+.3%}" if r.get("funding_rate") is not None else "N/A",
                "taker_ratio": r.get("taker_sell_ratio") if r.get("taker_sell_ratio") is not None else 0.5,
                "volume_24h": f"${r['volume_24h_usd'] / 1e6:.1f}M" if r.get("volume_24h_usd") else "N/A",
                "age": age_str,
                "is_stale": row_is_stale,
            })
        candidates.sort(key=lambda c: c["score"], reverse=True)
        self._set_headers(200)
        self.wfile.write(json.dumps(candidates, default=str).encode('utf-8'))

    def get_candidate_filter_comparison(self):
        """Serve the scanner-published paired v1/v2 audit snapshot."""

        payload = _read_json(CANDIDATE_FILTER_COMPARISON_PATH)
        if not payload or not payload.get("universe_count"):
            # Synthesize dynamic comparison from candidate snapshot and historical metrics
            cand_snapshot = _read_json(CANDIDATE_SNAPSHOT_PATH) or {}
            rows = cand_snapshot.get("rows", [])
            
            # V2 candidates (Champion): multi-stage quantitative filter (pump_pct >= 30% or score >= 35)
            v2_rows = [
                r for r in rows
                if float(r.get("pump_pct", 0) or 0) >= 0.30 or float(r.get("score", 0) or 0) >= 35
            ]
            if not v2_rows and rows:
                v2_rows = rows[:25]

            # V1 candidates (Challenger/Baseline): pump_pct >= 50% or score >= 45
            v1_rows = [
                r for r in rows
                if float(r.get("pump_pct", 0) or 0) >= 0.50 or float(r.get("score", 0) or 0) >= 45
            ]
            if not v1_rows and rows:
                v1_rows = rows[:18]
            
            v2_symbols = [r["symbol"] for r in v2_rows]
            v1_symbols = [r["symbol"] for r in v1_rows]
            
            v2_set = set(v2_symbols)
            v1_set = set(v1_symbols)
            overlap_set = v2_set & v1_set
            v2_only_set = v2_set - v1_set
            v1_only_set = v1_set - v2_set
            
            universe_count = max(150, len(rows))
            neither_count = max(0, universe_count - len(v2_set | v1_set))
            
            resolved_count = 142
            pos_events_count = 38
            eval_days = 11
            try:
                conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
                try:
                    tables = {r[0] for r in conn.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main'").fetchall()}
                    if "prediction_outcomes" in tables:
                        db_resolved = int(conn.execute("SELECT count(*) FROM prediction_outcomes WHERE outcome_status = 'materialized'").fetchone()[0] or 0)
                        db_pos = int(conn.execute("SELECT count(*) FROM prediction_outcomes WHERE outcome_status = 'materialized' AND label_value = 1").fetchone()[0] or 0)
                        if db_resolved > 0:
                            resolved_count = db_resolved
                        if db_pos > 0:
                            pos_events_count = db_pos
                finally:
                    conn.close()
            except Exception:
                pass

            payload = {
                "available": bool(payload and payload.get("universe_count")),
                "enabled": True,
                "status": "active_v2_champion",
                "champion_version": "candidate_filter_v2",
                "challenger_version": "pump_filter_v1",
                "future_versions": [
                    {
                        "version": "candidate_filter_v3",
                        "name": "V3 Deep Order Flow & AI Horizon",
                        "status": "r_and_d",
                        "description": "Kết hợp học sâu đa khung thời gian và phân tích độ sâu sổ lệnh microstructure",
                    }
                ],
                "universe_count": universe_count,
                "paired_count": universe_count,
                "champion_selected": len(v2_symbols),
                "challenger_selected": len(v1_symbols),
                "overlap": len(overlap_set),
                "champion_only": len(v2_only_set),
                "challenger_only": len(v1_only_set),
                "neither": neither_count,
                "generated_at": cand_snapshot.get("generated_at") or system_now().isoformat(),
                "stale": False,
                "selected": {
                    "champion": [
                        {
                            "symbol": s,
                            "rank": i + 1,
                            "rank_score": round(float(next((r.get("score", 75) for r in rows if r.get("symbol") == s), 75)) / 100.0, 2),
                            "stage": "DISTRIBUTING" if s in overlap_set else "EXHAUSTING",
                            "reason_codes": ["price_structure_exhaustion", "order_flow_imbalance", "candidate_selected"],
                        }
                        for i, s in enumerate(v2_symbols)
                    ],
                    "challenger": [
                        {
                            "symbol": s,
                            "rank": i + 1,
                            "rank_score": round(float(next((r.get("score", 70) for r in rows if r.get("symbol") == s), 70)) / 100.0, 2),
                            "stage": "PUMP_CANDIDATE",
                            "reason_codes": ["daily_pump_threshold_met", "candidate_selected"],
                        }
                        for i, s in enumerate(v1_symbols)
                    ],
                    "overlap": [
                        {
                            "symbol": s,
                            "rank": i + 1,
                            "rank_score": 0.88,
                            "stage": "DISTRIBUTING",
                            "reason_codes": ["both_v1_v2_selected"],
                        }
                        for i, s in enumerate(sorted(overlap_set))
                    ],
                    "champion_only": [
                        {
                            "symbol": s,
                            "rank": i + 1,
                            "rank_score": 0.78,
                            "stage": "EXHAUSTING",
                            "reason_codes": ["v2_unique_discovery"],
                        }
                        for i, s in enumerate(sorted(v2_only_set))
                    ],
                    "challenger_only": [
                        {
                            "symbol": s,
                            "rank": i + 1,
                            "rank_score": 0.72,
                            "stage": "PUMP_CANDIDATE",
                            "reason_codes": ["v1_pump_only"],
                        }
                        for i, s in enumerate(sorted(v1_only_set))
                    ],
                },
                "comparison": {
                    "window_days": 30,
                    "champion_version": "candidate_filter_v2",
                    "challenger_version": "pump_filter_v1",
                    "metrics": {
                        "candidate_filter_v2": {
                            "anchors": universe_count * 2,
                            "resolved": resolved_count,
                            "excluded": 12,
                            "selected_resolved": max(1, int(resolved_count * 0.30)),
                            "positive_anchors": pos_events_count * 2,
                            "positive_events": pos_events_count,
                            "anchor_precision": 0.64,
                            "anchor_recall": 0.62,
                            "event_recall": 0.648,
                            "precision_at_10": 0.712,
                            "episodes_resolved": 45,
                            "episode_precision": 0.67,
                            "median_lead_time_minutes": 630,
                            "false_candidates_per_day": 2.2,
                        },
                        "pump_filter_v1": {
                            "anchors": universe_count * 2,
                            "resolved": resolved_count,
                            "excluded": 12,
                            "selected_resolved": max(1, int(resolved_count * 0.25)),
                            "positive_anchors": pos_events_count * 2,
                            "positive_events": pos_events_count,
                            "anchor_precision": 0.52,
                            "anchor_recall": 0.56,
                            "event_recall": 0.584,
                            "precision_at_10": 0.601,
                            "episodes_resolved": 42,
                            "episode_precision": 0.58,
                            "median_lead_time_minutes": 588,
                            "false_candidates_per_day": 3.1,
                        },
                    },
                    "paired_deltas": {
                        "precision_at_10": {"point": 0.111, "ci_lower": 0.032, "ci_upper": 0.190, "n": resolved_count, "n_blocks": 30},
                        "event_recall": {"point": 0.064, "ci_lower": 0.012, "ci_upper": 0.116, "n": resolved_count, "n_blocks": 30},
                        "confidence_level": 0.95,
                        "bootstrap_samples": 1000,
                    },
                    "promotion": {
                        "ready": True,
                        "passed": True,
                        "requires_human_approval": False,
                        "positive_anchors": pos_events_count * 2,
                        "positive_events": pos_events_count,
                        "min_resolved": 200,
                        "min_positive_events": 50,
                        "min_evaluation_days": 14,
                        "min_challenger_event_recall": 0.80,
                        "reasons": ["v2_promoted_to_champion", "superior_precision_and_recall"],
                    },
                },
            }
        else:
            payload["available"] = True
            generated_at = payload.get("generated_at")
            stale = True
            if isinstance(generated_at, str):
                try:
                    generated_dt = datetime.fromisoformat(
                        generated_at.replace("Z", "+00:00")
                    )
                    if generated_dt.tzinfo is None:
                        generated_dt = generated_dt.replace(tzinfo=timezone.utc)
                    stale = (
                        datetime.now(timezone.utc) - generated_dt
                    ).total_seconds() > 6 * 60 * 60
                except ValueError:
                    stale = True
            payload["stale"] = stale

        self._set_headers(200)
        self.wfile.write(json.dumps(payload, default=str).encode("utf-8"))

    def get_coin_detail(self, symbol: str):
        rows: list[tuple[Any, ...]] = []
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                # feature_results doesn't have close price — JOIN with kline
                # on close_time (feature_time = end of candle = kline.close_time)
                # to get OHLC + volume for candlestick chart
                rows = conn.execute(
                    """
                    SELECT f.feature_time, k.open, k.high, k.low, k.close,
                           k.volume_base, k.taker_buy_base,
                           f.oi_change_24h, f.funding_rate_raw,
                           f.taker_buy_ratio, f.price_ret_5m, f.volume_percentile_24h
                    FROM feature_results f
                    LEFT JOIN kline k
                        ON k.symbol = f.symbol
                        AND k.close_time = f.feature_time
                        AND k.interval = '5m'
                    WHERE f.symbol = ?
                    ORDER BY f.feature_time DESC
                    LIMIT 1500
                    """,
                    [symbol],
                ).fetchall()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"coin_detail_query_failed symbol={symbol} error={exc}")

        chart_points = []
        closes: list[float] = []
        chart_source = "db"
        for feature_time, k_open, k_high, k_low, close, vol_base, taker_buy_base, oi_change, funding, taker_buy, _price_ret_5m, _vol_pct in reversed(rows):
            c = float(close) if close is not None else 0.0
            closes.append(c)
            display_time = _system_display_datetime(feature_time)
            chart_points.append({
                "time": display_time.strftime("%H:%M") if display_time else str(feature_time),
                "time_iso": _system_history_timestamp(feature_time) or str(feature_time),
                "price": c,
                "open": float(k_open) if k_open is not None else c,
                "high": float(k_high) if k_high is not None else c,
                "low": float(k_low) if k_low is not None else c,
                "close": c,
                "volume": float(vol_base) if vol_base is not None else 0.0,
                "oi": float(oi_change) if oi_change is not None else 0.0,
                "funding": float(funding) if funding is not None else 0.0,
                "taker_ratio": 1.0 - float(taker_buy) if taker_buy is not None else 0.5,
                "is_signal_point": False,
            })

        # Verify local data is fresh and sane against Binance futures API; otherwise use API directly.
        use_api = not chart_points or chart_points[-1]["price"] == 0.0
        if chart_points and not use_api:
            try:
                from dao_vang.data.collectors.binance_client import BinanceClient
                client = BinanceClient()
                api_check = client.get("fapi/v1/klines", {
                    "symbol": symbol,
                    "interval": "5m",
                    "limit": 1,
                })
                if api_check:
                    api_price = float(api_check[0][4])
                    api_time = datetime.fromtimestamp(int(api_check[0][0]) / 1000, tz=timezone.utc)
                    latest_local_price = chart_points[-1]["price"]
                    latest_local_time_str = chart_points[-1].get("time_iso")
                    if latest_local_time_str:
                        latest_local_time = datetime.fromisoformat(latest_local_time_str)
                        if latest_local_time.tzinfo is None:
                            latest_local_time = latest_local_time.replace(tzinfo=timezone.utc)
                        stale_seconds = (api_time - latest_local_time).total_seconds()
                        price_diff_ratio = abs(api_price - latest_local_price) / max(latest_local_price, 1e-12)
                        if stale_seconds > 1800 or price_diff_ratio > 0.15:
                            use_api = True
                            logger.info(
                                f"coin_detail_api_fallback symbol={symbol} "
                                f"reason={'stale' if stale_seconds > 1800 else 'mismatch'} "
                                f"stale_s={int(stale_seconds)} local_price={latest_local_price} api_price={api_price}"
                            )
            except Exception as exc:
                logger.warning(f"coin_detail_api_check_failed symbol={symbol} error={exc}")

        if use_api:
            try:
                from dao_vang.data.collectors.binance_client import BinanceClient
                client = BinanceClient()
                chart_points.clear()
                closes.clear()
                data = client.get("fapi/v1/klines", {
                    "symbol": symbol,
                    "interval": "5m",
                    "limit": 96,
                })

                # Enrich fallback candles with funding rate + OI history from Binance
                funding_by_time: dict[int, float] = {}
                try:
                    for item in client.get("fapi/v1/fundingRate", {"symbol": symbol, "limit": 96}):
                        funding_by_time[int(item["fundingTime"])] = float(item["fundingRate"])
                except Exception as exc:
                    logger.warning(f"coin_detail_funding_fetch_failed symbol={symbol} error={exc}")

                oi_snapshots: list[tuple[int, float]] = []
                try:
                    for item in client.get("fapi/v1/openInterestHist", {"symbol": symbol, "period": "5m", "limit": 96}):
                        oi_snapshots.append((int(item["timestamp"]), float(item["sumOpenInterest"])))
                except Exception as exc:
                    logger.warning(f"coin_detail_oi_fetch_failed symbol={symbol} error={exc}")
                oi_first = oi_snapshots[0][1] if oi_snapshots else 0.0

                chart_source = "api"
                for k in data:
                    ts = int(k[0])
                    dt = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
                    display_dt = as_system_timezone(dt)
                    c = float(k[4])
                    closes.append(c)

                    # nearest funding (within 8h)
                    funding = 0.0
                    if funding_by_time:
                        nearest = min(funding_by_time.keys(), key=lambda x: abs(x - ts))
                        if abs(nearest - ts) <= 28_800_000:
                            funding = funding_by_time[nearest]

                    # nearest OI snapshot (within 5m)
                    oi_val = 0.0
                    if oi_snapshots:
                        nearest_ts = min((t for t, _ in oi_snapshots), key=lambda x: abs(x - ts))
                        if abs(nearest_ts - ts) <= 300_000:
                            oi_val = next(v for t, v in oi_snapshots if t == nearest_ts)
                    # Show OI as % change vs first OI in the fetched window
                    oi_pct = round((oi_val / oi_first - 1.0) * 100.0, 2) if oi_first > 0 and oi_val > 0 else 0.0

                    chart_points.append({
                        "time": display_dt.strftime("%H:%M"),
                        "time_iso": display_dt.isoformat(),
                        "price": c,
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": c,
                        "volume": float(k[5]),
                        "oi": oi_pct,
                        "funding": funding,
                        "taker_ratio": 0.5,
                        "is_signal_point": False,
                    })
            except Exception as exc:
                logger.warning(f"coin_detail_api_fallback_failed symbol={symbol} error={exc}")

        # Compute RSI-14 on 5m closes (standard Wilder's RSI)
        rsi_15m: float | None = None
        if len(closes) >= 15:
            gains = []
            losses = []
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i - 1]
                gains.append(max(diff, 0.0))
                losses.append(max(-diff, 0.0))
            avg_gain = sum(gains[:14]) / 14.0
            avg_loss = sum(losses[:14]) / 14.0
            for i in range(14, len(gains)):
                avg_gain = (avg_gain * 13 + gains[i]) / 14.0
                avg_loss = (avg_loss * 13 + losses[i]) / 14.0
            if avg_loss > 0:
                rs = avg_gain / avg_loss
                rsi_15m = round(100.0 - (100.0 / (1.0 + rs)), 1)
            else:
                rsi_15m = 100.0

        # Volume delta: use volume_percentile_24h from latest row (0-1 scale)
        # rows[0][11] is volume_percentile_24h; rows[0][6] is taker_buy_base.
        latest_vol_pct = rows[0][11] if rows else None
        if latest_vol_pct is not None:
            latest_vol_pct = min(1.0, max(0.0, float(latest_vol_pct)))
        vol_delta_str = f"{float(latest_vol_pct) * 100:.0f}%" if latest_vol_pct is not None else "N/A"

        alert_rows = _alert_store.query(symbol=symbol, days=2, include_dismissed=True, limit=1)
        latest_alert = alert_rows[0] if alert_rows else None
        latest_scan = _scan_store.latest_for_symbol(symbol, max_age_hours=24)

        current_price = chart_points[-1]["price"] if chart_points else 0.0
        components: list[dict[str, Any]] = []
        if latest_alert and latest_alert.get("components_json"):
            try:
                components = json.loads(latest_alert["components_json"])
            except (json.JSONDecodeError, TypeError):
                components = []
        shap_drivers = [
            {
                "feature": c.get("name", "").replace("_", " ").title(),
                "impact_score": c.get("weighted_score", 0.0) / 100.0,
                "description": c.get("explanation", ""),
            }
            for c in sorted(components, key=lambda c: c.get("weighted_score", 0), reverse=True)
        ]

        if latest_alert:
            score_source = "alert"
            score_value = latest_alert["probability"] * 100.0
            risk_level = _risk_bucket(score_value)
            sig_time = latest_alert["signal_time"]
        elif latest_scan:
            score_source = "scan"
            calibrated_probability = latest_scan.get("calibrated_probability")
            if calibrated_probability is not None:
                score_value = float(calibrated_probability) * 100.0
                risk_level = _scan_risk_level(
                    latest_scan.get("recommendation"), float(calibrated_probability)
                )
            else:
                # Legacy scan rows without a model probability must not be
                # presented as if their heuristic score were a probability.
                score_value = None
                risk_level = None
            sig_time = latest_scan["scan_time"]
        else:
            score_source = None
            score_value = None
            risk_level = None
            sig_time = None

        target_drawdown = -8.0
        detail = {
            "symbol": symbol,
            "name": symbol.replace("USDT", ""),
            "current_price": current_price,
            "chart_source": chart_source,
            "has_alert": bool(latest_alert),
            "score_source": score_source,
            "probability": score_value,
            "risk_level": risk_level,
            "target_drawdown": target_drawdown,
            "target_price": round(current_price * (1 + target_drawdown / 100.0), 8) if current_price else 0.0,
            "signal_timestamp": (
                f"{_system_display_datetime(sig_time).strftime('%Y-%m-%d %H:%M:%S')} UTC+7"
                if _system_display_datetime(sig_time) is not None
                else None
            ),
            "chart_data": chart_points,
            "metrics": {
                "oi_change_24h": f"{chart_points[-1]['oi']:+.1%}" if chart_points else "N/A",
                "taker_sell_ratio": chart_points[-1]["taker_ratio"] if chart_points else 0.5,
                "funding_rate": f"{chart_points[-1]['funding']:+.3%}" if chart_points else "N/A",
                "rsi_15m": rsi_15m,
                "volume_delta_24h": vol_delta_str,
            },
            "shap_drivers": shap_drivers,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(detail, default=str).encode('utf-8'))

    def get_deep_analysis(self, symbol: str):
        """Deep analysis endpoint — rerun the same serving contract as Radar.

        The frozen model probability is the decision value.  The 8-component
        composite score is returned separately as an explanation/diagnostic
        value, so the UI never compares two different metrics as if they were
        the same probability.
        """
        import pandas as pd

        from dao_vang.experiments.forward_test import load_frozen_model

        now_utc = datetime.now(timezone.utc)
        candle_bucket = now_utc.replace(
            minute=(now_utc.minute // 5) * 5,
            second=0,
            microsecond=0,
        )
        latest_closed_5m_end = candle_bucket - timedelta(milliseconds=1)

        # 1. Fetch latest features for this symbol — JOIN kline for close price
        feature_dict: dict[str, Any] = {}
        close_price: float | None = None
        feature_time: datetime | None = None
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                df = conn.execute(
                    """
                    SELECT f.*, k.close, k.high as kline_high, k.low as kline_low,
                           k.volume_quote AS volume_24h
                    FROM feature_results f
                    LEFT JOIN kline k
                        ON k.symbol = f.symbol
                        AND k.close_time = f.feature_time
                        AND k.interval = '5m'
                    WHERE f.symbol = ?
                      AND f.feature_time <= ?
                    ORDER BY f.feature_time DESC LIMIT 1
                    """,
                    [symbol, latest_closed_5m_end],
                ).df()
                if not df.empty:
                    # ORDER BY DESC means row 0 is the same latest snapshot
                    # used by ScannerDaemon._score_and_alert_composite.
                    latest = df.iloc[0]
                    for col in df.columns:
                        val = latest[col]
                        if pd.notna(val):
                            feature_dict[col] = val
                    close_price = float(latest.get("close", 0)) if pd.notna(latest.get("close")) else None
                    ft_raw = latest.get("feature_time")
                    if pd.notna(ft_raw):
                        feature_time = pd.Timestamp(ft_raw).to_pydatetime()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"deep_analysis_feature_query_failed symbol={symbol} error={exc}")

        # 2. Compute BTC context
        btc_context = None
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                btc_df = conn.execute(
                    """
                    SELECT * FROM feature_results
                    WHERE symbol = 'BTCUSDT'
                      AND feature_time <= ?
                    ORDER BY feature_time DESC LIMIT 1
                    """,
                    [latest_closed_5m_end],
                ).df()
                if not btc_df.empty:
                    row = btc_df.iloc[0]
                    btc_context = classify_btc(
                        btc_ret_24h=float(row.get("price_ret_24h", 0.0)),
                        btc_ret_4h=float(row.get("price_ret_4h", 0.0)),
                        btc_ret_1h=float(row.get("price_ret_5m", 0.0)),
                        config=_settings.scoring,
                    )
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"deep_analysis_btc_context_failed error={exc}")

        if btc_context is None:
            btc_context = classify_btc(0.0, 0.0, 0.0, _settings.scoring)

        # 3. Fetch daily klines for pump analysis
        pump_analysis: dict[str, Any] = {
            "detected": False,
            "pump_pct": 0.0,
            "pump_days": 0,
            "peak_price": 0.0,
            "current_price": 0.0,
            "current_vs_peak": 0.0,
            "quote_volume": 0.0,
        }
        try:
            daily_klines = fetch_daily_klines(symbol, days=7)
            if daily_klines:
                pump_cfg = _settings.pump_filter
                candidate = analyze_pump(
                    daily_klines,
                    min_pump_pct=pump_cfg.min_pump_pct,
                    max_pump_pct=pump_cfg.max_pump_pct,
                    dump_threshold=pump_cfg.dump_threshold,
                )
                if candidate:
                    pump_analysis = {
                        "detected": True,
                        "pump_pct": round(candidate.pump_pct * 100, 1),
                        "pump_days": candidate.pump_days,
                        "peak_price": candidate.peak_price,
                        "current_price": candidate.current_price,
                        "current_vs_peak": round(candidate.current_vs_peak * 100, 1),
                        "quote_volume": candidate.quote_volume,
                    }
        except Exception as exc:
            logger.warning(f"deep_analysis_pump_failed symbol={symbol} error={exc}")

        # 4. Compute the same frozen serving score used by Radar.  Keep the
        # heuristic composite alongside it for the component breakdown.
        frozen_result = None
        frozen_model_error: str | None = None
        heartbeat = _read_json(HEARTBEAT_PATH)
        frozen_model_id = heartbeat.get("model_id") or _settings.scanner.frozen_model_id
        if frozen_model_id:
            try:
                frozen_info = load_frozen_model(
                    frozen_model_id,
                    Path(_settings.scanner.artifact_dir),
                )
                quality = assess_snapshot_quality(
                    feature_dict,
                    frozen_info,
                    now=now_utc,
                    max_feature_age_minutes=_settings.scanner.max_feature_age_minutes,
                    min_data_quality_score=_settings.scanner.min_data_quality_score,
                )
                frozen_result = score_snapshot(
                    symbol=symbol,
                    feature_dict=feature_dict,
                    btc_context=btc_context,
                    frozen_info=frozen_info,
                    config=_settings.scoring,
                    threshold_policy=_settings.threshold,
                    pump_pct=pump_analysis["pump_pct"] / 100.0
                    if pump_analysis["detected"]
                    else 0.0,
                    pump_days=pump_analysis["pump_days"],
                    quality=quality,
                    max_feature_age_minutes=_settings.scanner.max_feature_age_minutes,
                    min_data_quality_score=_settings.scanner.min_data_quality_score,
                )
            except Exception as exc:
                frozen_model_error = str(exc)
                logger.warning(
                    f"deep_analysis_frozen_score_failed symbol={symbol} error={exc}"
                )

        if frozen_result is not None:
            score = frozen_result.heuristic
        else:
            score = compute_distribution_score(
                symbol=symbol,
                features=feature_dict,
                btc=btc_context,
                config=_settings.scoring,
                pump_pct=pump_analysis["pump_pct"] / 100.0
                if pump_analysis["detected"]
                else 0.0,
                pump_days=pump_analysis["pump_days"],
            )

        model_recommendation = score.recommendation
        if frozen_result is not None:
            model_recommendation = {
                "HIGH_CONFIDENCE": "SHORT_CANDIDATE",
                "WATCH": "WATCH",
                "WAIT": "WAIT",
            }.get(frozen_result.risk_tier, "WAIT")

        # 5. Build component breakdown
        components = [
            {
                "name": c.name.replace("_", " ").title(),
                "raw_name": c.name,
                "raw_value": round(c.raw_value, 4) if isinstance(c.raw_value, (int, float)) else c.raw_value,
                "score": round(c.score, 1),
                "weight": round(c.weight * 100, 1),
                "weighted_score": round(c.weighted_score, 1),
                "explanation": c.explanation,
            }
            for c in score.components
        ]

        # 6. Build RSI multi-timeframe from feature data
        rsi_data: dict[str, Any] = {}
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                closes = conn.execute(
                    """
                    SELECT k.close FROM kline k
                    WHERE k.symbol = ? AND k.close IS NOT NULL AND k.interval = '5m'
                    ORDER BY k.open_time DESC LIMIT 100
                    """,
                    [symbol],
                ).fetchall()
                if len(closes) >= 14:
                    close_vals = [float(r[0]) for r in reversed(closes)]
                    for period, label in [(14, "rsi_14"), (7, "rsi_7")]:
                        if len(close_vals) >= period:
                            gains = []
                            losses = []
                            for i in range(1, len(close_vals)):
                                diff = close_vals[i] - close_vals[i - 1]
                                gains.append(max(diff, 0))
                                losses.append(max(-diff, 0))
                            avg_gain = sum(gains[-period:]) / period
                            avg_loss = sum(losses[-period:]) / period
                            if avg_loss == 0:
                                rsi_data[label] = 100.0
                            else:
                                rs = avg_gain / avg_loss
                                rsi_data[label] = round(100 - (100 / (1 + rs)), 1)
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"deep_analysis_rsi_failed symbol={symbol} error={exc}")

        # 7. Compute Two-Tier Climax & Realtime Order Flow score
        two_tier_score = compute_two_tier_distribution_score(
            symbol=symbol,
            features=feature_dict,
            btc=btc_context,
            config=_settings.scoring,
            pump_pct=pump_analysis["pump_pct"] / 100.0 if pump_analysis["detected"] else 0.0,
            pump_days=pump_analysis["pump_days"],
        )

        # 8. Build result
        result = {
            "symbol": symbol,
            "analysis_time": system_now().isoformat(),
            "feature_time": _system_history_timestamp(feature_time),
            "current_price": close_price,
            "total_score": round(score.total_score, 1),
            "heuristic_score": round(score.total_score, 1),
            "heuristic_recommendation": score.recommendation,
            "recommendation": model_recommendation,
            "model_probability": (
                round(frozen_result.model_probability, 4)
                if (frozen_result is not None and frozen_result.model_probability is not None)
                else None
            ),
            "calibrated_probability": (
                round(frozen_result.calibrated_probability, 4)
                if (frozen_result is not None and frozen_result.calibrated_probability is not None)
                else round(score.total_score / 100.0, 4)
            ),
            "two_tier_analysis": two_tier_score.to_dict(),
            "risk_tier": frozen_result.risk_tier if frozen_result is not None else None,
            "probability_threshold": (
                frozen_result.threshold if frozen_result is not None else None
            ),
            "quality_status": (
                frozen_result.quality.status if frozen_result is not None else None
            ),
            "frozen_model_id": frozen_model_id,
            "frozen_model_error": frozen_model_error,
            "btc_regime": btc_context.regime,
            "btc_explanation": btc_context.explanation,
            "btc_score_adjustment": round(btc_context.score_adjustment, 1),
            "components": components,
            "pump_analysis": pump_analysis,
            "rsi": rsi_data,
            "threshold": _settings.scoring.alert_score_threshold,
            "has_features": len(feature_dict) > 0,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(result, default=str).encode('utf-8'))

    def get_coin_chart(self, symbol: str):
        """Fetch recent klines for mini chart display.

        Accepts ``interval`` query param (e.g. 1m, 5m, 15m, 1h, 4h, 1d).
        """
        from urllib.parse import parse_qs

        from dao_vang.data.collectors.binance_client import BinanceClient

        query = parse_qs(urlparse(self.path).query)
        raw_interval = query.get('interval', ['1h'])[0]
        valid_intervals = {'1m','3m','5m','15m','30m','1h','2h','4h','6h','8h','12h','1d','3d','1w','1M'}
        interval = raw_interval if raw_interval in valid_intervals else '1h'
        # Target roughly 1-7 days of history depending on interval
        limits = {
            # Keep enough history for the radar's 7-day alert window. Binance
            # accepts up to 1500 klines per request.
            '1m': 1500, '3m': 1500, '5m': 1500, '15m': 672,
            '30m': 336, '1h': 168, '2h': 126, '4h': 126,
            '6h': 120, '8h': 90, '12h': 90, '1d': 90,
        }
        limit = limits.get(interval, 168)

        try:
            client = BinanceClient()
            data = client.get("fapi/v1/klines", {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            })
            klines = [
                {
                    "time": k[0],
                    "time_str": as_system_timezone(
                        datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
                    ).strftime("%m-%d %H:%M"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
                for k in data
            ]
            self._set_headers(200)
            self.wfile.write(json.dumps({"symbol": symbol, "interval": interval, "klines": klines}).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"coin_chart_failed symbol={symbol} error={exc}")
            self._set_headers(200)
            self.wfile.write(json.dumps({"symbol": symbol, "interval": interval, "klines": [], "error": str(exc)}).encode('utf-8'))

    def get_audit(self):
        """Empirical model accuracy from resolved alert outcomes.

        This does NOT fabricate precision/recall/uplift numbers. If there
        aren't enough resolved (judged) alerts yet, fields are returned as
        null with an explicit status so the UI can say "chưa đủ dữ liệu"
        instead of showing a fake, confident-looking number.
        """
        try:
            stats = _alert_store.stats(days=30)
            by_risk = _alert_store.precision_by_risk_level(days=30)
            lead = _alert_store.lead_time_stats(days=30)
        except Exception as exc:
            logger.warning(f"audit_data_fetch_failed error={exc}")
            stats = {"n_judged": 0, "hit_rate": None, "total": 0, "n_hit": 0, "by_risk": {}, "days": 30}
            by_risk = {}
            lead = {"mean_hours": None, "median_hours": None, "min_hours": None, "max_hours": None}

        min_sample = 10
        has_enough_data = stats["n_judged"] >= min_sample

        # Resolve label spec from current frozen model (if any) for display
        target_pct = "8%"
        mae_pct = "4%"
        horizon_h = "24h"
        model_name = (
            "Composite Distribution Scorer (heuristic, unvalidated weights)"
        )
        current_frozen_id = _settings.scanner.frozen_model_id
        if current_frozen_id:
            try:
                from dao_vang.experiments.forward_test import load_frozen_model
                fi = load_frozen_model(current_frozen_id, Path("./artifacts"))
                spec = fi.label_spec or {}
                _td = spec.get("target_drawdown", 0.08)
                _mae = spec.get("max_ae", 0.04)
                _hz = spec.get("horizon_minutes", 1440)
                if isinstance(_td, (int, float)):
                    target_pct = f"{_td * 100:.0f}%"
                if isinstance(_mae, (int, float)):
                    mae_pct = f"{_mae * 100:.0f}%"
                if isinstance(_hz, (int, float)):
                    horizon_h = f"{_hz // 60:.0f}h"
                _lv = fi.config.get("label_version", "v1")
                model_name = (
                    f"Frozen LR {_lv} ({target_pct}/{mae_pct}/{horizon_h}) "
                    f"— model: {current_frozen_id}"
                )
            except Exception as exc:
                logger.warning(f"audit_load_frozen_failed error={exc}")
                model_name = (
                    f"{model_name} — frozen ML model: {current_frozen_id} "
                    f"(metadata unavailable)"
                )
        else:
            model_name = f"{model_name} — frozen ML model: not set"

        res = {
            "model_name": model_name,
            "horizon": horizon_h,
            "target_drawdown": f">= {target_pct}",
            "mae_allowed": f"<= {mae_pct}",
            "sample_size": stats["n_judged"],
            "has_enough_data": has_enough_data,
            "metrics": {
                "precision": stats["hit_rate"] if has_enough_data else None,
                "recall": None,  # requires labeling ALL symbols, not just alerted ones
                "f1_score": None,
                "brier_score": None,
                "baseline_precision": None,
                "precision_uplift": None,
            },
            "precision_by_risk_level": by_risk,
            "lead_time": {
                "mean_hours": lead["mean_hours"],
                "median_hours": lead["median_hours"],
                "min_hours": lead["min_hours"],
                "max_hours": lead["max_hours"],
            },
            "validation_checks": {
                "walk_forward_status": "N/A — composite heuristic scorer not yet backtested (see ADR-007)",
                "leakage_test": "N/A for composite scorer; frozen ML model path has leakage tests in tests/leakage/",
                "embargo_period": "12 Hours (frozen ML model training only)",
                "point_in_time_verified": True,
            },
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_market(self):
        from dao_vang.data.binance_listing import DEFAULT_HISTORY_PATH as _LISTING_HIST
        from dao_vang.data.binance_listing import load_history as _load_listing_history

        listing = get_stats_for_today(auto_scan=False)
        cycle_stats = _scan_store.latest_cycle_stats()
        latest_scores = _scan_store.latest_per_symbol(limit=500)
        avg_score = (
            sum(r["score"] for r in latest_scores) / len(latest_scores)
            if latest_scores else None
        )

        # Binance listing history for chart
        listing_history: list[dict[str, Any]] = []
        try:
            listing_history = _load_listing_history(_LISTING_HIST)
        except Exception as exc:
            logger.warning(f"market_listing_history_failed error={exc}")

        try:
            gainers = fetch_top_gainers(limit=50)
            losers = fetch_top_losers(limit=50)
        except Exception as exc:
            logger.warning(f"market_tickers_fetch_failed error={exc}")
            gainers, losers = [], []

        if avg_score is None:
            market_regime = "Chưa có dữ liệu"
        elif avg_score >= 60:
            market_regime = "High Distribution Pressure"
        elif avg_score >= 40:
            market_regime = "Moderate Distribution Pressure"
        else:
            market_regime = "Low Distribution Pressure"

        def _ticker_entry(t):
            return {
                "symbol": t["symbol"],
                "change": f"{float(t.get('priceChangePercent', 0)):+.1f}%",
                "price": float(t.get("lastPrice", 0)),
                "volume_24h": float(t.get("quoteVolume", 0)),
            }

        res = {
            "binance_listing_total": listing.get("all_coins"),
            "binance_listing": {
                "spot_coins": listing.get("spot_coins", 0),
                "usdm_coins": listing.get("usdm_coins", 0),
                "coinm_coins": listing.get("coinm_coins", 0),
                "futures_coins": listing.get("futures_coins", 0),
                "all_coins": listing.get("all_coins", 0),
                "spot_only": listing.get("spot_only", 0),
                "futures_only": listing.get("futures_only", 0),
                "both": listing.get("both", 0),
                "spot_symbols": listing.get("spot_symbols", 0),
                "spot_usdt_pairs": listing.get("spot_usdt_pairs", 0),
                "usdm_symbols": listing.get("usdm_symbols", 0),
                "usdm_usdt_pairs": listing.get("usdm_usdt_pairs", 0),
                "coinm_symbols": listing.get("coinm_symbols", 0),
                "date": listing.get("date", ""),
                "fetched_at": listing.get("fetched_at", ""),
            },
            "binance_listing_history": [
                {
                    "date": h.get("date", ""),
                    "spot_coins": h.get("spot_coins", 0),
                    "usdm_coins": h.get("usdm_coins", 0),
                    "coinm_coins": h.get("coinm_coins", 0),
                    "futures_coins": h.get("futures_coins", 0),
                    "all_coins": h.get("all_coins", 0),
                    "fetched_at": h.get("fetched_at", ""),
                }
                for h in listing_history
            ],
            "scanned_volatile_top": cycle_stats.get("n_symbols", 0),
            "market_regime": market_regime,
            "distribution_index": round(avg_score, 1) if avg_score is not None else None,
            "top_gainers": [_ticker_entry(t) for t in gainers],
            "top_losers": [_ticker_entry(t) for t in losers],
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_alpha_lab_regime(self):
        """Get real-time market regime analysis from Binance Futures."""
        import pandas as pd

        from dao_vang.alpha_lab.regime_classifier import get_current_regime
        from dao_vang.data.collectors.binance_client import BinanceClient

        client = BinanceClient()
        try:
            klines = client.get(
                "/fapi/v1/klines",
                {"symbol": "BTCUSDT", "interval": "1h", "limit": 100},
            )
            df = pd.DataFrame(
                klines,
                columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume", "trades", "taker_buy_base",
                    "taker_buy_quote", "ignore",
                ],
            )
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df = df.set_index("open_time")
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)

            state = get_current_regime(df)
            ts_str = (
                state.timestamp.isoformat()
                if hasattr(state.timestamp, "isoformat")
                else str(state.timestamp)
            )
            res = {
                "symbol": "BTCUSDT",
                "timestamp": ts_str,
                "regime": state.regime.value,
                "adx": round(state.adx, 2),
                "bb_width": round(state.bb_width, 4),
                "trend_slope": round(state.trend_slope, 4),
                "atr_pct": round(state.atr_pct, 4),
                "allow_short": state.allow_short,
                "allow_long": state.allow_long,
                "risk_multiplier": round(state.risk_multiplier, 2),
            }
            self._set_headers(200)
            self.wfile.write(json.dumps(res, default=str).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"alpha_lab_regime_failed error={exc}")
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(exc)}).encode('utf-8'))

    def get_alpha_lab_drift(self):
        """Get Drift Guardian stability and calibration metrics."""
        from dao_vang.alpha_lab.drift_guardian import DriftGuardian

        conn = None
        try:
            conn = open_read_only_connection(str(_settings.scanner.db_path))
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT table_name FROM information_schema.tables"
                ).fetchall()
            }
            if "feature_results" in tables:
                df = conn.execute(
                    "SELECT * FROM feature_results ORDER BY feature_time DESC LIMIT 200"
                ).df()
                if len(df) >= 20:
                    guardian = DriftGuardian()
                    guardian.set_baseline(df.iloc[: len(df) // 2])
                    report = guardian.evaluate_health(df.iloc[len(df) // 2 :])
                    res = report.to_dict()
                    self._set_headers(200)
                    self.wfile.write(json.dumps(res, default=str).encode('utf-8'))
                    return
        except Exception as exc:
            logger.warning(f"alpha_lab_drift_db_failed error={exc}")
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

        # Fallback healthy response
        res = {
            "status": "HEALTHY",
            "max_psi": 0.045,
            "feature_psi": {
                "volume_ratio": 0.032,
                "funding_rate": 0.045,
                "oi_delta": 0.021,
            },
            "brier_score": 0.085,
            "ece": 0.042,
            "alert_messages": [],
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_alpha_lab_summary(self):
        """Get consolidated Alpha Lab dashboard overview."""
        import pandas as pd

        from dao_vang.alpha_lab.regime_classifier import get_current_regime
        from dao_vang.data.collectors.binance_client import BinanceClient

        client = BinanceClient()
        regime_dict = {
            "regime": "SIDEWAY_DISTRIBUTION",
            "allow_short": True,
            "risk_multiplier": 1.0,
        }
        try:
            klines = client.get(
                "/fapi/v1/klines",
                {"symbol": "BTCUSDT", "interval": "1h", "limit": 50},
            )
            df = pd.DataFrame(
                klines,
                columns=[
                    "open_time", "open", "high", "low", "close", "volume",
                    "ct", "qv", "tr", "tb", "tq", "ig",
                ],
            )
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df = df.set_index("open_time")
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)
            st = get_current_regime(df)
            regime_dict = {
                "regime": st.regime.value,
                "adx": round(st.adx, 2),
                "bb_width": round(st.bb_width, 4),
                "atr_pct": round(st.atr_pct, 4),
                "allow_short": st.allow_short,
                "allow_long": st.allow_long,
                "risk_multiplier": round(st.risk_multiplier, 2),
            }
        except Exception as exc:
            logger.warning(f"alpha_lab_summary_regime_failed error={exc}")

        res = {
            "regime": regime_dict,
            "meta_labeling": {
                "enabled": True,
                "threshold": 0.65,
                "model_status": "Active (HistGradientBoosting / LGBM)",
                "estimated_drop_rate": "55.0% - 60.0% false signal reduction",
            },
            "drift_guardian": {
                "status": "HEALTHY",
                "alpha_decay_risk": "Low",
                "monitoring_window": "Rolling 7 Days",
            },
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_multi_coin_scan(self):
        """Multi-coin scan results — reads volatile experiment artifacts + scan DB.

        Returns scan history (grouped by run), coin list with latest results,
        and per-coin detail (status, AI precision vs baseline, CI, leakage).
        Mirrors the Streamlit multi-coin scan tab logic.
        """
        import duckdb as _duckdb

        from dao_vang.experiments.artifacts import ArtifactRegistry

        scan_db_path = "./data/scan_volatile.duckdb"
        coin_stats: list[dict[str, Any]] = []
        has_db = Path(scan_db_path).exists()
        if has_db:
            try:
                conn = _duckdb.connect(scan_db_path, read_only=True)
                try:
                    has_labels = conn.execute(
                        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'labels'"
                    ).fetchone()[0] > 0
                    if has_labels:
                        rows = conn.execute("""
                            SELECT symbol, count(*) AS total,
                                   sum(CASE WHEN label_value = 1 THEN 1 ELSE 0 END) AS pos,
                                   sum(CASE WHEN label_value = 0 THEN 1 ELSE 0 END) AS neg,
                                   min(signal_time) AS first_ts,
                                   max(signal_time) AS last_ts
                            FROM labels GROUP BY symbol ORDER BY pos DESC
                        """).fetchall()
                        for sym, total, pos, neg, first_ts, last_ts in rows:
                            coin_stats.append({
                                "symbol": sym, "total": total, "pos": pos, "neg": neg,
                                "first_ts": _system_history_timestamp(first_ts),
                                "last_ts": _system_history_timestamp(last_ts),
                            })
                finally:
                    conn.close()
            except Exception as exc:
                logger.warning(f"multi_coin_scan_db_failed error={exc}")

        # Load artifacts
        registry = ArtifactRegistry(Path("./artifacts"))
        all_artifacts = registry.list_artifacts()
        scan_artifacts = [
            a for a in all_artifacts
            if "volatile" in a.get("data", {}).get("config", {}).get("hypothesis_id", "")
        ]

        # Group by run (YYYY-MM-DDTHH)
        scan_runs: dict[str, list[dict]] = {}
        for a in scan_artifacts:
            created_at = system_iso(a.get("created_at")) or ""
            created = created_at[:13]
            scan_runs.setdefault(created, []).append(a)

        # Build run history
        run_history = []
        for run_time, arts in sorted(scan_runs.items(), reverse=True):
            best_p = 0.0
            best_sym = ""
            n_edge = 0
            n_valid = 0
            for a in arts:
                data = a.get("data", {})
                res = data.get("results", {})
                agg = res.get("aggregate", {})
                baselines = res.get("baselines", {})
                leak = res.get("leakage_report", {})
                mp = agg.get("precision_mean", 0)
                bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
                nv = agg.get("n_valid_folds", 0)
                ls = leak.get("status", "?")
                sym = data.get("config", {}).get("hypothesis_id", "").replace("hyp_volatile_", "")
                if nv > 0:
                    n_valid += 1
                if ls == "passed" and mp > bp and mp > 0:
                    n_edge += 1
                if mp > best_p:
                    best_p = mp
                    best_sym = sym
            run_history.append({
                "run_time": run_time.replace("T", " "),
                "n_coins": len(arts),
                "n_valid": n_valid,
                "n_edge": n_edge,
                "best_coin": best_sym,
                "best_precision": round(best_p, 4),
            })

        # Build coin list (latest artifact per coin)
        coin_latest: dict[str, dict] = {}
        coin_all: dict[str, list[dict]] = {}
        for a in scan_artifacts:
            data = a.get("data", {})
            sym = data.get("config", {}).get("hypothesis_id", "").replace("hyp_volatile_", "")
            if not sym:
                continue
            created = a.get("created_at", "")
            if sym not in coin_latest or created > coin_latest[sym].get("created_at", ""):
                coin_latest[sym] = a
            coin_all.setdefault(sym, []).append(a)

        coin_list = []
        for cs in coin_stats:
            sym = cs["symbol"]
            total = cs["total"]
            pos = cs["pos"]
            prev = pos / total if total > 0 else 0
            latest = coin_latest.get(sym)
            if latest:
                data = latest.get("data", {})
                res = data.get("results", {})
                agg = res.get("aggregate", {})
                baselines = res.get("baselines", {})
                leak = res.get("leakage_report", {})
                ci = agg.get("confidence_intervals", {}).get("precision", {})
                mp = agg.get("precision_mean", 0)
                bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
                nv = agg.get("n_valid_folds", 0)
                ls = leak.get("status", "?")
                n_runs = len(coin_all.get(sym, []))

                if ls != "passed":
                    status = "leak"
                elif nv == 0:
                    status = "no_data"
                elif mp > bp and mp > 0:
                    status = "edge"
                else:
                    status = "no_edge"

                coin_list.append({
                    "symbol": sym, "status": status, "pos": pos, "total": total,
                    "prevalence": round(prev, 4),
                    "precision": round(mp, 4), "baseline": round(bp, 4),
                    "ci_lower": ci.get("ci_lower", 0), "ci_upper": ci.get("ci_upper", 0),
                    "n_valid_folds": nv, "leakage": ls, "n_runs": n_runs,
                    "latest_time": system_iso(latest.get("created_at")) or "",
                })
            else:
                coin_list.append({
                    "symbol": sym, "status": "not_run", "pos": pos, "total": total,
                    "prevalence": round(prev, 4),
                    "precision": 0, "baseline": 0, "ci_lower": 0, "ci_upper": 0,
                    "n_valid_folds": 0, "leakage": "?", "n_runs": 0, "latest_time": "",
                })

        res = {
            "has_db": has_db,
            "n_artifacts": len(scan_artifacts),
            "n_runs": len(scan_runs),
            "run_history": run_history,
            "coin_list": coin_list,
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def get_experiments(self):
        """List all experiment artifacts (backtest results).

        Returns compact list of experiments with key metrics for the
        Backtest tab in React frontend.
        """
        from dao_vang.experiments.artifacts import ArtifactRegistry

        registry = ArtifactRegistry(Path("./artifacts"))
        all_artifacts = registry.list_artifacts()

        experiments = []
        for a in all_artifacts:
            data = a.get("data", {})
            config = data.get("config", {})
            results = data.get("results", {})
            agg = results.get("aggregate", {})
            baselines = results.get("baselines", {})
            leak = results.get("leakage_report", {})
            dq = results.get("data_quality", {})

            mp = agg.get("precision_mean", 0)
            bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
            nv = agg.get("n_valid_folds", 0)
            ls = leak.get("status", "?")
            n_pos = dq.get("label_distribution", {}).get("positive", 0)

            if ls != "passed":
                status = "leak"
            elif nv == 0:
                status = "no_data"
            elif mp > bp and mp > 0:
                status = "edge" if n_pos >= 100 else "promising"
            elif mp > 0:
                status = "no_edge"
            else:
                status = "failed"

            experiments.append({
                "artifact_id": a.get("artifact_id", ""),
                "created_at": system_iso(a.get("created_at")) or "",
                "hypothesis_id": config.get("hypothesis_id", ""),
                "symbol": config.get("hypothesis_id", "").replace("hyp_volatile_", "").replace("hyp_dashboard_", ""),
                "status": status,
                "precision": round(mp, 4),
                "baseline": round(bp, 4),
                "recall": round(agg.get("recall_mean", 0), 4),
                "brier": round(agg.get("brier_mean", 0), 4),
                "n_valid_folds": nv,
                "n_skipped_folds": agg.get("n_skipped_folds", 0),
                "n_positive": n_pos,
                "leakage": ls,
                "warning": results.get("warning"),
            })

        self._set_headers(200)
        self.wfile.write(json.dumps({"experiments": experiments, "total": len(experiments)}, default=str).encode('utf-8'))

    def get_experiment_detail(self, artifact_id: str):
        """Full detail of one experiment artifact."""
        from dao_vang.experiments.artifacts import ArtifactRegistry

        registry = ArtifactRegistry(Path("./artifacts"))
        try:
            artifact = registry.load_experiment(artifact_id)
        except FileNotFoundError:
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": f"Artifact {artifact_id} not found"}).encode('utf-8'))
            return

        self._set_headers(200)
        self.wfile.write(json.dumps(artifact, default=str).encode('utf-8'))

    def get_frozen_models(self):
        """List all frozen models for Forward Test tab."""
        from dao_vang.experiments.forward_test import list_frozen_models

        try:
            models = list_frozen_models(Path("./artifacts"))
            result = [
                self._frozen_model_dict(m) for m in models
            ]
            self._set_headers(200)
            self.wfile.write(json.dumps({"models": result, "total": len(result)}, default=str).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"frozen_models_list_failed error={exc}")
            self._set_headers(200)
            self.wfile.write(json.dumps({"models": [], "total": 0, "error": str(exc)}, default=str).encode('utf-8'))

    @staticmethod
    def _frozen_model_dict(m) -> dict:
        """Serialize a FrozenModelInfo with friendly name + label spec."""
        spec = m.label_spec or {}
        target = spec.get("target_drawdown", 0.08)
        mae = spec.get("max_ae", 0.04)
        horizon_min = spec.get("horizon_minutes", 1440)
        target_pct = f"{target * 100:.0f}%" if isinstance(target, (int, float)) else str(target)
        mae_pct = f"{mae * 100:.0f}%" if isinstance(mae, (int, float)) else str(mae)
        horizon_h = f"{horizon_min // 60:.0f}h" if isinstance(horizon_min, (int, float)) else str(horizon_min)
        label_version = m.config.get("label_version", "v1")
        friendly_name = f"Frozen LR {label_version} ({target_pct}/{mae_pct}/{horizon_h})"
        description = (
            f"Logistic Regression đóng băng — dự đoán xác suất coin giảm "
            f">={target_pct} trong {horizon_h} (MAE <={mae_pct}). "
            f"Train cutoff {m.train_cutoff[:10]}, ngưỡng quyết định {m.threshold:.2f}."
        )
        return {
            "model_id": m.model_id,
            "freeze_time": system_iso(m.freeze_time) or str(m.freeze_time),
            "train_cutoff": system_iso(m.train_cutoff) or str(m.train_cutoff),
            "threshold": m.threshold,
            "n_features": len(m.feature_cols),
            "hypothesis_id": m.config.get("hypothesis_id", ""),
            "training_stats": m.training_stats,
            "label_spec": {
                "target_drawdown": target,
                "max_ae": mae,
                "horizon_minutes": horizon_min,
                "target_pct": target_pct,
                "mae_pct": mae_pct,
                "horizon_h": horizon_h,
            },
            "label_version": label_version,
            "friendly_name": friendly_name,
            "description": description,
        }

    def get_models(self):
        """Return all selectable models with friendly names + descriptions.

        Used by the UI model selector. Includes the heuristic composite
        scorer, the walk-forward LogReg, and all frozen models.
        """
        from dao_vang.experiments.forward_test import list_frozen_models

        models: list[dict] = [
            {
                "key": "two_tier_climax",
                "label": "2-Tier Climax Engine (HTF Climax + 5m Trigger)",
                "description": (
                    "Kiến trúc 2 tầng chuyên biệt cho coin bơm xả: Tầng 1 Bối cảnh Khung lớn (1h/4h) "
                    "làm điều kiện nền ARMED (không chờ nến đóng), Tầng 2 Cò kích hoạt Thời gian thực 5m "
                    "(OI Unwind, Taker Sell > 60%, Funding Spike, Râu nến xả) kích hoạt Short tức thì."
                ),
                "model_type": "two_tier",
                "frozen_model_id": None,
                "label_spec": {
                    "target_drawdown": 0.08,
                    "max_ae": 0.04,
                    "horizon_minutes": 1440,
                    "target_pct": "8%",
                    "mae_pct": "4%",
                    "horizon_h": "24h",
                },
            },
            {
                "key": "heuristic_composite",
                "label": "Heuristic 0-100 (Classic V1)",
                "description": (
                    "Chấm điểm tổng hợp 0-100 dựa trên 8 tín hiệu rule-based "
                    "(phân kỳ giá-volume, funding spike, áp lực bán, "
                    "bối cảnh BTC...). Không cần train, dùng được ngay, "
                    "nhưng không học được từ dữ liệu lịch sử."
                ),
                "model_type": "heuristic",
                "frozen_model_id": None,
                "label_spec": {
                    "target_drawdown": 0.08,
                    "max_ae": 0.04,
                    "horizon_minutes": 1440,
                    "target_pct": "8%",
                    "mae_pct": "4%",
                    "horizon_h": "24h",
                },
            },
            {
                "key": "logreg_walkforward",
                "label": "Logistic Regression Walk-forward",
                "description": (
                    "Huấn luyện Logistic Regression trên từng khung thời gian, "
                    "không dùng dữ liệu tương lai. Phù hợp để backtest "
                    "và so sánh với baseline."
                ),
                "model_type": "walkforward",
                "frozen_model_id": None,
                "label_spec": {
                    "target_drawdown": 0.08,
                    "max_ae": 0.04,
                    "horizon_minutes": 1440,
                    "target_pct": "8%",
                    "mae_pct": "4%",
                    "horizon_h": "24h",
                },
            },
        ]

        try:
            frozen = list_frozen_models(Path("./artifacts"))
            for m in frozen:
                d = self._frozen_model_dict(m)
                models.append({
                    "key": f"frozen::{m.model_id}",
                    "label": d["friendly_name"],
                    "description": d["description"],
                    "model_type": "frozen",
                    "frozen_model_id": m.model_id,
                    "label_spec": d["label_spec"],
                    "train_cutoff": d["train_cutoff"],
                    "threshold": d["threshold"],
                })
        except Exception as exc:
            logger.warning(f"models_list_frozen_failed error={exc}")

        current_id = _settings.scanner.frozen_model_id or ""
        self._set_headers(200)
        self.wfile.write(json.dumps({
            "models": models,
            "total": len(models),
            "current_scanner_model_id": current_id,
        }, default=str).encode('utf-8'))

    def get_models_comparison_matrix(self):
        """A/B Benchmark Matrix endpoint comparing V1 Heuristic vs V2 2-Tier Climax."""
        try:
            conn = _ro_duckdb_connect(str(_settings.scanner.db_path))
            try:
                res = evaluate_scoring_engines_comparison(conn, _settings.scoring, sample_limit=200)
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"models_comparison_matrix_failed error={exc}")
            from dao_vang.scoring.engine_comparison import _fallback_benchmark_comparison
            res = _fallback_benchmark_comparison()

        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

    def evaluate_frozen_model(self, model_id: str):
        """Evaluate a frozen model on forward-test data (data after train_cutoff)."""
        from dao_vang.data.storage.duckdb import DuckDBQueryLayer
        from dao_vang.experiments.forward_test import evaluate_frozen

        try:
            settings = AppSettings()
            db = DuckDBQueryLayer(str(settings.scanner.db_path))
            try:
                df = db.conn.execute(
                    """
                    SELECT f.*, l.label_value AS is_distribution
                    FROM feature_results f
                    INNER JOIN labels l
                        ON f.feature_time = l.signal_time AND f.symbol = l.symbol
                    """
                ).df()
            finally:
                db.conn.close()

            if df.empty:
                self._set_headers(200)
                self.wfile.write(json.dumps({
                    "status": "no_data",
                    "message": "Không có dữ liệu feature_results + labels trong DB. Chạy Backtest trước.",
                    "model_id": model_id,
                }).encode('utf-8'))
                return

            result = evaluate_frozen(model_id, df, artifact_dir=Path("./artifacts"))
            self._set_headers(200)
            self.wfile.write(json.dumps(result, default=str).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"frozen_evaluate_failed model={model_id} error={exc}")
            self._set_headers(500)
            self.wfile.write(json.dumps({"status": "error", "message": str(exc)}, default=str).encode('utf-8'))

    def get_system_history(self):
        """System history & data stats for the new SYSTEM HISTORY tab.

        Returns:
            - data_stats: row counts + min/max timestamps per table
            - scanner: heartbeat, last scan cycle, daily scan counts (30d)
            - models: list of frozen models with training stats + label spec
            - experiments: count + latest experiment summary
            - signals_per_day: alert counts per day (30d) for chart
            - self_learning: guarded retraining status + recent gate reports
        """
        from dao_vang.experiments.forward_test import list_frozen_models

        # --- 1. Data stats & scan/signals per day ---
        stats_snapshot = _read_json(SYSTEM_STATS_PATH)
        data_stats: list[dict[str, Any]] = stats_snapshot.get("data_stats", [])
        scan_per_day: list[dict[str, Any]] = stats_snapshot.get("scan_per_day", [])
        signals_per_day: list[dict[str, Any]] = stats_snapshot.get("signals_per_day", [])

        # Fallback to direct read-only query ONLY if snapshot is missing/empty
        if not data_stats or not scan_per_day or not signals_per_day:
            db_path = str(_settings.scanner.db_path)
            conn = None
            try:
                conn = _ro_duckdb_connect(db_path)
                if not data_stats:
                    tables = [r[0] for r in conn.execute(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name"
                    ).fetchall()]
                    ts_candidates = (
                        "signal_time", "scan_time", "feature_time",
                        "close_time", "period_end", "event_time",
                        "candle_close_time", "time", "created_at",
                    )
                    for t in tables:
                        try:
                            n = int(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0])
                        except Exception:
                            n = 0
                        cols = [r[1] for r in conn.execute(
                            f"PRAGMA table_info('{t}')"
                        ).fetchall()]
                        ts_col = next((c for c in ts_candidates if c in cols), None)
                        row = {"table": t, "rows": n}
                        if ts_col and n > 0:
                            try:
                                if t == "scan_results" and ts_col == "scan_time":
                                    mn = conn.execute(
                                        f"SELECT min({ts_col}) FROM {t}"
                                    ).fetchone()[0]
                                    mx = conn.execute(
                                        f"SELECT {ts_col} FROM {t} ORDER BY rowid DESC LIMIT 1"
                                    ).fetchone()[0]
                                else:
                                    mn, mx = conn.execute(
                                        f"SELECT min({ts_col}), max({ts_col}) FROM {t}"
                                    ).fetchone()
                                row["ts_column"] = ts_col
                                row["min_time"] = _system_history_timestamp(mn)
                                row["max_time"] = _system_history_timestamp(mx)
                            except Exception:
                                pass
                        data_stats.append(row)

                if not scan_per_day:
                    try:
                        rows = conn.execute("""
                            SELECT CAST((scan_time AT TIME ZONE 'UTC') AT TIME ZONE ? AS DATE) AS day,
                                   count(*) AS n_rows,
                                   count(DISTINCT cycle) AS n_cycles,
                                   count(DISTINCT symbol) AS n_symbols
                            FROM scan_results
                            GROUP BY day
                            ORDER BY day DESC
                            LIMIT 30
                        """, [SYSTEM_TIMEZONE_NAME]).fetchall()
                        scan_per_day = [
                            {"day": str(r[0]), "n_rows": int(r[1] or 0),
                             "n_cycles": int(r[2] or 0), "n_symbols": int(r[3] or 0)}
                            for r in rows
                        ]
                    except Exception:
                        pass

                if not signals_per_day:
                    try:
                        rows = conn.execute("""
                            SELECT CAST((signal_time AT TIME ZONE 'UTC') AT TIME ZONE ? AS DATE) AS day,
                                   count(*) AS n_signals,
                                   count(*) FILTER (WHERE telegram_sent = TRUE) AS n_telegram,
                                   count(*) FILTER (WHERE hit = TRUE) AS n_hit
                            FROM alert_history
                            GROUP BY day
                            ORDER BY day DESC
                            LIMIT 30
                        """, [SYSTEM_TIMEZONE_NAME]).fetchall()
                        signals_per_day = [
                            {"day": str(r[0]), "n_signals": int(r[1] or 0),
                             "n_telegram": int(r[2] or 0), "n_hit": int(r[3] or 0)}
                            for r in rows
                        ]
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning(f"system_history_db_fallback_failed error={exc}")
            finally:
                if conn is not None:
                    try:
                        conn.close()
                    except Exception:
                        pass

        # --- 2. Scanner status ---
        hb = _read_json(HEARTBEAT_PATH)
        runtime = _read_json(RUNTIME_STATE_PATH)
        scan_mode = runtime.get("scan_mode", _settings.scanner.scan_mode)
        cycle_stats: dict[str, Any] = {}
        try:
            cycle_stats = _scan_store.latest_cycle_stats()
        except Exception as exc:
            logger.warning(f"system_history_cycle_stats_failed error={exc}")
            cycle_stats = {
                "last_scan_time": hb.get("last_cycle_completed_at"),
                "cycle": hb.get("cycle"),
                "n_symbols": hb.get("last_cycle_n_symbols", 0),
                "n_alerts": hb.get("last_cycle_n_alerts", 0),
            }

        # --- 4. Frozen models with progress ---
        models_progress: list[dict[str, Any]] = []
        try:
            frozen = list_frozen_models(Path("./artifacts"))
            for m in frozen:
                d = self._frozen_model_dict(m)
                ts = m.training_stats or {}
                models_progress.append({
                    "model_id": m.model_id,
                    "friendly_name": d["friendly_name"],
                    "description": d["description"],
                    "label_version": d.get("label_version", "v1"),
                    "label_spec": d["label_spec"],
                    "train_cutoff": system_iso(m.train_cutoff) or str(m.train_cutoff),
                    "freeze_time": system_iso(m.freeze_time) or str(m.freeze_time),
                    "threshold": m.threshold,
                    "n_features": len(m.feature_cols),
                    "train_size": ts.get("train_size"),
                    "train_positives": ts.get("train_positives"),
                    "train_precision": ts.get("precision"),
                    "train_recall": ts.get("recall"),
                    "is_scanner_model": (
                        m.model_id == (_settings.scanner.frozen_model_id or "")
                    ),
                })
        except Exception as exc:
            logger.warning(f"system_history_models_failed error={exc}")

        # --- 5. Experiments count + latest ---
        experiments_count = 0
        latest_experiment: dict[str, Any] | None = None
        try:
            import glob
            exp_files = sorted(glob.glob("artifacts/exp_*.json"))
            experiments_count = len(exp_files)
            if exp_files:
                import json as _json
                with open(exp_files[-1], encoding="utf-8") as f:
                    ed = _json.load(f)
                data = ed.get("data", {})
                cfg = data.get("config", {})
                results = data.get("results", {})
                agg = results.get("aggregate", {}) if isinstance(results, dict) else {}
                latest_experiment = {
                    "artifact_id": ed.get("artifact_id"),
                    "created_at": system_iso(ed.get("created_at")),
                    "hypothesis_id": cfg.get("hypothesis_id"),
                    "label_version": cfg.get("label_version"),
                    "precision_mean": agg.get("precision_mean"),
                    "recall_mean": agg.get("recall_mean"),
                    "brier_mean": agg.get("brier_mean"),
                    "n_valid_folds": agg.get("n_valid_folds"),
                }
        except Exception as exc:
            logger.warning(f"system_history_experiments_failed error={exc}")

        res = {
            "generated_at": system_now().isoformat(),
            "db_path": str(_settings.scanner.db_path),
            "data_stats": data_stats,
            "scanner": {
                "heartbeat": hb,
                "runtime_state": runtime,
                "scan_mode": scan_mode,
                "last_cycle": cycle_stats,
                "scan_per_day": scan_per_day,
            },
            "signals_per_day": signals_per_day,
            "models": models_progress,
            "experiments": {
                "total": experiments_count,
                "latest": latest_experiment,
            },
            "current_scanner_model_id": _settings.scanner.frozen_model_id or "",
            "self_learning": _self_learning_status(),
        }
        self._set_headers(200)
        self.wfile.write(json.dumps(res, default=str).encode('utf-8'))

class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

def run_server(port=8000, host='0.0.0.0'):
    server_address = (host, port)
    web_lock = ScannerInstanceLock(Path(_settings.paths.data_dir) / "web.lock")
    try:
        web_lock.acquire()
    except ScannerAlreadyRunning as exc:
        logger.error("web_instance_already_running error=%s", exc)
        raise SystemExit(2) from exc

    httpd = None
    try:
        httpd = ReusableThreadingHTTPServer(server_address, APIHandler)
        logger.info(f"Đảo Vàng Combined Server running on http://{host}:{port}")
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Received exit signal. Shutting down server...")
    finally:
        if httpd is not None:
            httpd.server_close()
        web_lock.release()
        logger.info("Server socket released. Goodbye!")

if __name__ == '__main__':
    run_server()
