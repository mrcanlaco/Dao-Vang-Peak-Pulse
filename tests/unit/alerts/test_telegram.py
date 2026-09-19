"""Tests for TelegramNotifier — mock HTTP, verify message formatting."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dao_vang.alerts.telegram import TelegramNotifier
from dao_vang.config.settings import TelegramConfig


@pytest.fixture
def configured_notifier() -> TelegramNotifier:
    """Notifier with fake token + chat_id."""
    config = TelegramConfig(
        bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
        chat_id="987654321",
    )
    return TelegramNotifier(config, web_base_url="https://daovang.comaygiauco.com")


@pytest.fixture
def unconfigured_notifier() -> TelegramNotifier:
    """Notifier without token/chat_id."""
    return TelegramNotifier(TelegramConfig())


class TestTelegramConfig:
    def test_is_configured_true(self, configured_notifier: TelegramNotifier) -> None:
        assert configured_notifier.is_configured is True

    def test_is_configured_false(self, unconfigured_notifier: TelegramNotifier) -> None:
        assert unconfigured_notifier.is_configured is False


class TestTelegramSend:
    def test_send_message_not_configured(
        self, unconfigured_notifier: TelegramNotifier
    ) -> None:
        """Should return False and not attempt HTTP when not configured."""
        assert unconfigured_notifier.send_message("test") is False

    def test_send_message_success(self, configured_notifier: TelegramNotifier) -> None:
        """Should return True on successful API response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = configured_notifier.send_message("hello")
        assert result is True
        mock_client.post.assert_called_once()

    def test_send_message_api_error(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """Should return False when API returns ok=False."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": False, "description": "chat not found"}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = configured_notifier.send_message("hello")
        assert result is False

    def test_send_message_http_error(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """Should return False on HTTP error (not raise)."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = httpx.ConnectError("connection refused")

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = configured_notifier.send_message("hello")
        assert result is False


class TestTelegramAlert:
    def test_send_alert_includes_all_fields(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """Alert message should contain symbol, risk, probability, etc."""
        captured_payload: dict = {}

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response

        def capture_post(url, json=None, **kwargs):
            captured_payload.update(json or {})
            return mock_response

        mock_client.post.side_effect = capture_post

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = configured_notifier.send_alert(
                symbol="BTCUSDT",
                risk_level="CAO",
                probability=0.85,
                threshold=0.4,
                close_price=65000.0,
                feature_time="2026-08-03T12:00:00+00:00",
                invalidation_time="2026-08-04T12:00:00+00:00",
                model_id="frozen_test_001",
            )

        assert result is True
        text = captured_payload.get("text", "")
        assert "BTCUSDT" in text
        assert "TÍN HIỆU MẠNH" in text
        assert "85.0%" in text
        assert "65,000.0000" in text
        assert "⭐⭐⭐⭐⭐" in text
        assert "🔴" in text
        assert "CỰC MẠNH" in text
        assert "https://daovang.comaygiauco.com/#coin=BTCUSDT" in text
        assert captured_payload.get("disable_web_page_preview") is True
        assert captured_payload.get("link_preview_options") == {"is_disabled": True}

    def test_send_alert_with_web_url(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """Alert with web_url should include a link."""
        captured: dict = {}

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            configured_notifier.send_alert(
                symbol="ETHUSDT",
                risk_level="TRUNG BÌNH",
                probability=0.55,
                threshold=0.4,
                close_price=3200.0,
                feature_time="2026-08-03T12:00:00+00:00",
                invalidation_time="2026-08-04T12:00:00+00:00",
                model_id="frozen_test_002",
                web_url="http://localhost:8501",
            )

        assert "localhost:8501" in captured.get("text", "")

    def test_scored_alert_includes_operating_mode(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """Observational messages must make their serving mode unambiguous."""
        captured: dict = {}
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            configured_notifier.send_scored_alert(
                symbol="BTCUSDT",
                total_score=70.0,
                recommendation="HIGH_CONFIDENCE",
                pump_pct=0.8,
                pump_days=2,
                top_signals=[],
                btc_regime="NEUTRAL",
                btc_explanation="neutral",
                close_price=65000.0,
                feature_time="2026-08-03T12:00:00+00:00",
                invalidation_time="2026-08-04T12:00:00+00:00",
                operating_mode="shadow",
            )

        text = captured.get("text", "")
        assert "QUAN SÁT (SHADOW)" in text

    def test_scored_alert_is_vietnamese_and_has_coin_link(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """Composite report should be decision-friendly and deep-link to coin."""
        captured: dict = {}
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            configured_notifier.send_scored_alert(
                symbol="ETHUSDT",
                total_score=82.0,
                recommendation="HIGH_CONFIDENCE",
                pump_pct=1.2,
                pump_days=3,
                top_signals=[("funding_spike", 90.0, 0.15, "Funding is elevated")],
                btc_regime="WEAK",
                btc_explanation="BTC is weakening",
                close_price=3200.0,
                feature_time="2026-08-03T12:00:00+00:00",
                invalidation_time="2026-08-04T12:00:00+00:00",
                model_probability=0.78,
                horizon_hours=24,
                data_quality_score=0.95,
                operating_mode="production_alerting",
            )

        text = captured.get("text", "")
        assert "CẢNH BÁO TÍN HIỆU SHORT" in text
        assert "⭐⭐⭐⭐" in text
        assert "Điểm phân phối 2 Tầng" in text
        assert "Funding tăng đột biến" in text
        assert "https://daovang.comaygiauco.com/#coin=ETHUSDT" in text
        assert "Báo cáo phân tích" in text
        assert "binance.com" not in text.lower()
        assert "okx.com" not in text.lower()
    def test_send_test(self, configured_notifier: TelegramNotifier) -> None:
        """Test message should be sent successfully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.return_value = mock_response

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            assert configured_notifier.send_test() is True

    def test_send_alert_english(self) -> None:
        """Verify English alert rendering."""
        config = TelegramConfig(
            bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
            chat_id="987654321",
            language="en",
        )
        notifier = TelegramNotifier(config, web_base_url="https://trade.example.com")
        captured: dict = {}

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            notifier.send_alert(
                symbol="SOLUSDT",
                risk_level="CAO",
                probability=0.88,
                threshold=0.70,
                close_price=180.5,
                feature_time="2026-08-03T12:00:00+00:00",
                invalidation_time="2026-08-04T12:00:00+00:00",
                model_id="frozen_model_v1",
                operating_mode="production",
            )

        text = captured.get("text", "")
        assert "DISTRIBUTION ALERT" in text
        assert "Conviction:* HIGH CONVICTION" in text
        assert "Model Probability:* 88.0%" in text
        assert "https://trade.example.com/#coin=SOLUSDT" in text

    def test_scored_alert_english(self) -> None:
        """Verify English scored alert rendering."""
        config = TelegramConfig(
            bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
            chat_id="987654321",
            language="en",
        )
        notifier = TelegramNotifier(config, web_base_url="https://trade.example.com")
        captured: dict = {}

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            notifier.send_scored_alert(
                symbol="BNBUSDT",
                total_score=85.0,
                recommendation="SHORT_CANDIDATE",
                pump_pct=0.45,
                pump_days=4,
                top_signals=[("price_volume_divergence", 80.0, 0.2, "Volume diverging")],
                btc_regime="FOMO",
                btc_explanation="BTC heating up",
                close_price=580.0,
                feature_time="2026-08-03T12:00:00+00:00",
                invalidation_time="2026-08-04T12:00:00+00:00",
                operating_mode="production_alerting",
            )

        text = captured.get("text", "")
        assert "DISTRIBUTION SIGNAL" in text
        assert "⭐⭐⭐⭐⭐" in text
        assert "Price-Volume Divergence" in text
        assert "https://trade.example.com/#coin=BNBUSDT" in text
        assert "binance.com" not in text.lower()
        assert "okx.com" not in text.lower()
    def test_send_cycle_digest_vietnamese(self, configured_notifier: TelegramNotifier) -> None:
        """Verify cycle digest formatting in Vietnamese."""
        captured: dict = {}
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        alerts = [
            {
                "symbol": "CRVUSDT",
                "recommendation": "HIGH_CONFIDENCE",
                "model_probability": 0.82,
                "pump_pct": 1.25,
                "pump_days": 2,
                "close_price": 0.35,
                "top_signals": [("oi_divergence", 85.0, 0.2, "OI tăng mạnh")],
                "web_url": "https://daovang.comaygiauco.com/#coin=CRVUSDT",
            },
            {
                "symbol": "DOGEUSDT",
                "recommendation": "HIGH_CONFIDENCE",
                "model_probability": 0.78,
                "pump_pct": 0.90,
                "pump_days": 1,
                "close_price": 0.12,
                "top_signals": [("funding_spike", 80.0, 0.15, "Funding spike")],
                "web_url": "https://daovang.comaygiauco.com/#coin=DOGEUSDT",
            },
        ]

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = configured_notifier.send_cycle_digest(
                alerts=alerts,
                btc_regime="WEAK",
                operating_mode="shadow",
            )

        assert result is True
        text = captured.get("text", "")
        assert "TỔNG HỢP TÍN HIỆU PHÂN PHỐI CHU KỲ" in text
        assert "2 coin" in text
        assert "CRVUSDT" in text
        assert "DOGEUSDT" in text
        assert "82.0%" in text
        assert "78.0%" in text
        assert "⭐⭐⭐⭐" in text
        assert "BTC:* YẾU" in text
        assert "binance.com" not in text.lower()
        assert "okx.com" not in text.lower()
    def test_send_cycle_digest_english(self) -> None:
        """Verify cycle digest formatting in English for multiple coins."""
        config = TelegramConfig(
            bot_token="123456789:ABCdefGHIjklMNOpqrSTUvwxYZ",
            chat_id="987654321",
            language="en",
        )
        notifier = TelegramNotifier(config, web_base_url="https://trade.example.com")
        captured: dict = {}

        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        alerts = [
            {
                "symbol": "CRVUSDT",
                "recommendation": "HIGH_CONFIDENCE",
                "model_probability": 0.82,
                "pump_pct": 1.25,
                "pump_days": 2,
                "close_price": 0.35,
                "top_signals": [("oi_divergence", 85.0, 0.2, "OI spike")],
                "web_url": "https://trade.example.com/#coin=CRVUSDT",
            },
            {
                "symbol": "DOGEUSDT",
                "recommendation": "HIGH_CONFIDENCE",
                "model_probability": 0.78,
                "pump_pct": 0.90,
                "pump_days": 1,
                "close_price": 0.12,
                "top_signals": [("funding_spike", 80.0, 0.15, "Funding spike")],
                "web_url": "https://trade.example.com/#coin=DOGEUSDT",
            },
        ]

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = notifier.send_cycle_digest(
                alerts=alerts,
                btc_regime="FOMO",
                operating_mode="production",
            )

        assert result is True
        text = captured.get("text", "")
        assert "RADAR CYCLE DIGEST" in text
        assert "2 coins" in text
        assert "CRVUSDT" in text
        assert "DOGEUSDT" in text
        assert "82.0%" in text
        assert "*BTC Context:* BULLISH HEAT (FOMO)" in text
        assert "binance.com" not in text.lower()
        assert "okx.com" not in text.lower()

    def test_send_two_tier_alert_no_exchange_links(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """Verify 2-tier alert formatting has no Binance/OKX links."""
        captured: dict = {}
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            configured_notifier.send_two_tier_alert(
                symbol="SOLUSDT",
                stage="FIRED",
                total_score=88.0,
                htf_score=85.0,
                ltf_score=90.0,
                pump_pct=0.75,
                pump_days=3,
                close_price=150.0,
                feature_time="2026-08-03T12:00:00+00:00",
                web_url="https://daovang.comaygiauco.com/#coin=SOLUSDT",
            )

        text = captured.get("text", "")
        assert "CẢNH BÁO TÍN HIỆU SHORT" in text
        assert "SOLUSDT" in text
        assert "https://daovang.comaygiauco.com/#coin=SOLUSDT" in text
        assert "binance.com" not in text.lower()
        assert "okx.com" not in text.lower()


class TestV3Alert:
    def test_send_v3_alert_suppressed_in_research_mode_without_shadow_chat(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """Research mode must never send V3 alert to production channel."""
        with patch("dao_vang.alerts.telegram.httpx.Client") as mock_client:
            result = configured_notifier.send_v3_alert(
                symbol="BEATUSDT",
                entry_price=4.42,
                probability=0.52,
                pump_pct=0.72,
                distance_from_high=-0.03,
                funding_percentile=0.95,
                feature_time="2026-06-08T12:04:00+00:00",
                is_champion=True,
                operating_mode="research",
            )
            assert result is False
            mock_client.assert_not_called()

    def test_send_v3_alert_delivers_to_shadow_chat_when_provided(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        """V3 research alert delivers to shadow chat when provided."""
        captured: dict = {}
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True}
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = configured_notifier.send_v3_alert(
                symbol="BEATUSDT",
                entry_price=4.42,
                probability=0.52,
                pump_pct=0.725,
                distance_from_high=-0.03,
                funding_percentile=0.95,
                feature_time="2026-06-08T12:04:00+00:00",
                is_champion=True,
                operating_mode="research",
                shadow_chat_id="-100999888777",
            )

        assert result is True
        assert captured.get("chat_id") == "-100999888777"
        text = captured.get("text", "")
        assert "V3 CHAMPION" in text
        assert "+1.8% EV" not in text
        assert "BEATUSDT" in text
        assert "Entry 1" in text
        assert "TP reference from initial Entry 1:* `-20%`" in text
        assert "Stop reference from initial Entry 1:* `+16%`" in text

    def test_v3_alert_renders_pattern_stage_unknown_and_reference_score(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        captured: dict = {}
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 77}}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = configured_notifier.send_v3_alert_with_result(
                symbol="XRPUSDT",
                entry_price=1.0,
                probability=0.52,
                pump_pct=0.3,
                distance_from_high=-0.03,
                funding_percentile=0.9,
                feature_time="2026-09-15T00:00:00+00:00",
                operating_mode="research",
                shadow_chat_id="-1009",
                pattern_id="unknown",
                pattern_stage="reversal",
                pattern_status="unknown",
                nearest_pattern="pattern_01",
                pattern_distance=2.1,
                pattern_discrepancies=["funding_persistence_7d"],
                conditions={
                    "pump": True,
                    "reversal": True,
                    "funding": True,
                    "funding_change": True,
                    "score": True,
                    "funding_persistence": True,
                },
                score_kind="reference_model_score",
            )

        assert result == {"message_id": 77}
        text = captured["text"]
        assert "[PATTERN:unknown]" in text
        assert "[STAGE:REVERSAL]" in text
        assert "Nearest pattern" in text
        assert "Discrepancies" in text
        assert "Reference model score" in text
        assert "5/5 configured conditions met" in text
        assert "reference score" in text
        assert "52.0%" not in text

    def test_v3_outcome_update_replies_and_separates_post_stop_price_only(
        self, configured_notifier: TelegramNotifier
    ) -> None:
        captured: dict = {}
        mock_response = MagicMock()
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 78}}
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.post.side_effect = lambda url, json=None, **kw: (
            captured.update(json or {}) or mock_response
        )

        with patch("dao_vang.alerts.telegram.httpx.Client", return_value=mock_client):
            result = configured_notifier.send_v3_outcome_update_with_result(
                symbol="XRPUSDT",
                outcome_type="target_after_stop",
                status="target_after_stop",
                operating_mode="research",
                shadow_chat_id="-1009",
                chat_id="-1009",
                reply_to_message_id=77,
                price_only_post_stop=True,
                frozen_average_entry=100.0,
                frozen_target_price=80.0,
                horizon_time="2026-09-17T00:00:00+00:00",
            )

        assert result == {"message_id": 78}
        assert captured["reply_parameters"] == {"message_id": 77}
        assert "POST-STOP PRICE-ONLY TRACK" in captured["text"]
        assert "not an actual outcome" in captured["text"]
        assert "80" in captured["text"]
