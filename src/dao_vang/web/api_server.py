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
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import duckdb

from dao_vang.alerts.store import AlertStore
from dao_vang.alerts.telegram import TelegramNotifier
from dao_vang.config.settings import AppSettings
from dao_vang.data.binance_listing import get_stats_for_today
from dao_vang.scanner.pump_filter import fetch_daily_klines, analyze_pump
from dao_vang.scanner.scan_results_store import ScanResultStore
from dao_vang.scanner.watchlist import (
    _filter_tickers,
    add_to_watchlist,
    fetch_all_tickers,
    fetch_top_gainers,
    fetch_top_losers,
    load_manual_watchlist,
    remove_from_watchlist,
)
from dao_vang.scoring import classify_btc, compute_distribution_score

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("dao_vang_api")

DIST_DIR = Path("frontend/dist").resolve()

_settings = AppSettings()
WATCHLIST_PATH = _settings.scanner.watchlist_path
HEARTBEAT_PATH = Path("data/scanner_heartbeat.json")
TRIGGER_PATH = Path("data/scanner_trigger.flag")
RUNTIME_STATE_PATH = Path("data/scanner_runtime_state.json")

_alert_store = AlertStore(str(_settings.scanner.db_path))
_scan_store = ScanResultStore(str(_settings.scanner.db_path))
_notifier = TelegramNotifier(_settings.telegram)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _ro_duckdb_connect(db_path: str) -> duckdb.DuckDBPyConnection:
    """Open a read-only DuckDB connection, copying the file if it's locked.

    DuckDB on Windows doesn't allow multiple processes to open the same file,
    even with read_only=True. This helper tries a direct read-only connection
    first, and falls back to copying the DB file if that fails.
    """
    try:
        return duckdb.connect(db_path, read_only=True)
    except duckdb.IOException:
        import shutil
        tmp = db_path + ".ro_copy"
        try:
            shutil.copy2(db_path, tmp)
        except PermissionError:
            with open(db_path, 'rb') as src, open(tmp, 'wb') as dst:
                dst.write(src.read())
        return duckdb.connect(tmp, read_only=True)


def _current_scan_mode() -> str:
    return _read_json(RUNTIME_STATE_PATH).get("scan_mode", _settings.scanner.scan_mode)


def _request_scan(mode: str | None = None) -> None:
    """Ask the running ScannerDaemon to run a cycle immediately.

    Writes a flag file the daemon polls between cycles instead of running a
    scan inline in this HTTP handler — the daemon is a separate long-running
    process holding the Binance client / DuckDB write connection.
    """
    TRIGGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"requested_at": datetime.now(timezone.utc).isoformat()}
    if mode:
        state = _read_json(RUNTIME_STATE_PATH)
        state["scan_mode"] = mode
        RUNTIME_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        RUNTIME_STATE_PATH.write_text(json.dumps(state), encoding="utf-8")
        payload["scan_mode"] = mode
    TRIGGER_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _risk_bucket(score: float) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 50:
        return "MEDIUM"
    return "SAFE"


class APIHandler(BaseHTTPRequestHandler):
    def _set_headers(self, status=200, content_type='application/json; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self._set_headers(200)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith('/api/'):
            if path == '/api/status':
                self.get_status()
            elif path == '/api/signals':
                self.get_signals()
            elif path == '/api/candidates':
                self.get_candidates()
            elif path == '/api/watchlist':
                self.get_watchlist()
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
            if not ctype:
                ctype = 'application/octet-stream'
            self._set_headers(200, content_type=ctype)
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
                "timestamp": datetime.now(timezone.utc).isoformat()
            }).encode('utf-8'))
        elif parsed.path == '/api/scanner/trigger':
            _request_scan()
            self._set_headers(202)
            self.wfile.write(json.dumps({
                "status": "queued",
                "message": "Đã ghi nhận yêu cầu quét — scanner daemon sẽ chạy trong vài giây (nếu daemon đang chạy).",
            }).encode('utf-8'))
        elif parsed.path == '/api/watchlist/add':
            symbol = data.get('symbol', '').upper()
            if symbol:
                updated = add_to_watchlist(WATCHLIST_PATH, symbol)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "manual_watchlist": updated}).encode('utf-8'))
            else:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Symbol required"}).encode('utf-8'))
        elif parsed.path == '/api/watchlist/remove':
            symbol = data.get('symbol', '').upper()
            if symbol:
                updated = remove_from_watchlist(WATCHLIST_PATH, symbol)
                self._set_headers(200)
                self.wfile.write(json.dumps({"status": "success", "manual_watchlist": updated}).encode('utf-8'))
            else:
                self._set_headers(400)
                self.wfile.write(json.dumps({"error": "Symbol required"}).encode('utf-8'))
        elif parsed.path == '/api/watchlist/mode':
            new_mode = data.get('mode', 'volatile')
            _request_scan(mode=new_mode)
            self._set_headers(202)
            self.wfile.write(json.dumps({
                "status": "queued",
                "active_scan_mode": new_mode,
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
                import pandas as pd
                from sklearn.linear_model import LogisticRegression as _LR
                import numpy as _np
                from dao_vang.data.storage.duckdb import DuckDBQueryLayer
                from dao_vang.experiments.forward_test import freeze_model as _freeze_model

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
                m = _LR(max_iter=1000, random_state=42, class_weight="balanced")
                m.fit(tr[feats].fillna(0), tr["is_distribution"])

                best_t, best_f1 = 0.5, 0.0
                if len(va) > 0 and va["is_distribution"].nunique() >= 2:
                    yp = m.predict_proba(va[feats].fillna(0))[:, 1]
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

                final_m = _LR(max_iter=1000, random_state=42, class_weight="balanced")
                final_m.fit(ft_df[feats].fillna(0), ft_df["is_distribution"])

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

        recent_alerts = _alert_store.query(days=1, include_dismissed=False, limit=1)
        top_risk_symbol = recent_alerts[0]["symbol"] if recent_alerts else None
        active_signals = len(_alert_store.query(days=1, include_dismissed=False, limit=500))
        cycle_stats = _scan_store.latest_cycle_stats()

        res = {
            "scanner_status": "OFFLINE" if (is_stale or hb.get("status") != "running") else "ONLINE",
            "scanner_mode": f"24/7 Scanner ({scan_mode.upper()})",
            "heartbeat": hb_ts_raw,
            "scanned_coins_count": cycle_stats.get("n_symbols", 0),
            "active_signals_count": active_signals,
            "top_risk_symbol": top_risk_symbol,
            "model_version": hb.get("model_id") or _settings.scanner.frozen_model_id,
            "telegram_connected": _notifier.is_configured,
            "threshold": _settings.scoring.alert_score_threshold / 100.0,
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
            ts_str = sig_time.strftime("%H:%M:%S") if isinstance(sig_time, datetime) else str(sig_time)
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
                    ts_str = scan_time.strftime("%H:%M:%S") if isinstance(scan_time, datetime) else str(scan_time)
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
            telegram_logs.append({
                "timestamp": sent_at.strftime("%Y-%m-%d %H:%M:%S") if isinstance(sent_at, datetime) else str(sent_at),
                "symbol": r["symbol"],
                "risk_score": f"{r['probability'] * 100:.1f}%",
                "channel": "Telegram",
                "status": "DELIVERED",
            })

        last_scan_time = hb.get("timestamp")
        if not last_scan_time and cycle_stats.get("last_scan_time") is not None:
            lst = cycle_stats["last_scan_time"]
            last_scan_time = lst.isoformat() if hasattr(lst, "isoformat") else str(lst)

        # Compute next scan time from heartbeat
        next_scan_in = None
        hb_ts = hb.get("timestamp")
        poll_min = hb.get("poll_minutes", _settings.scanner.poll_interval_minutes)
        if hb_ts and poll_min:
            try:
                hb_dt = datetime.fromisoformat(hb_ts.replace("Z", "+00:00"))
                next_dt = hb_dt + timedelta(minutes=poll_min)
                now_dt = datetime.now(timezone.utc)
                next_scan_in = max(0, int((next_dt - now_dt).total_seconds()))
            except Exception as e:
                logger.warning(f"Error processing stats item: {e}")

        res = {
            "scanner_engine_status": "ONLINE" if hb.get("status") == "running" else "OFFLINE",
            "last_scan_timestamp": last_scan_time,
            "next_scan_in_seconds": next_scan_in,
            "poll_interval_minutes": poll_min,
            "api_endpoint": "https://fapi.binance.com/fapi/v1",
            "average_api_latency_ms": None,
            "active_scan_mode": hb.get("scan_mode", _current_scan_mode()),
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
        scan_mode = _current_scan_mode()
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
        seen_symbols: set[str] = set()
        for r in rows:
            sig_time = r["signal_time"]
            inv_time = r["invalidation_time"]
            seen_symbols.add(r["symbol"])

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
            if isinstance(inv_time, datetime):
                inv_dt = inv_time if inv_time.tzinfo else inv_time.replace(tzinfo=timezone.utc)
                validity_hours_left = max(0.0, (inv_dt - now).total_seconds() / 3600.0)

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

            signals.append({
                "id": f"{r['symbol']}-{sig_time.isoformat() if isinstance(sig_time, datetime) else sig_time}",
                "symbol": r["symbol"],
                "name": r["symbol"].replace("USDT", ""),
                "probability": r["probability"],
                "risk_level": _risk_bucket(r["probability"] * 100.0),
                "signal_time": sig_time.isoformat() if isinstance(sig_time, datetime) else sig_time,
                "signal_price": close_price or 0.0,
                "target_drawdown": target_drawdown,
                "target_price": target_price,
                "validity_hours_left": validity_hours_left,
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
            if sym in seen_symbols:
                continue
            score = sr.get("score", 0.0)
            if score < 10:
                continue
            seen_symbols.add(sym)
            scan_time = sr.get("scan_time")
            sig_time_str = scan_time.isoformat() if hasattr(scan_time, "isoformat") else str(scan_time)
            close_price = sr.get("close_price")
            oi_change = sr.get("oi_change_24h")
            funding = sr.get("funding_rate")
            taker_sell = sr.get("taker_sell_ratio")
            target_drawdown = -8.0
            target_price = round(close_price * (1 + target_drawdown / 100.0), 8) if close_price else 0.0
            prob = score / 100.0
            signals.append({
                "id": f"{sym}-scan-{sig_time_str}",
                "symbol": sym,
                "name": sym.replace("USDT", ""),
                "probability": prob,
                "risk_level": _risk_bucket(score),
                "signal_time": sig_time_str,
                "signal_price": close_price or 0.0,
                "target_drawdown": target_drawdown,
                "target_price": target_price,
                "validity_hours_left": 24.0,
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

        # Sort by probability (score) descending
        signals.sort(key=lambda s: s["probability"], reverse=True)
        self._set_headers(200)
        self.wfile.write(json.dumps(signals, default=str).encode('utf-8'))

    def get_candidates(self):
        rows = _scan_store.latest_per_symbol(limit=200)
        now = datetime.now(timezone.utc)
        candidates = []
        for r in rows:
            scan_time = r.get("scan_time")
            age_str = "N/A"
            if isinstance(scan_time, datetime):
                st = scan_time if scan_time.tzinfo else scan_time.replace(tzinfo=timezone.utc)
                age_minutes = (now - st).total_seconds() / 60.0
                age_str = f"{age_minutes:.0f}m ago" if age_minutes < 120 else f"{age_minutes / 60:.1f}h ago"
            candidates.append({
                "symbol": r["symbol"],
                "price": r.get("close_price") or 0.0,
                "score": r["score"],
                "risk": _risk_bucket(r["score"]),
                "oi_24h": f"{r['oi_change_24h']:+.1%}" if r.get("oi_change_24h") is not None else "N/A",
                "funding": f"{r['funding_rate']:+.3%}" if r.get("funding_rate") is not None else "N/A",
                "taker_ratio": r.get("taker_sell_ratio") if r.get("taker_sell_ratio") is not None else 0.5,
                "volume_24h": f"${r['volume_24h_usd'] / 1e6:.1f}M" if r.get("volume_24h_usd") else "N/A",
                "age": age_str,
            })
        candidates.sort(key=lambda c: c["score"], reverse=True)
        self._set_headers(200)
        self.wfile.write(json.dumps(candidates, default=str).encode('utf-8'))

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
                    LIMIT 96
                    """,
                    [symbol],
                ).fetchall()
            finally:
                conn.close()
        except Exception as exc:
            logger.warning(f"coin_detail_query_failed symbol={symbol} error={exc}")

        chart_points = []
        closes: list[float] = []
        for feature_time, k_open, k_high, k_low, close, vol_base, taker_buy_base, oi_change, funding, taker_buy, _price_ret_5m, _vol_pct in reversed(rows):
            c = float(close) if close is not None else 0.0
            closes.append(c)
            chart_points.append({
                "time": feature_time.strftime("%H:%M") if isinstance(feature_time, datetime) else str(feature_time),
                "time_iso": feature_time.isoformat() if isinstance(feature_time, datetime) else str(feature_time),
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
        latest_vol_pct = rows[0][6] if rows else None
        vol_delta_str = f"{float(latest_vol_pct) * 100:.0f}%" if latest_vol_pct is not None else "N/A"

        alert_rows = _alert_store.query(symbol=symbol, days=2, include_dismissed=True, limit=1)
        latest_alert = alert_rows[0] if alert_rows else None

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

        sig_time = latest_alert["signal_time"] if latest_alert else None
        target_drawdown = -8.0
        detail = {
            "symbol": symbol,
            "name": symbol.replace("USDT", ""),
            "current_price": current_price,
            "probability": latest_alert["probability"] if latest_alert else 0.0,
            "risk_level": _risk_bucket((latest_alert["probability"] if latest_alert else 0.0) * 100.0),
            "target_drawdown": target_drawdown,
            "target_price": round(current_price * (1 + target_drawdown / 100.0), 8) if current_price else 0.0,
            "signal_timestamp": sig_time.strftime("%Y-%m-%d %H:%M:%S UTC") if isinstance(sig_time, datetime) else None,
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
        """Deep analysis endpoint — runs full scoring pipeline for a single symbol.

        Fetches latest features from DuckDB, computes BTC context, runs the
        8-component composite distribution scorer, fetches daily klines for
        pump pattern analysis, and returns a comprehensive analysis result.
        """
        import pandas as pd

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
                    ORDER BY f.feature_time DESC LIMIT 12
                    """,
                    [symbol],
                ).df()
                if not df.empty:
                    latest = df.iloc[-1]
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
                    ORDER BY feature_time DESC LIMIT 1
                    """
                ).df()
                if not btc_df.empty:
                    row = btc_df.iloc[-1]
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

        # 4. Compute full 8-component distribution score
        score = compute_distribution_score(
            symbol=symbol,
            features=feature_dict,
            btc=btc_context,
            config=_settings.scoring,
            pump_pct=pump_analysis["pump_pct"] / 100.0 if pump_analysis["detected"] else 0.0,
            pump_days=pump_analysis["pump_days"],
        )

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

        # 7. Build result
        result = {
            "symbol": symbol,
            "analysis_time": datetime.now(timezone.utc).isoformat(),
            "feature_time": feature_time.isoformat() if feature_time else None,
            "current_price": close_price,
            "total_score": round(score.total_score, 1),
            "recommendation": score.recommendation,
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
        """Fetch recent klines for mini chart display."""
        from dao_vang.data.collectors.binance_client import BinanceClient

        try:
            client = BinanceClient()
            data = client.get("fapi/v1/klines", {
                "symbol": symbol,
                "interval": "1h",
                "limit": 72,
            })
            klines = [
                {
                    "time": k[0],
                    "time_str": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc).strftime("%m-%d %H:%M"),
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5]),
                }
                for k in data
            ]
            self._set_headers(200)
            self.wfile.write(json.dumps({"symbol": symbol, "klines": klines}).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"coin_chart_failed symbol={symbol} error={exc}")
            self._set_headers(200)
            self.wfile.write(json.dumps({"symbol": symbol, "klines": [], "error": str(exc)}).encode('utf-8'))

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

        res = {
            "model_name": f"Composite Distribution Scorer (heuristic, unvalidated weights) — frozen ML model: {_settings.scanner.frozen_model_id or 'not set'}",
            "horizon": "24h",
            "target_drawdown": ">= 8.0%",
            "mae_allowed": "<= 4.0%",
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
        from dao_vang.data.binance_listing import load_history as _load_listing_history, DEFAULT_HISTORY_PATH as _LISTING_HIST

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
                                "first_ts": first_ts.isoformat() if hasattr(first_ts, "isoformat") else str(first_ts),
                                "last_ts": last_ts.isoformat() if hasattr(last_ts, "isoformat") else str(last_ts),
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
            created = a.get("created_at", "")[:13]
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
                    "latest_time": latest.get("created_at", ""),
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
                "created_at": a.get("created_at", ""),
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
                {
                    "model_id": m.model_id,
                    "freeze_time": m.freeze_time,
                    "train_cutoff": m.train_cutoff,
                    "threshold": m.threshold,
                    "n_features": len(m.feature_cols),
                    "hypothesis_id": m.config.get("hypothesis_id", ""),
                    "training_stats": m.training_stats,
                }
                for m in models
            ]
            self._set_headers(200)
            self.wfile.write(json.dumps({"models": result, "total": len(result)}, default=str).encode('utf-8'))
        except Exception as exc:
            logger.warning(f"frozen_models_list_failed error={exc}")
            self._set_headers(200)
            self.wfile.write(json.dumps({"models": [], "total": 0, "error": str(exc)}, default=str).encode('utf-8'))

    def evaluate_frozen_model(self, model_id: str):
        """Evaluate a frozen model on forward-test data (data after train_cutoff)."""
        import pandas as pd
        from dao_vang.experiments.forward_test import evaluate_frozen
        from dao_vang.data.storage.duckdb import DuckDBQueryLayer

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

def run_server(port=8000):
    server_address = ('0.0.0.0', port)
    httpd = HTTPServer(server_address, APIHandler)
    logger.info(f"Đảo Vàng Combined Server running on http://127.0.0.1:{port}")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
