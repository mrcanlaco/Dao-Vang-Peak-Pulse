"""Telegram Bot API client for sending distribution alerts.

Reads bot_token + chat_id from TelegramConfig (env var or YAML).
Uses httpx (already a dependency via collectors) for HTTP calls.
Retries with tenacity on transient failures.

Supports bilingual formatting (Vietnamese 'vi' and English 'en').
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


def _display_time(value: str, lang: str = "vi") -> str:
    """Format an ISO/DB timestamp for Telegram. UTC+7 for VI, UTC for EN."""
    if lang == "en":
        raw = str(value).replace("T", " ")[:19]
        return f"{raw} UTC"
    converted = system_iso(value)
    formatted = converted[:19].replace("T", " ") if converted else str(value)[:19]
    return f"{formatted} UTC+7"


_RISK_EMOJI = {
    "CAO": "🚨",
    "HIGH": "🚨",
    "TRUNG BÌNH": "⚠️",
    "MEDIUM": "⚠️",
    "THẤP": "🟡",
    "LOW": "🟡",
    "RẤT THẤP": "⚪",
    "VERY LOW": "⚪",
}

_RISK_LABELS_VI = {
    "CAO": "CAO",
    "HIGH": "CAO",
    "TRUNG BÌNH": "TRUNG BÌNH",
    "MEDIUM": "TRUNG BÌNH",
    "THẤP": "THẤP",
    "LOW": "THẤP",
    "RẤT THẤP": "RẤT THẤP",
    "VERY LOW": "RẤT THẤP",
}

_RISK_LABELS_EN = {
    "CAO": "HIGH",
    "HIGH": "HIGH",
    "TRUNG BÌNH": "MEDIUM",
    "MEDIUM": "MEDIUM",
    "THẤP": "LOW",
    "LOW": "LOW",
    "RẤT THẤP": "VERY LOW",
    "VERY LOW": "VERY LOW",
}

_MODE_LABELS_VI = {
    "research": "NGHIÊN CỨU",
    "shadow": "QUAN SÁT (SHADOW)",
    "canary": "CANARY / THỬ NGHIỆM",
    "production": "VẬN HÀNH THẬT",
    "production_alerting": "BÁO CÁO THAM KHẢO",
}

_MODE_LABELS_EN = {
    "research": "RESEARCH",
    "shadow": "SHADOW OBSERVATION",
    "canary": "CANARY / PILOT",
    "production": "PRODUCTION",
    "production_alerting": "REFERENCE REPORT",
}

_RECOMMENDATION_LABELS_VI = {
    "SHORT_CANDIDATE": "ỨNG VIÊN SHORT",
    "HIGH_CONFIDENCE": "TÍN HIỆU MẠNH",
    "WATCH": "THEO DÕI",
    "WAIT": "CHỜ THÊM",
}

_RECOMMENDATION_LABELS_EN = {
    "SHORT_CANDIDATE": "SHORT CANDIDATE",
    "HIGH_CONFIDENCE": "HIGH CONFIDENCE SIGNAL",
    "WATCH": "WATCHLIST",
    "WAIT": "WAIT / STANDBY",
}

_BTC_REGIME_LABELS_VI = {
    "FOMO": "TĂNG NÓNG (FOMO)",
    "NEUTRAL": "TRUNG TÍNH",
    "WEAK": "YẾU",
}

_BTC_REGIME_LABELS_EN = {
    "FOMO": "BULLISH HEAT (FOMO)",
    "NEUTRAL": "NEUTRAL",
    "WEAK": "WEAK",
}

_SIGNAL_LABELS_VI = {
    "price_volume_divergence": "Phân kỳ giá - khối lượng",
    "funding_spike": "Funding tăng đột biến",
    "momentum_exhaustion": "Đà tăng suy yếu",
    "distance_from_high": "Xa đỉnh gần nhất",
    "taker_sell_pressure": "Áp lực bán chủ động",
    "btc_context": "Bối cảnh BTC",
    "oi_divergence": "Phân kỳ Open Interest",
    "fake_breakout": "Có dấu hiệu phá vỡ giả",
}

_SIGNAL_LABELS_EN = {
    "price_volume_divergence": "Price-Volume Divergence",
    "funding_spike": "Funding Rate Spike",
    "momentum_exhaustion": "Momentum Exhaustion",
    "distance_from_high": "Distance from Recent High",
    "taker_sell_pressure": "Taker Sell Pressure",
    "btc_context": "BTC Market Regime",
    "oi_divergence": "Open Interest Divergence",
    "fake_breakout": "Suspected Fake Breakout",
}


def _mode_label(mode: str, lang: str = "vi") -> str:
    """Return a stable, human-readable serving-mode label for Telegram."""
    normalized = str(mode).strip().lower()
    table = _MODE_LABELS_EN if lang == "en" else _MODE_LABELS_VI
    return table.get(normalized, normalized.upper() or "UNKNOWN")


def _recommendation_label(recommendation: str, lang: str = "vi") -> str:
    normalized = str(recommendation).strip().upper()
    table = _RECOMMENDATION_LABELS_EN if lang == "en" else _RECOMMENDATION_LABELS_VI
    return table.get(normalized, normalized.replace("_", " "))


def _risk_label(risk_level: str, lang: str = "vi") -> str:
    normalized = str(risk_level).strip().upper()
    table = _RISK_LABELS_EN if lang == "en" else _RISK_LABELS_VI
    default = "UNKNOWN" if lang == "en" else "KHÔNG XÁC ĐỊNH"
    return table.get(normalized, normalized or default)


def _btc_regime_label(regime: str, lang: str = "vi") -> str:
    normalized = str(regime).strip().upper()
    table = _BTC_REGIME_LABELS_EN if lang == "en" else _BTC_REGIME_LABELS_VI
    default = "UNKNOWN" if lang == "en" else "KHÔNG XÁC ĐỊNH"
    return table.get(normalized, normalized or default)


def _signal_label(name: str, lang: str = "vi") -> str:
    normalized = str(name).strip().lower()
    table = _SIGNAL_LABELS_EN if lang == "en" else _SIGNAL_LABELS_VI
    return table.get(normalized, normalized.replace("_", " ").title())


def _signal_grade(
    probability: float | None = None,
    total_score: float | None = None,
    recommendation: str = "",
    risk_level: str = "",
    lang: str = "vi",
) -> tuple[str, str, str]:
    """Calculate rating stars, badge color emoji, and human tier label.

    Returns:
        (stars_str, color_emoji, tier_title)
        Example: ("⭐⭐⭐⭐⭐", "🔴", "CỰC MẠNH" / "EXTREME")
    """
    prob = float(probability) if probability is not None else 0.0
    score = float(total_score) if total_score is not None else 0.0
    rec = str(recommendation).strip().upper()
    risk = str(risk_level).strip().upper()

    if prob >= 0.85 or score >= 85 or (risk in {"CAO", "HIGH"} and prob >= 0.82):
        stars = "⭐⭐⭐⭐⭐"
        color = "🔴"
        title = "CỰC MẠNH" if lang == "vi" else "EXTREME"
    elif prob >= 0.80 or score >= 75 or rec in {"SHORT_CANDIDATE", "HIGH_CONFIDENCE"}:
        stars = "⭐⭐⭐⭐"
        color = "🟠"
        title = "RẤT MẠNH" if lang == "vi" else "VERY HIGH"
    elif prob >= 0.70 or score >= 60:
        stars = "⭐⭐⭐"
        color = "🟡"
        title = "TIÊU CHUẨN" if lang == "vi" else "STANDARD"
    elif prob >= 0.50 or rec == "WATCH" or risk in {"TRUNG BÌNH", "MEDIUM"}:
        stars = "⭐⭐"
        color = "🟢"
        title = "THEO DÕI" if lang == "vi" else "WATCH"
    else:
        stars = "⭐"
        color = "⚪"
        title = "THẤP" if lang == "vi" else "LOW"

    return stars, color, title


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
        config: TelegramConfig with bot_token + chat_id + language.
    """

    def __init__(self, config: TelegramConfig, web_base_url: str | None = None) -> None:
        self._config = config
        self._web_base_url = web_base_url
        self._base_url = f"{config.api_base}/bot{config.bot_token}"
        self._lang = getattr(config, "language", "vi") or "vi"
        token_display = f"{config.bot_token[:4]}***" if config.bot_token else "NOT_SET"
        logger.info("telegram_notifier_init", token=token_display, language=self._lang)

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

    def send_message(
        self,
        text: str,
        parse_mode: str = "Markdown",
        disable_web_page_preview: bool = True,
    ) -> bool:
        """Send a plain text message.

        Returns True on success, False on failure (logged, not raised).
        """
        if not self.is_configured:
            logger.warning("telegram_not_configured_skip")
            return False
        payload: dict[str, Any] = {
            "chat_id": self._config.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_web_page_preview,
            "link_preview_options": {"is_disabled": disable_web_page_preview},
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
        """Send a compact, mobile-friendly distribution alert with star rating."""
        stars, color_badge, grade_title = _signal_grade(
            probability=probability,
            risk_level=risk_level,
            lang=self._lang,
        )
        price_str = f"${close_price:,.4f}" if close_price else "N/A"
        mode_label = _mode_label(operating_mode, self._lang)
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""

        if self._lang == "en":
            lines = [
                f"{color_badge} *DISTRIBUTION ALERT — `{symbol}`* {stars}{mode_prefix}",
                f"• *Signal Grade:* {stars} `{grade_title}` ({color_badge})",
                f"• *Risk Level:* {_risk_label(risk_level, 'en')}",
                f"• *Model Probability:* {probability:.1%}",
                f"• *Close Price:* {price_str}",
                f"• *Signal Time:* {_display_time(feature_time, 'en')}",
            ]
            if detail_url:
                lines.append(f"[🔗 Open {symbol} Analysis Dashboard]({detail_url})")
            lines.extend(["", "_Reference only. Please DYOR before making any trading decisions._"])
        else:
            lines = [
                f"{color_badge} *CẢNH BÁO PHÂN PHỐI — `{symbol}`* {stars}{mode_prefix}",
                f"• *Cấp độ tín hiệu:* {stars} `{grade_title}` ({color_badge})",
                f"• *Mức cảnh báo:* {_risk_label(risk_level, 'vi')}",
                f"• *Xác suất mô hình:* {probability:.1%}",
                f"• *Giá đóng cửa:* {price_str}",
                f"• *Thời điểm tín hiệu:* {_display_time(feature_time, 'vi')}",
            ]
            if detail_url:
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
        """Send a compact composite-score distribution alert with star rating."""
        normalized_recommendation = str(recommendation).strip().upper()
        stars, color_badge, grade_title = _signal_grade(
            probability=model_probability,
            total_score=total_score,
            recommendation=normalized_recommendation,
            lang=self._lang,
        )
        price = close_price or 0.0
        price_str = f"${price:,.4f}" if price > 0 else "N/A"
        mode_label = _mode_label(operating_mode, self._lang)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        is_fired = normalized_recommendation in {"SHORT_CANDIDATE", "HIGH_CONFIDENCE"} or total_score >= 50.0

        if self._lang == "en":
            stage_badge = "⚡ *[DISTRIBUTION SIGNAL — HIGH CONFIDENCE]*" if is_fired else "🧭 *[OVERBOUGHT WATCHLIST — ARMED]*"
            sig_lines = []
            for s in top_signals[:3]:
                sig_name = _signal_label(s[0], "en")
                sig_exp = f" ({s[3]})" if len(s) > 3 and s[3] and s[3] != s[0] else ""
                sig_lines.append(f"  • *{sig_name}*{sig_exp}")
            sig_text = "\n".join(sig_lines) if sig_lines else "  • Distribution pattern detected on order flow"
            prob_str = f"{model_probability:.1%}" if model_probability is not None else "N/A"
            pump_str = f"+{pump_pct:.0%} in {pump_days}d" if pump_days > 0 else f"+{pump_pct:.0%}"

            lines = [
                f"{stage_badge} `{symbol}` {stars}{mode_prefix}",
                f"• *Market Price:* `{price_str}` | *Pump Amplitude:* `{pump_str}`",
                f"• *Distribution Score:* `{total_score:.0f}/100` | *Short Probability:* `{prob_str}`",
                f"• *BTC Market Context:* {_btc_regime_label(btc_regime, 'en')}",
                "• *Key Distribution Reasons:*",
                sig_text,
            ]
            if detail_url:
                lines.append(f"[🔗 Open {symbol} Analysis Dashboard]({detail_url})")
            lines.extend(["", "_Distribution radar analysis from Dao Vang AI._"])
        else:
            stage_badge = "⚡ *[CẢNH BÁO TÍN HIỆU SHORT — PHÂN PHỐI ĐỈNH]* 🚨" if is_fired else "🧭 *[THEO DÕI VÙNG ĐỈNH QUÁ MUA]*"
            sig_lines = []
            for s in top_signals[:3]:
                sig_name = _signal_label(s[0], "vi")
                sig_exp = f" ({s[3]})" if len(s) > 3 and s[3] and s[3] != s[0] else ""
                sig_lines.append(f"  • *{sig_name}*{sig_exp}")
            sig_text = "\n".join(sig_lines) if sig_lines else "  • Phát hiện dấu hiệu phân phối đỉnh trên dữ liệu phái sinh"
            prob_str = f"{model_probability:.1%}" if model_probability is not None else "N/A"
            pump_str = f"+{pump_pct:.0%} trong {pump_days} ngày" if pump_days > 0 else f"+{pump_pct:.0%}"

            lines = [
                f"{stage_badge} `{symbol}` {stars}{mode_prefix}",
                f"• *Giá thị trường:* `{price_str}` | *Biên độ bơm:* `{pump_str}`",
                f"• *Điểm phân phối 2 Tầng:* *{total_score:.0f}/100* | *Xác suất Short:* `{prob_str}`",
                f"• *Bối cảnh BTC:* {_btc_regime_label(btc_regime, 'vi')}",
                "• *Căn cứ & Tín hiệu phân phối chính:*",
                sig_text,
            ]
            if detail_url:
                lines.append(f"[🔗 Mở Biểu Đồ & Phân Tích {symbol}]({detail_url})")
            lines.extend(["", "_Báo cáo phân tích xác suất phân phối từ Đảo Vàng AI._"])
        text = "\n".join(lines)
        return self.send_message(text)

    def send_cycle_digest(
        self,
        alerts: list[dict[str, Any]],
        btc_regime: str = "NEUTRAL",
        scan_time: str | None = None,
        operating_mode: str = "production",
    ) -> bool:
        """Send a consolidated cycle digest when multiple coins are detected."""
        if not alerts:
            return False
        if len(alerts) == 1:
            a = alerts[0]
            return self.send_scored_alert(
                symbol=a["symbol"],
                total_score=a.get("total_score", 0.0),
                recommendation=a.get("recommendation", "HIGH_CONFIDENCE"),
                pump_pct=a.get("pump_pct", 0.0),
                pump_days=a.get("pump_days", 0),
                top_signals=a.get("top_signals", []),
                btc_regime=btc_regime,
                btc_explanation=a.get("btc_explanation", ""),
                close_price=a.get("close_price"),
                feature_time=a.get("feature_time", scan_time or ""),
                invalidation_time=a.get("invalidation_time", ""),
                model_probability=a.get("model_probability"),
                operating_mode=operating_mode,
                web_url=a.get("web_url"),
            )

        mode_label = _mode_label(operating_mode, self._lang)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""
        formatted_time = _display_time(scan_time, self._lang) if scan_time else ""

        # Categorize into FIRED vs ARMED
        fired_alerts = []
        armed_alerts = []
        for a in alerts:
            rec = a.get("recommendation", "")
            prob = a.get("model_probability") or 0.0
            score = a.get("total_score") or 0.0
            if rec in {"SHORT_CANDIDATE", "HIGH_CONFIDENCE"} or prob >= 0.55 or score >= 50.0:
                fired_alerts.append(a)
            else:
                armed_alerts.append(a)

        if self._lang == "en":
            lines = [
                f"📊 *RADAR CYCLE DIGEST (DISTRIBUTION SIGNALS)* ({len(alerts)} coins){mode_prefix}",
            ]
            if formatted_time:
                lines.append(f"• *Time:* {formatted_time}")
            lines.append(f"• *BTC Context:* {_btc_regime_label(btc_regime, 'en')}")
            lines.append(f"• *Summary:* ⚡ *{len(fired_alerts)} High Confidence* | 🧭 *{len(armed_alerts)} Overbought Watch*")
            lines.append("")

            if fired_alerts:
                lines.append("⚡ *[HIGH CONFIDENCE SHORT SIGNALS]*")
                for i, a in enumerate(fired_alerts, 1):
                    sym = a["symbol"]
                    prob = a.get("model_probability")
                    score_val = a.get("total_score") or 0.0
                    c_stars, _, _ = _signal_grade(probability=prob, total_score=score_val, recommendation="HIGH_CONFIDENCE", lang="en")
                    prob_str = f"{prob:.1%}" if prob is not None else "N/A"
                    price = a.get("close_price") or 0.0
                    price_str = f"${price:,.4f}" if price > 0 else "N/A"
                    pump_pct = a.get("pump_pct", 0.0)
                    pump_days = a.get("pump_days", 0)
                    pump_str = f"+{pump_pct:.0%} ({pump_days}d)" if pump_days > 0 else f"+{pump_pct:.0%}"
                    top_sigs = a.get("top_signals", [])
                    sig_names = [_signal_label(s[0], "en") for s in top_sigs[:2]]
                    sig_str = ", ".join(sig_names) if sig_names else "Order flow distribution detected"
                    detail_url = a.get("web_url") or _coin_url(self._web_base_url, sym)

                    lines.append(f"{i}. ⚡ `{sym}` {c_stars} — Price: `{price_str}` (Pumped {pump_str})")
                    lines.append(f"   • Score: *{score_val:.0f}/100* | Short Prob: *{prob_str}*")
                    lines.append(f"   • Reasons: {sig_str}")
                    if detail_url:
                        lines.append(f"   • [🔗 View Analysis]({detail_url})")
                    lines.append("")

            if armed_alerts:
                lines.append("🧭 *[OVERBOUGHT WATCHLIST]*")
                for i, a in enumerate(armed_alerts, 1):
                    sym = a["symbol"]
                    prob = a.get("model_probability")
                    score_val = a.get("total_score") or 0.0
                    c_stars, _, _ = _signal_grade(probability=prob, total_score=score_val, recommendation="WATCH", lang="en")
                    prob_str = f"{prob:.1%}" if prob is not None else "N/A"
                    price = a.get("close_price") or 0.0
                    price_str = f"${price:,.4f}" if price > 0 else "N/A"
                    pump_pct = a.get("pump_pct", 0.0)
                    pump_str = f"+{pump_pct:.0%}"
                    detail_url = a.get("web_url") or _coin_url(self._web_base_url, sym)

                    lines.append(f"{i}. 🧭 `{sym}` {c_stars} — Price: `{price_str}` (Pumped {pump_str})")
                    armed_line = f"   • Reasons: HTF Overbought reached (Score: {score_val:.0f}/100), monitoring 5m exhaustion."
                    if detail_url:
                        armed_line += f" [🔗 Chart]({detail_url})"
                    lines.append(armed_line)

            lines.extend(["", "_Reference report from Dao Vang AI; analyze carefully._"])
        else:
            lines = [
                f"📊 *TỔNG HỢP TÍN HIỆU PHÂN PHỐI CHU KỲ* ({len(alerts)} coin){mode_prefix}",
            ]
            if formatted_time:
                lines.append(f"• *Thời điểm:* {formatted_time}")
            lines.append(f"• *Bối cảnh BTC:* {_btc_regime_label(btc_regime, 'vi')}")
            lines.append(f"• *Tổng quan:* ⚡ *{len(fired_alerts)} Tín hiệu mạnh* | 🧭 *{len(armed_alerts)} Canh đỉnh quá mua*")
            lines.append("")

            if fired_alerts:
                lines.append("⚡ *[DANH SÁCH TÍN HIỆU SHORT MẠNH]* 🚨")
                for i, a in enumerate(fired_alerts, 1):
                    sym = a["symbol"]
                    prob = a.get("model_probability")
                    score_val = a.get("total_score") or 0.0
                    c_stars, _, _ = _signal_grade(probability=prob, total_score=score_val, recommendation="HIGH_CONFIDENCE", lang="vi")
                    prob_str = f"{prob:.1%}" if prob is not None else "N/A"
                    price = a.get("close_price") or 0.0
                    price_str = f"${price:,.4f}" if price > 0 else "N/A"
                    pump_pct = a.get("pump_pct", 0.0)
                    pump_days = a.get("pump_days", 0)
                    pump_str = f"+{pump_pct:.0%} ({pump_days} ngày)" if pump_days > 0 else f"+{pump_pct:.0%}"
                    top_sigs = a.get("top_signals", [])
                    sig_names = [_signal_label(s[0], "vi") for s in top_sigs[:2]]
                    sig_str = ", ".join(sig_names) if sig_names else "Xác nhận dấu hiệu xả 5m"
                    detail_url = a.get("web_url") or _coin_url(self._web_base_url, sym)

                    lines.append(f"{i}. ⚡ `{sym}` {c_stars} — Giá: `{price_str}` (Đã tăng {pump_str})")
                    lines.append(f"   • Điểm phân phối: *{score_val:.0f}/100* | Xác suất Short: *{prob_str}*")
                    lines.append(f"   • Lý do: {sig_str}")
                    if detail_url:
                        lines.append(f"   • [🔗 Xem phân tích {sym}]({detail_url})")
                    lines.append("")

            if armed_alerts:
                lines.append("🧭 *[DANH SÁCH CANH ĐỈNH QUÁ MUA]*")
                for i, a in enumerate(armed_alerts, 1):
                    sym = a["symbol"]
                    prob = a.get("model_probability")
                    score_val = a.get("total_score") or 0.0
                    c_stars, _, _ = _signal_grade(probability=prob, total_score=score_val, recommendation="WATCH", lang="vi")
                    prob_str = f"{prob:.1%}" if prob is not None else "N/A"
                    price = a.get("close_price") or 0.0
                    price_str = f"${price:,.4f}" if price > 0 else "N/A"
                    pump_pct = a.get("pump_pct", 0.0)
                    pump_str = f"+{pump_pct:.0%}"
                    detail_url = a.get("web_url") or _coin_url(self._web_base_url, sym)

                    lines.append(f"{i}. 🧭 `{sym}` {c_stars} — Giá: `{price_str}` (Đã tăng {pump_str})")
                    armed_line = f"   • Lý do: Đã vào vùng đỉnh khung lớn (Điểm: {score_val:.0f}/100), đang theo dõi dấu hiệu hụt hơi."
                    if detail_url:
                        armed_line += f" [🔗 Xem chart]({detail_url})"
                    lines.append(armed_line)

            lines.extend(["", "_Báo cáo tự động từ Đảo Vàng AI — Phục vụ mục đích tham khảo & phân tích._"])
        text = "\n".join(lines)
        return self.send_message(text)

    def send_two_tier_alert(
        self,
        symbol: str,
        stage: str,
        total_score: float,
        htf_score: float,
        ltf_score: float,
        pump_pct: float,
        pump_days: int,
        close_price: float | None,
        feature_time: str,
        peak_wick_price: float | None = None,
        web_url: str | None = None,
        operating_mode: str = "production",
    ) -> bool:
        """Send a 2-Tier Climax specialized alert: ARMED (Pre-alert) or FIRED (Execution)."""
        price = close_price or 0.0
        price_str = f"${price:,.4f}" if price > 0 else "N/A"
        mode_label = _mode_label(operating_mode, self._lang)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        if stage.upper() == "ARMED":
            if self._lang == "en":
                lines = [
                    f"🧭 *[OVERBOUGHT WATCHLIST — ARMED]* `{symbol}`{mode_prefix}",
                    f"• *Market Price:* {price_str} | *Pump Amplitude:* `+{pump_pct:.0%}` ({pump_days}d)",
                    f"• *HTF Climax Score:* `{htf_score:.0f}/100` (Tier 1 Overbought)",
                    "• *Why Short:* Extreme overbought conditions reached on high timeframes. Order flow exhaustion being tracked.",
                ]
                if detail_url:
                    lines.append(f"[🔗 Open {symbol} Dashboard]({detail_url})")
            else:
                lines = [
                    f"🧭 *[THEO DÕI VÙNG ĐỈNH QUÁ MUA]* `{symbol}`{mode_prefix}",
                    f"• *Giá thị trường:* {price_str} | *Biên độ bơm:* `+{pump_pct:.0%}` ({pump_days} ngày)",
                    f"• *Điểm đỉnh bơm HTF:* *{htf_score:.0f}/100* (Tầng 1 Quá mua cực hạn)",
                    "• *Lý do theo dõi Short:* Coin đã bơm nóng cực hạn trên khung lớn. Đang theo dõi dấu hiệu hụt hơi dòng tiền.",
                ]
                if detail_url:
                    lines.append(f"[🔗 Mở Radar & Phân Tích {symbol}]({detail_url})")
        else:
            if self._lang == "en":
                lines = [
                    f"⚡ *[DISTRIBUTION SIGNAL — FIRED]* `{symbol}` 🚨{mode_prefix}",
                    f"• *Market Price:* `{price_str}` | *Pump Amplitude:* `+{pump_pct:.0%}` ({pump_days}d)",
                    f"• *2-Tier Confluence Score:* *{total_score:.0f}/100* (HTF: {htf_score:.0f} | LTF: {ltf_score:.0f})",
                    "• *Why Short:* Both HTF pump climax and 5m order flow sell pressure have confirmed.",
                ]
                if detail_url:
                    lines.append(f"[🔗 Open {symbol} Analysis Dashboard]({detail_url})")
            else:
                lines = [
                    f"⚡ *[CẢNH BÁO TÍN HIỆU SHORT — PHÂN PHỐI ĐỈNH]* `{symbol}` 🚨{mode_prefix}",
                    f"• *Giá thị trường:* `{price_str}` | *Biên độ bơm:* `+{pump_pct:.0%}` ({pump_days} ngày)",
                    f"• *Điểm hợp lưu 2 Tầng:* *{total_score:.0f}/100* (Khung lớn: {htf_score:.0f} | Khung 5m: {ltf_score:.0f})",
                    "• *Lý do nên Short:* Hợp lưu đồng thời giữa đỉnh bơm khung lớn và áp lực xả chủ động khung 5m.",
                ]
                if detail_url:
                    lines.append(f"[🔗 Mở Biểu Đồ & Phân Tích {symbol}]({detail_url})")

        lines.extend(["", "_Báo cáo phân tích xác suất từ Đảo Vàng AI._"])
        text = "\n".join(lines)
        return self.send_message(text)

    def send_test(self) -> bool:
        """Send a test message to verify configuration."""
        if self._lang == "en":
            return self.send_message(
                "🧪 *DAO VANG — Test Alert*\n\n"
                "Telegram bot connected successfully. "
                "You will receive alerts when the scanner detects Distribution signals."
            )
        return self.send_message(
            "🧪 *Đảo Vàng — Test*\n\n"
            "Telegram bot đã kết nối thành công. "
            "Bạn sẽ nhận alert khi scanner phát hiện Distribution."
        )

