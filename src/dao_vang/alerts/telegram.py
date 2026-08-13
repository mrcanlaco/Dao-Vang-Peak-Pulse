"""Telegram Bot API client for sending distribution alerts.

Reads bot_token + chat_id from TelegramConfig (env var or YAML).
Uses httpx (already a dependency via collectors) for HTTP calls.
Retries with tenacity on transient failures.

Security: never logs the full bot token — only first 4 chars + ***.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from dao_vang.config.settings import TelegramConfig
from dao_vang.domain.time import system_iso
from dao_vang.logging import get_logger

logger = get_logger(__name__)


def _display_time(value: str) -> str:
    """Format an ISO/DB timestamp for Telegram in Vietnam time."""
    converted = system_iso(value)
    return converted[:19].replace("T", " ") if converted else str(value)[:19]

_RISK_EMOJI = {
    "CAO": "🚨",
    "TRUNG BÌNH": "⚠️",
    "THẤP": "🟡",
    "RẤT THẤP": "⚪",
}

_RISK_LABELS = {
    "CAO": "CAO",
    "TRUNG BÌNH": "TRUNG BÌNH",
    "THẤP": "THẤP",
    "RẤT THẤP": "RẤT THẤP",
}

_MODE_LABELS = {
    "research": "NGHIÊN CỨU",
    "shadow": "QUAN SÁT (SHADOW)",
    "canary": "CANARY / THỬ NGHIỆM",
    "production": "VẬN HÀNH THẬT",
    "production_alerting": "BÁO CÁO THAM KHẢO",
}

_RECOMMENDATION_LABELS = {
    "SHORT_CANDIDATE": "ỨNG VIÊN SHORT",
    "HIGH_CONFIDENCE": "TÍN HIỆU MẠNH",
    "WATCH": "THEO DÕI",
    "WAIT": "CHỜ THÊM",
}

_BTC_REGIME_LABELS = {
    "FOMO": "TĂNG NÓNG (FOMO)",
    "NEUTRAL": "TRUNG TÍNH",
    "WEAK": "YẾU",
}

_SIGNAL_LABELS = {
    "price_volume_divergence": "Phân kỳ giá - khối lượng",
    "funding_spike": "Funding tăng đột biến",
    "momentum_exhaustion": "Đà tăng suy yếu",
    "distance_from_high": "Xa đỉnh gần nhất",
    "taker_sell_pressure": "Áp lực bán chủ động",
    "btc_context": "Bối cảnh BTC",
    "oi_divergence": "Phân kỳ Open Interest",
    "fake_breakout": "Có dấu hiệu phá vỡ giả",
}


def _mode_label(mode: str) -> str:
    """Return a stable, human-readable serving-mode label for Telegram."""

    normalized = str(mode).strip().lower()
    return _MODE_LABELS.get(normalized, normalized.upper() or "UNKNOWN")


def _recommendation_label(recommendation: str) -> str:
    normalized = str(recommendation).strip().upper()
    return _RECOMMENDATION_LABELS.get(normalized, normalized.replace("_", " "))


def _risk_label(risk_level: str) -> str:
    normalized = str(risk_level).strip().upper()
    return _RISK_LABELS.get(normalized, normalized or "KHÔNG XÁC ĐỊNH")


def _btc_regime_label(regime: str) -> str:
    normalized = str(regime).strip().upper()
    return _BTC_REGIME_LABELS.get(normalized, normalized or "KHÔNG XÁC ĐỊNH")


def _signal_label(name: str) -> str:
    normalized = str(name).strip().lower()
    return _SIGNAL_LABELS.get(normalized, normalized.replace("_", " ").title())


def _coin_url(base_url: str | None, symbol: str) -> str | None:
    """Build the frontend hash link that opens the selected coin directly."""

    base = str(base_url or "").strip().rstrip("/")
    normalized_symbol = str(symbol).strip().upper()
    if not base or not normalized_symbol:
        return None
    return f"{base}/#coin={quote(normalized_symbol, safe='')}"


class TelegramNotifier:
    """Send alerts via Telegram Bot API.

    Args:
        config: TelegramConfig with bot_token + chat_id.
    """

    def __init__(self, config: TelegramConfig, web_base_url: str | None = None) -> None:
        self._config = config
        self._web_base_url = web_base_url
        self._base_url = f"{config.api_base}/bot{config.bot_token}"
        token_display = f"{config.bot_token[:4]}***" if config.bot_token else "NOT_SET"
        logger.info("telegram_notifier_init", token=token_display)

    @property
    def is_configured(self) -> bool:
        """True if both bot_token and chat_id are set."""
        return bool(self._config.bot_token and self._config.chat_id)

    @retry(
        retry=retry_if_exception_type((httpx.HTTPError, OSError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST to Telegram API with retry."""
        url = f"{self._base_url}/sendMessage"
        with httpx.Client(timeout=self._config.timeout_seconds) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a plain text message.

        Returns True on success, False on failure (logged, not raised).
        """
        if not self.is_configured:
            logger.warning("telegram_not_configured_skip")
            return False
        payload = {
            "chat_id": self._config.chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        try:
            result = self._post(payload)
            ok = result.get("ok", False)
            if not ok:
                logger.error("telegram_send_failed", response=result)
            return ok
        except Exception as exc:
            logger.error("telegram_send_error", error=str(exc))
            return False

    def send_alert(
        self,
        symbol: str,
        risk_level: str,
        probability: float,
        threshold: float,
        close_price: float | None,
        feature_time: str,
        invalidation_time: str,
        model_id: str,
        web_url: str | None = None,
        operating_mode: str = "production",
    ) -> bool:
        """Send a formatted distribution alert.

        Args:
            symbol: Coin symbol (e.g. "BTCUSDT").
            risk_level: One of CAO / TRUNG BÌNH / THẤP / RẤT THẤP.
            probability: Model probability (0.0–1.0).
            threshold: Decision threshold from frozen model.
            close_price: Close price at signal time, if available.
            feature_time: ISO timestamp of the signal candle.
            invalidation_time: ISO timestamp when alert expires (24h).
            model_id: Frozen model ID used for prediction.
            web_url: Optional URL to web app for deep-dive.

        Returns True on success.
        """
        emoji = _RISK_EMOJI.get(risk_level, "🔔")
        price_str = f"${close_price:,.4f}" if close_price else "N/A"
        mode_label = _mode_label(operating_mode)
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        lines = [
            f"{emoji} *CẢNH BÁO PHÂN PHỐI* — `{symbol}`",
            f"*Chế độ:* `{mode_label}`",
            "*Mục đích:* `THAM KHẢO / ĐÁNH GIÁ`",
            "*Tự động đặt lệnh:* `TẮT`",
            "",
            f"*Mức cảnh báo:* {_risk_label(risk_level)}",
            f"*Xác suất mô hình:* {probability:.1%}",
            f"*Ngưỡng quyết định:* {threshold:.2f}",
            f"*Giá đóng cửa:* {price_str}",
            f"*Thời điểm tín hiệu:* {_display_time(feature_time)} UTC+7",
            f"*Hết hiệu lực:* {_display_time(invalidation_time)} UTC+7",
            f"*Mô hình:* `{model_id}`",
        ]
        if detail_url:
            lines.append("")
            lines.append(f"[🔗 Mở trang phân tích {symbol}]({detail_url})")
        lines.extend(["", "_Báo cáo tham khảo; hãy tự kiểm tra trước khi quyết định._"])
        text = "\n".join(lines)
        return self.send_message(text)

    def send_scored_alert(
        self,
        symbol: str,
        total_score: float,
        recommendation: str,
        pump_pct: float,
        pump_days: int,
        top_signals: list[tuple[str, float, float, str]],
        btc_regime: str,
        btc_explanation: str,
        close_price: float | None,
        feature_time: str,
        invalidation_time: str,
        evidence_precision: float | None = None,
        evidence_n_judged: int = 0,
        web_url: str | None = None,
        model_probability: float | None = None,
        horizon_hours: int | None = None,
        data_quality_score: float | None = None,
        model_id: str | None = None,
        label_version: str | None = None,
        operating_mode: str = "production",
    ) -> bool:
        """Send a composite-score distribution alert.

        Args:
            symbol: Coin symbol (e.g. "EULUSDT").
            total_score: Composite score 0-100.
            recommendation: "SHORT_CANDIDATE" | "WATCH" | "WAIT".
            pump_pct: Pump magnitude (e.g. 1.8 = +180%).
            pump_days: Days to reach peak.
            top_signals: List of (name, score, weight, explanation) tuples.
            btc_regime: "FOMO" | "NEUTRAL" | "WEAK".
            btc_explanation: BTC context explanation string.
            close_price: Close price at signal time.
            feature_time: ISO timestamp of signal.
            invalidation_time: ISO timestamp when alert expires.
            evidence_precision: Empirical historical precision for this risk
                level, computed from resolved alert outcomes (self-learning
                feedback — None if not enough judged alerts yet).
            evidence_n_judged: Number of past alerts this precision is based on.
            web_url: Optional URL to web app.

        Returns True on success.
        """
        normalized_recommendation = str(recommendation).strip().upper()
        emoji = "🚨" if normalized_recommendation in {"SHORT_CANDIDATE", "HIGH_CONFIDENCE"} else "⚠️"
        price_str = f"${close_price:,.4f}" if close_price else "N/A"
        mode_label = _mode_label(operating_mode)
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        lines = [
            f"{emoji} *BÁO CÁO TÍN HIỆU* — `{symbol}`",
            f"*Kết luận:* `{_recommendation_label(normalized_recommendation)}`",
            f"*Chế độ:* `{mode_label}`",
            "*Mục đích:* `THAM KHẢO / ĐÁNH GIÁ`",
            "*Tự động đặt lệnh:* `TẮT`",
            "",
            f"*Điểm tín hiệu:* {total_score:.0f}/100",
            f"*Mức tăng trước đó:* +{pump_pct:.0%} trong {pump_days} ngày",
            f"*Giá đóng cửa:* {price_str}",
        ]
        if model_probability is not None:
            lines.append(f"*Xác suất mô hình:* {model_probability:.1%}")
        if horizon_hours is not None:
            lines.append(f"*Khung đánh giá:* {horizon_hours} giờ")
        if data_quality_score is not None:
            lines.append(f"*Chất lượng dữ liệu:* {data_quality_score:.0%}")
        lines.extend([
            "",
            "*Các tín hiệu chính:*",
        ])
        for name, score, weight, explanation in top_signals:
            label = _signal_label(name)
            lines.append(f"  • {label}: {score:.0f}/100 (trọng số {weight:.0%})")
            lines.append(f"    _{explanation}_")
        lines.extend(
            [
                "",
                f"*Bối cảnh BTC:* {_btc_regime_label(btc_regime)} — {btc_explanation}",
            ]
        )
        if evidence_precision is not None and evidence_n_judged >= 5:
            lines.append(
                f"*Độ chính xác lịch sử:* {evidence_precision:.0%} "
                f"trên {evidence_n_judged} tín hiệu đã kiểm chứng gần đây"
            )
        else:
            lines.append(
                "*Độ chính xác lịch sử:* chưa đủ dữ liệu kiểm chứng "
                f"(cần ≥5 tín hiệu đã chấm kết quả, hiện có {evidence_n_judged})"
            )
        lines.extend(
            [
                f"*Thời điểm tín hiệu:* {_display_time(feature_time)} UTC+7",
                f"*Hết hiệu lực:* {_display_time(invalidation_time)} UTC+7",
            ]
        )
        if model_id:
            lines.append(f"*Mô hình:* `{model_id}`")
        if label_version:
            lines.append(f"*Phiên bản nhãn:* `{label_version}`")
        if detail_url:
            lines.append("")
            lines.append(f"[🔗 Mở trang phân tích {symbol}]({detail_url})")
        lines.extend(["", "_Báo cáo tham khảo; không tự động đặt lệnh._"])
        text = "\n".join(lines)
        return self.send_message(text)

    def send_test(self) -> bool:
        """Send a test message to verify configuration."""
        return self.send_message(
            "🧪 *Đảo Vàng — Test*\n\n"
            "Telegram bot đã kết nối thành công. "
            "Bạn sẽ nhận alert khi scanner phát hiện Distribution."
        )
