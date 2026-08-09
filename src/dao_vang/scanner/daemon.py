# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false
"""24/7 scanner daemon — polls Binance, scores with frozen model, alerts via Telegram.

Architecture (per ADR 0001):
    ┌───────────────────────────────────────┐
    │  Scanner loop (every poll_interval)   │
    │  1. build_scan_list (watchlist+gainers)│
    │  2. for each symbol:                  │
    │     a. collect latest data (incremental)│
    │     b. normalize → timeline → features│
    │     c. score_frozen (frozen model)    │
    │     d. filter by alert_levels         │
    │     e. cooldown check (AlertStore)    │
    │     f. send Telegram if not cooldown  │
    │     g. save to alert_history          │
    │  3. sleep poll_interval_minutes       │
    └───────────────────────────────────────┘

Constraints:
- Frozen model only — no retraining in loop.
- Point-in-time correct — features use available_time <= feature_time.
- Cooldown per symbol to avoid spam.
- No silent fallback — errors logged, not swallowed.
"""

from __future__ import annotations

import json
import signal
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd  # type: ignore[reportMissingTypeStubs]

from dao_vang.alerts.store import AlertRecord, AlertStore
from dao_vang.alerts.telegram import TelegramNotifier
from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.coingecko import cross_reference
from dao_vang.data.collectors.funding import FundingCollector
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.collectors.open_interest import OpenInterestCollector
from dao_vang.data.collectors.ratios import GlobalRatioCollector, TopRatioCollector
from dao_vang.data.collectors.taker import TakerRatioCollector
from dao_vang.data.pipeline import (
    build_raw_timeline,
    get_incremental_start,
    process_raw_to_parquet,
)
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.experiments.forward_test import load_frozen_model
from dao_vang.features.builder import build_features
from dao_vang.logging import get_logger
from dao_vang.scanner.outcomes import resolve_pending_outcomes
from dao_vang.scanner.pump_filter import PumpCandidate, scan_pumps
from dao_vang.scanner.scan_results_store import ScanResultRecord, ScanResultStore
from dao_vang.scanner.watchlist import build_scan_list
from dao_vang.scoring import classify_btc, compute_distribution_score

logger = get_logger(__name__)

_COLLECTORS = [
    ("klines", "Nến 5m", KlinesCollector),
    ("funding", "Funding Rate", FundingCollector),
    ("open_interest", "Open Interest", OpenInterestCollector),
    ("taker_ratio", "Taker Volume", TakerRatioCollector),
    ("global_ratio", "Global L/S", GlobalRatioCollector),
    ("top_ratio", "Top L/S", TopRatioCollector),
]


class ScannerDaemon:
    """24/7 scanner loop using a frozen model + Telegram alerts.

    Args:
        settings: AppSettings with scanner + telegram config.
    """

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._scanner_cfg = settings.scanner
        self._notifier = TelegramNotifier(settings.telegram)
        self._alert_store = AlertStore(str(self._scanner_cfg.db_path))
        self._scan_result_store = ScanResultStore(str(self._scanner_cfg.db_path))
        self._running = True
        self._cycle_count = 0
        self._heartbeat_path = Path("data/scanner_heartbeat.json")
        self._trigger_path = Path("data/scanner_trigger.flag")
        self._runtime_state_path = Path("data/scanner_runtime_state.json")

        # Validate frozen model
        model_id = self._scanner_cfg.frozen_model_id
        if not model_id:
            raise ValueError(
                "scanner.frozen_model_id not set. "
                "Run `dao-vang experiment freeze` first, then set in config."
            )
        self._frozen_info = load_frozen_model(
            model_id, Path(self._scanner_cfg.artifact_dir)
        )
        logger.info(
            "scanner_init",
            model_id=model_id,
            threshold=self._frozen_info.threshold,
            train_cutoff=self._frozen_info.train_cutoff,
        )

    def stop(self, *_: Any) -> None:
        """Graceful shutdown signal handler."""
        logger.info("scanner_stop_requested")
        self._running = False

    def _write_heartbeat(self, status: str = "running") -> None:
        """Write heartbeat file for web UI to detect scanner status."""
        try:
            self._heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            self._heartbeat_path.write_text(
                json.dumps(
                    {
                        "status": status,
                        "cycle": self._cycle_count,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "poll_minutes": self._scanner_cfg.poll_interval_minutes,
                        "model_id": self._scanner_cfg.frozen_model_id,
                        "scan_mode": self._scanner_cfg.scan_mode,
                        "max_coins": self._scanner_cfg.max_coins,
                    },
                ),
                encoding="utf-8",
            )
        except Exception as e:
            logger.debug(f"Heartbeat failed: {e}")  # heartbeat is best-effort, don't crash scanner

    def run(self) -> None:
        """Main loop — runs until stopped (Ctrl+C or signal)."""
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        logger.info(
            "scanner_start",
            poll_minutes=self._scanner_cfg.poll_interval_minutes,
            max_coins=self._scanner_cfg.max_coins,
            alert_levels=self._scanner_cfg.alert_levels,
            scan_mode=self._scanner_cfg.scan_mode,
            min_change_pct=self._scanner_cfg.min_price_change_pct,
        )
        self._write_heartbeat("running")

        while self._running:
            self._cycle_count += 1
            cycle_start = time.perf_counter()
            try:
                self._run_cycle()
            except Exception as exc:
                logger.error(
                    "scanner_cycle_error",
                    cycle=self._cycle_count,
                    error=str(exc),
                )

            elapsed = time.perf_counter() - cycle_start
            sleep_seconds = self._scanner_cfg.poll_interval_minutes * 60
            logger.info(
                "scanner_cycle_done",
                cycle=self._cycle_count,
                elapsed_s=round(elapsed, 1),
                sleep_s=sleep_seconds,
            )
            self._write_heartbeat("running")

            # Sleep in small increments so we can respond to stop signal AND
            # an on-demand scan trigger (e.g. "Quét ngay" button in the web UI
            # writes data/scanner_trigger.flag instead of faking a response).
            slept = 0
            while self._running and slept < sleep_seconds:
                if self._trigger_path.exists():
                    logger.info("scanner_manual_trigger_detected")
                    break
                time.sleep(min(5, sleep_seconds - slept))
                slept += 5

        self._write_heartbeat("stopped")
        logger.info("scanner_stopped", cycles=self._cycle_count)

    def _consume_trigger(self) -> None:
        """Remove the manual-trigger flag file (idempotent, best-effort)."""
        try:
            self._trigger_path.unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"Exception in scanner daemon loop: {e}")

    def _apply_runtime_overrides(self) -> None:
        """Apply scan_mode overrides written by the web UI at runtime.

        The API server cannot mutate the running daemon's in-memory config
        directly (separate process), so it writes desired overrides to
        ``scanner_runtime_state.json`` and this reads them each cycle.
        """
        if not self._runtime_state_path.exists():
            return
        try:
            state = json.loads(self._runtime_state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("scanner_runtime_state_read_failed", error=str(exc))
            return
        new_mode = state.get("scan_mode")
        if new_mode and new_mode != self._scanner_cfg.scan_mode:
            logger.info(
                "scanner_scan_mode_override",
                old_mode=self._scanner_cfg.scan_mode,
                new_mode=new_mode,
            )
            self._scanner_cfg.scan_mode = new_mode

    def _run_cycle(self) -> None:
        """One scan cycle: build list → pump filter → collect → score → alert."""
        self._consume_trigger()
        self._apply_runtime_overrides()

        # 1. Build scan list (watchlist + auto market scan by mode)
        symbols = build_scan_list(self._scanner_cfg)
        if not symbols:
            logger.warning("scanner_no_symbols", scan_mode=self._scanner_cfg.scan_mode)
            return

        logger.info(
            "scanner_cycle_start",
            cycle=self._cycle_count,
            n_symbols=len(symbols),
            scan_mode=self._scanner_cfg.scan_mode,
            max_coins=self._scanner_cfg.max_coins,
            min_change_pct=self._scanner_cfg.min_price_change_pct,
        )

        # 1b. Pump filter — find coins that pumped 50-300% in 1-5 days
        pump_candidates = scan_pumps(self._settings.pump_filter, symbols)
        pump_map: dict[str, PumpCandidate] = {c.symbol: c for c in pump_candidates}
        # If pump filter finds candidates, prioritize them; else use all symbols
        score_symbols = list(pump_map.keys()) if pump_map else symbols
        logger.info(
            "pump_filter_result",
            n_scanned=len(symbols),
            n_pump_candidates=len(pump_candidates),
            n_to_score=len(score_symbols),
            pump_symbols=[c.symbol for c in pump_candidates[:5]],  # top 5 for log
        )

        # 2. Collect + normalize + timeline + features (shared across symbols)
        now = datetime.now(timezone.utc)
        start_dt = now - timedelta(days=self._scanner_cfg.history_days)
        self._collect_all(score_symbols, start_dt, now)
        self._normalize_and_timeline()

        # 2b. Self-learning feedback loop: resolve hit/miss for alerts whose
        # 24h horizon has now completed (was previously dead code — see
        # AlertStore.update_hits — nothing ever called it).
        db = DuckDBQueryLayer(str(self._scanner_cfg.db_path))
        try:
            n_resolved = resolve_pending_outcomes(self._alert_store, db)
            if n_resolved:
                logger.info("scanner_outcomes_resolved", n_resolved=n_resolved)
        except Exception as exc:
            logger.warning("scanner_outcome_resolution_failed", error=str(exc))

        # 3. Build features
        build_features(db, "raw_timeline", "feature_results")

        # 3b. Compute BTC context for this cycle
        btc_context = self._compute_btc_context(db)

        # 4. Score with composite scorer + alert
        n_alerts_sent = 0
        for symbol in score_symbols:
            try:
                pump_cand = pump_map.get(symbol)
                n_alerts_sent += self._score_and_alert_composite(
                    symbol, db, btc_context, pump_cand
                )
            except Exception as exc:
                logger.error("scanner_symbol_error", symbol=symbol, error=str(exc))

        logger.info(
            "scanner_cycle_summary",
            cycle=self._cycle_count,
            n_symbols=len(score_symbols),
            n_alerts_sent=n_alerts_sent,
        )

    def _compute_btc_context(self, db: DuckDBQueryLayer):
        """Compute BTC context from latest BTC features."""
        try:
            btc_df = db.conn.execute(
                """
                SELECT * FROM feature_results
                WHERE symbol = 'BTCUSDT'
                ORDER BY feature_time DESC LIMIT 1
                """
            ).df()
            if btc_df.empty:
                logger.warning("btc_no_features")
                return classify_btc(0.0, 0.0, 0.0, self._settings.scoring)
            row = btc_df.iloc[-1]
            return classify_btc(
                btc_ret_24h=float(row.get("price_ret_24h", 0.0)),
                btc_ret_4h=float(row.get("price_ret_4h", 0.0)),
                btc_ret_1h=float(row.get("price_ret_5m", 0.0)),
                config=self._settings.scoring,
            )
        except Exception as exc:
            logger.warning("btc_context_failed", error=str(exc))
            return classify_btc(0.0, 0.0, 0.0, self._settings.scoring)

    def _collect_all(
        self, symbols: list[str], start_dt: datetime, end_dt: datetime
    ) -> None:
        """Incremental collect for all symbols across all data types."""
        client = BinanceClient()
        run_id = f"scan_{int(time.time())}"
        data_dir = Path(self._settings.paths.data_dir)

        for data_type, _label, collector_cls in _COLLECTORS:
            collector = collector_cls(client, self._settings)
            for symbol in symbols:
                self._settings.binance.symbol = symbol
                inc_start = get_incremental_start(data_dir, data_type, symbol, start_dt)
                if inc_start > end_dt:
                    continue
                try:
                    collector.collect(inc_start, end_dt, run_id)
                except Exception as exc:
                    logger.warning(
                        "scanner_collect_skip",
                        symbol=symbol,
                        data_type=data_type,
                        error=str(exc),
                    )

    def _normalize_and_timeline(self) -> None:
        """Normalize raw → parquet → build timeline views."""
        process_raw_to_parquet(self._settings)
        db = DuckDBQueryLayer(str(self._scanner_cfg.db_path))
        build_raw_timeline(db, self._settings)

    def _score_and_alert_composite(
        self,
        symbol: str,
        db: DuckDBQueryLayer,
        btc_context: Any,
        pump_candidate: PumpCandidate | None,
    ) -> int:
        """Score one symbol with composite scorer, send Telegram if score >= threshold.

        Returns number of alerts sent (0 or 1).
        """
        # Get latest features for this symbol — JOIN kline to get close price
        df = db.conn.execute(
            """
            SELECT f.*, k.close, k.volume_quote AS volume_24h
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

        if df.empty:
            logger.debug("scanner_no_features", symbol=symbol)
            return 0

        latest = df.iloc[-1]
        feature_dict: dict[str, Any] = {}
        for col in df.columns:
            val = latest[col]
            if pd.notna(val):
                feature_dict[col] = val

        pump_pct = pump_candidate.pump_pct if pump_candidate else 0.0
        pump_days = pump_candidate.pump_days if pump_candidate else 0

        # Compute composite score
        score = compute_distribution_score(
            symbol=symbol,
            features=feature_dict,
            btc=btc_context,
            config=self._settings.scoring,
            pump_pct=pump_pct,
            pump_days=pump_days,
        )

        close_price: float | None = (
            float(df.iloc[-1].get("close", 0))  # type: ignore[union-attr]
            if "close" in df.columns
            else None
        )

        # Persist EVERY scored symbol (Constitution Khối 6: record every
        # signal, not just the ones that crossed the alert threshold). This
        # is what powers the real "candidates" list in the UI instead of
        # hardcoded mock data.
        try:
            self._scan_result_store.save_batch(
                [
                    ScanResultRecord(
                        scan_time=datetime.now(timezone.utc),
                        symbol=symbol,
                        score=score.total_score,
                        recommendation=score.recommendation,
                        close_price=close_price,
                        price_change_24h=float(feature_dict.get("price_ret_24h", 0.0) or 0.0),
                        oi_change_24h=float(feature_dict.get("oi_change_24h", 0.0) or 0.0),
                        funding_rate=float(feature_dict.get("funding_rate_raw", 0.0) or 0.0),
                        taker_sell_ratio=1.0
                        - float(feature_dict.get("taker_buy_ratio", 0.5) or 0.5),
                        volume_24h_usd=float(feature_dict.get("volume_24h", 0.0) or feature_dict.get("volume_base", 0.0) or 0.0),
                        pump_pct=pump_pct,
                        pump_days=pump_days,
                        cycle=self._cycle_count,
                    )
                ]
            )
        except Exception as exc:
            logger.warning("scan_result_save_failed", symbol=symbol, error=str(exc))

        # Filter by score threshold
        if score.total_score < self._settings.scoring.alert_score_threshold:
            logger.debug(
                "scanner_score_below_threshold",
                symbol=symbol,
                score=score.total_score,
                threshold=self._settings.scoring.alert_score_threshold,
            )
            return 0

        # Cooldown check
        if self._alert_store.is_in_cooldown(symbol, self._scanner_cfg.cooldown_minutes):
            logger.debug("scanner_cooldown_skip", symbol=symbol)
            return 0

        # Build timestamps
        sig_raw = pd.Timestamp(latest.get("feature_time", datetime.now(timezone.utc)))
        if pd.isna(sig_raw):
            logger.warning("scanner_nat_timestamp", symbol=symbol)
            return 0
        sig_time: datetime = sig_raw.to_pydatetime()  # type: ignore[assignment]
        if sig_time.tzinfo is None:
            sig_time = sig_time.replace(tzinfo=timezone.utc)
        inv_time = sig_time + timedelta(hours=24)

        # Cross-reference with CoinGecko if enabled — flagged explicitly
        # (not just logged) so the alert record + UI can surface it.
        price_mismatch = False
        if self._settings.coingecko.enabled and close_price:
            xref = cross_reference(
                binance_price=close_price,
                binance_volume_usd=float(feature_dict.get("volume_base", 0) or 0),
                symbol=symbol,
                config=self._settings.coingecko,
            )
            if xref.flag == "PRICE_MISMATCH":
                price_mismatch = True
                logger.warning(
                    "price_mismatch_detected",
                    symbol=symbol,
                    binance=close_price,
                    coingecko=xref.coingecko_price,
                    diff=xref.price_diff_pct,
                )

        # Self-learning feedback: attach the *empirical* historical precision
        # for this risk level (from resolved outcomes) as evidence quality,
        # instead of only showing the unvalidated heuristic score.
        risk_level = "CAO" if score.total_score >= 80 else "TRUNG BÌNH"
        evidence = self._alert_store.precision_by_risk_level(days=30).get(risk_level, {})
        evidence_precision = evidence.get("precision")
        evidence_n_judged = evidence.get("n_judged", 0)

        components_payload: list[dict[str, Any]] = [
            {
                "name": c.name,
                "raw_value": c.raw_value,
                "score": c.score,
                "weight": c.weight,
                "weighted_score": c.weighted_score,
                "explanation": c.explanation,
            }
            for c in score.components
        ]
        if price_mismatch:
            components_payload.append(
                {
                    "name": "price_cross_reference",
                    "raw_value": None,
                    "score": 0.0,
                    "weight": 0.0,
                    "weighted_score": 0.0,
                    "explanation": "PRICE_MISMATCH: giá Binance lệch đáng kể so với CoinGecko — kiểm tra lại trước khi tin tưởng alert này.",
                }
            )

        # Save to alert history
        record = AlertRecord(
            signal_time=sig_time,
            symbol=symbol,
            probability=score.total_score / 100.0,  # store score as probability
            risk_level=risk_level,
            threshold=self._settings.scoring.alert_score_threshold / 100.0,
            close_price=close_price,
            model_id=self._frozen_info.model_id,
            invalidation_time=inv_time,
            components_json=json.dumps(components_payload),
            evidence_precision=evidence_precision,
            evidence_n_judged=evidence_n_judged,
        )
        self._alert_store.save(record)

        # Build top signals for Telegram
        top_signals = [
            (c.name, c.score, c.weight, c.explanation) for c in score.top_signals
        ]

        # Send Telegram
        sent = self._notifier.send_scored_alert(
            symbol=symbol,
            total_score=score.total_score,
            recommendation=score.recommendation,
            pump_pct=pump_pct,
            pump_days=pump_days,
            top_signals=top_signals,
            btc_regime=score.btc_regime,
            btc_explanation=score.btc_explanation,
            close_price=close_price,
            evidence_precision=evidence_precision,
            evidence_n_judged=evidence_n_judged,
            feature_time=str(sig_time),
            invalidation_time=str(inv_time),
        )

        if sent:
            self._alert_store.mark_telegram_sent(sig_time, symbol)
            logger.info(
                "scanner_composite_alert_sent",
                symbol=symbol,
                score=score.total_score,
                recommendation=score.recommendation,
            )
            return 1
        return 0
