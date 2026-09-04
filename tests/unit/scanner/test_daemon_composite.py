from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import duckdb

from dao_vang.config.settings import AppSettings
from dao_vang.scanner.daemon import ScannerDaemon
from dao_vang.scanner.pump_filter import PumpCandidate


def test_score_and_alert_composite_executes_without_name_errors():
    conn = duckdb.connect(":memory:")
    conn.execute("""
        CREATE TABLE feature_results (
            symbol VARCHAR,
            feature_time TIMESTAMP,
            price_ret_24h DOUBLE,
            oi_change_24h DOUBLE,
            funding_rate_raw DOUBLE,
            taker_buy_ratio DOUBLE,
            volume_24h DOUBLE,
            volume_base DOUBLE
        );
        CREATE TABLE kline (
            symbol VARCHAR,
            close_time TIMESTAMP,
            interval VARCHAR,
            close DOUBLE,
            volume_quote DOUBLE
        );
        CREATE TABLE scan_results (
            scan_time TIMESTAMP,
            symbol VARCHAR,
            score DOUBLE,
            recommendation VARCHAR,
            model_probability DOUBLE,
            heuristic_score DOUBLE,
            calibrated_probability DOUBLE,
            data_quality_score DOUBLE,
            horizon_hours BIGINT,
            close_price DOUBLE,
            price_change_24h DOUBLE,
            oi_change_24h DOUBLE,
            funding_rate DOUBLE,
            taker_sell_ratio DOUBLE,
            volume_24h_usd DOUBLE,
            pump_pct DOUBLE,
            pump_days BIGINT,
            cycle BIGINT
        );
    """)

    conn.execute(
        """
        INSERT INTO feature_results VALUES
        ('BTCUSDT', '2026-08-14 19:55:00', 0.01, 0.05, 0.0001, 0.45, 1000000.0, 1000000.0)
        """
    )
    conn.execute(
        """
        INSERT INTO kline VALUES
        ('BTCUSDT', '2026-08-14 19:55:00', '5m', 60000.0, 1000000.0)
        """
    )

    settings = AppSettings()
    daemon = ScannerDaemon.__new__(ScannerDaemon)
    daemon._settings = settings
    daemon._scanner_cfg = SimpleNamespace(
        max_feature_age_minutes=60,
        min_data_quality_score=0.1,
        shadow_telegram_enabled=True,
        cooldown_minutes=120,
        telegram_cooldown_minutes=120,
        telegram_min_volume_usd=1000.0,
        telegram_min_probability=0.5,
        telegram_tiers=["HIGH_CONFIDENCE"],
        alert_levels=["CAO"],
    )
    daemon._operating_mode = "shadow"
    daemon._web_base_url = "https://daovang.comaygiauco.com"
    daemon._cycle_count = 1
    daemon._bundle_valid = True
    daemon._kill_switch = SimpleNamespace(active=False)
    daemon._frozen_info = SimpleNamespace(
        model_id="test_model",
        label_spec={"version": "v1", "target_drawdown": 0.08, "max_ae": 0.04},
        checksums={},
        metadata={"horizon_hours": 24},
    )
    daemon._scan_result_store = MagicMock()
    daemon._alert_store = MagicMock()
    daemon._alert_store.is_in_cooldown_key.return_value = False
    daemon._alert_store.is_in_cooldown.return_value = False
    daemon._scan_result_store.is_prediction_telegram_in_cooldown.return_value = False
    daemon._alert_store.precision_by_risk_level.return_value = {}
    daemon._notifier = MagicMock()

    mock_score = SimpleNamespace(
        total_score=85.0,
        components=[],
        top_signals=[],
        btc_regime="NEUTRAL",
        btc_explanation="BTC flat",
    )
    mock_result = SimpleNamespace(
        heuristic=mock_score,
        risk_tier="HIGH_CONFIDENCE",
        model_probability=0.88,
        calibrated_probability=0.85,
        quality=SimpleNamespace(score=1.0, status="valid", max_feature_age_minutes=5.0, missing_features=0, is_usable=True, reason_codes=[]),
        threshold=0.6,
        threshold_policy_version="1.0",
        evidence_groups=("order_flow",),
        calibrator_id="calib1",
        alertable=True,
    )

    with patch("dao_vang.scanner.daemon.assess_snapshot_quality", return_value=mock_result.quality), \
         patch("dao_vang.scanner.daemon.score_snapshot", return_value=mock_result):
        # Test collect_for_digest=True
        digest_res = daemon._score_and_alert_composite(
            symbol="BTCUSDT",
            db=SimpleNamespace(conn=conn),
            btc_context={"regime": "NEUTRAL"},
            pump_candidate=PumpCandidate("BTCUSDT", 0.1, 2, 0.1, 60000.0, 55000.0, 1000000.0),
            collect_for_digest=True,
        )
        assert isinstance(digest_res, dict)
        assert digest_res["symbol"] == "BTCUSDT"
        assert digest_res["total_score"] == 85.0
        assert digest_res["volume_24h_usd"] == 1_000_000.0
        assert digest_res["web_url"] == "https://daovang.comaygiauco.com/#coin=BTCUSDT"

        # Test collect_for_digest=False
        sent_res = daemon._score_and_alert_composite(
            symbol="BTCUSDT",
            db=SimpleNamespace(conn=conn),
            btc_context={"regime": "NEUTRAL"},
            pump_candidate=PumpCandidate("BTCUSDT", 0.1, 2, 0.1, 60000.0, 55000.0, 1000000.0),
            collect_for_digest=False,
        )
        assert sent_res in (0, 1)
