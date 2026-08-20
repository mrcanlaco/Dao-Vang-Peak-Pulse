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
        price_str = f"${close_price:,.4f}" if close_price else "N/A"
        mode_label = _mode_label(operating_mode, self._lang)
        detail_url = web_url or _coin_url(self._web_base_url, symbol)
        mode_prefix = f" `[{mode_label}]`" if operating_mode != "production" else ""

        if self._lang == "en":
            top_sig_names = [_signal_label(s[0], "en") for s in top_signals[:2]]
            sig_summary = ", ".join(top_sig_names) if top_sig_names else "Distribution pattern detected"
            prob_str = f"{model_probability:.1%}" if model_probability is not None else "N/A"
            pump_str = f"+{pump_pct:.0%} in {pump_days} days" if pump_days > 0 else f"+{pump_pct:.0%}"
            rec_label = _recommendation_label(normalized_recommendation, "en")
            btc_lbl = _btc_regime_label(btc_regime, "en")

            lines = [
                f"{color_badge} *SIGNAL REPORT — `{symbol}`* {stars}{mode_prefix}",
                f"• *Grade & Score:* {stars} `{grade_title}` | *Score:* {total_score:.0f}/100",
                f"• *Recommendation:* `{rec_label}` | *Probability:* `{prob_str}`",
                f"• *Close Price:* {price_str} (Pumped {pump_str})",
                f"• *Key Signals:* {sig_summary}",
                f"• *BTC Context:* {btc_lbl}",
            ]
            if detail_url:
                lines.append(f"[🔗 Open {symbol} Analysis Dashboard]({detail_url})")
            lines.extend(["", "_Reference report; no automated orders._"])
        else:
            top_sig_names = [_signal_label(s[0], "vi") for s in top_signals[:2]]
            sig_summary = ", ".join(top_sig_names) if top_sig_names else "Đạt điều kiện phân phối"
            prob_str = f"{model_probability:.1%}" if model_probability is not None else "N/A"
            pump_str = f"+{pump_pct:.0%} trong {pump_days} ngày" if pump_days > 0 else f"+{pump_pct:.0%}"
            rec_label = _recommendation_label(normalized_recommendation, "vi")
            btc_lbl = _btc_regime_label(btc_regime, "vi")

            lines = [
                f"{color_badge} *BÁO CÁO TÍN HIỆU — `{symbol}`* {stars}{mode_prefix}",
                f"• *Cấp độ:* {stars} `{grade_title}` | *Điểm:* {total_score:.0f}/100",
                f"• *Kết luận:* `{rec_label}` | *Xác suất:* `{prob_str}`",
                f"• *Giá đóng cửa:* {price_str} (Tăng {pump_str})",
                f"• *Tín hiệu chính:* {sig_summary}",
                f"• *Bối cảnh BTC:* {btc_lbl}",
            ]
            if detail_url:
                lines.append(f"[🔗 Mở trang phân tích {symbol}]({detail_url})")
            lines.extend(["", "_Báo cáo tham khảo; không tự động đặt lệnh._"])

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

        if self._lang == "en":
            lines = [
                f"📊 *RADAR CYCLE DIGEST* ({len(alerts)} coins){mode_prefix}",
            ]
            if formatted_time:
                lines.append(f"*Time:* {formatted_time}")
            lines.extend([
                f"*BTC Context:* {_btc_regime_label(btc_regime, 'en')}",
                "",
                f"Detected *{len(alerts)} distribution candidates*:",
            ])
            for i, a in enumerate(alerts, 1):
                sym = a["symbol"]
                prob = a.get("model_probability")
                score_val = a.get("total_score")
                rec_val = a.get("recommendation", "")
                c_stars, c_badge, c_title = _signal_grade(
                    probability=prob,
                    total_score=score_val,
                    recommendation=rec_val,
                    lang=self._lang,
                )
                prob_str = f"{prob:.1%}" if prob is not None else "N/A"
                price = a.get("close_price")
                price_str = f"${price:,.4f}" if price else "N/A"
                pump_pct = a.get("pump_pct", 0.0)
                pump_days = a.get("pump_days", 0)
                pump_str = f"+{pump_pct:.0%} ({pump_days}d)" if pump_days > 0 else f"+{pump_pct:.0%}"
                top_sigs = a.get("top_signals", [])
                sig_names = [_signal_label(s[0], "en") for s in top_sigs[:2]]
                sig_str = ", ".join(sig_names) if sig_names else "High probability"
                detail_url = a.get("web_url") or _coin_url(self._web_base_url, sym)
                link_md = f" [🔗 Open]({detail_url})" if detail_url else ""

                lines.append(f"{i}. {c_badge} `{sym}` {c_stars} — {price_str} ({pump_str})")
                lines.append(f"   • Prob: *{prob_str}* (`{c_title}`) | Signals: {sig_str}{link_md}")

            lines.extend(["", "_Reference report; DYOR before making any trading decisions._"])
        else:
            lines = [
                f"📊 *TỔNG HỢP CẢNH BÁO CHU KỲ* ({len(alerts)} coin){mode_prefix}",
            ]
            if formatted_time:
                lines.append(f"*Thời điểm:* {formatted_time}")
            lines.extend([
                f"*Bối cảnh BTC:* {_btc_regime_label(btc_regime, 'vi')}",
                "",
                f"Phát hiện *{len(alerts)} ứng viên* phân phối nổi bật:",
            ])
            for i, a in enumerate(alerts, 1):
                sym = a["symbol"]
                prob = a.get("model_probability")
                score_val = a.get("total_score")
                rec_val = a.get("recommendation", "")
                c_stars, c_badge, c_title = _signal_grade(
                    probability=prob,
                    total_score=score_val,
                    recommendation=rec_val,
                    lang=self._lang,
                )
                prob_str = f"{prob:.1%}" if prob is not None else "N/A"
                price = a.get("close_price")
                price_str = f"${price:,.4f}" if price else "N/A"
                pump_pct = a.get("pump_pct", 0.0)
                pump_days = a.get("pump_days", 0)
                pump_str = f"+{pump_pct:.0%} ({pump_days} ngày)" if pump_days > 0 else f"+{pump_pct:.0%}"
                top_sigs = a.get("top_signals", [])
                sig_names = [_signal_label(s[0], "vi") for s in top_sigs[:2]]
                sig_str = ", ".join(sig_names) if sig_names else "Tín hiệu phân phối"
                detail_url = a.get("web_url") or _coin_url(self._web_base_url, sym)
                link_md = f" [🔗 Xem chart]({detail_url})" if detail_url else ""

                lines.append(f"{i}. {c_badge} `{sym}` {c_stars} — {price_str} ({pump_str})")
                lines.append(f"   • Xác suất: *{prob_str}* (`{c_title}`) | Tín hiệu: {sig_str}{link_md}")

            lines.extend(["", "_Báo cáo tham khảo; hãy tự kiểm tra trước khi quyết định._"])

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
        binance_url = f"https://www.binance.com/en/futures/{symbol}"
        okx_sym = symbol.replace("USDT", "-USDT-SWAP").lower() if symbol.endswith("USDT") else f"{symbol}-SWAP".lower()
        okx_url = f"https://www.okx.com/trade-swap/{okx_sym}"

        # Adaptive SL calculation
        if peak_wick_price and peak_wick_price > price:
            sl_price = peak_wick_price * 1.005
            sl_pct = ((sl_price - price) / price) * 100
        else:
            sl_pct = 3.5
            sl_price = price * 1.035

        tp1_price = price * 0.96
        tp2_price = price * 0.92
        tp3_price = price * 0.86
        rr_ratio = (8.0 / sl_pct) if sl_pct > 0 else 2.3

        if stage.upper() == "ARMED":
            if self._lang == "en":
                lines = [
                    f"🧭 *[SHORT WATCHLIST — ARMED]* `{symbol}`{mode_prefix}",
                    f"• *Status:* `Tier 1: HTF PUMP CLIMAX ARMED` (Score: {htf_score:.0f}/100)",
                    f"• *Pump Amplitude:* `+{pump_pct:.0%}` ({pump_days}d)",
                    f"• *Current Price:* {price_str}",
                    f"• *Action:* Extreme overbought zone reached. Stand by for 5m order flow dump trigger.",
                ]
                if detail_url:
                    lines.append(f"[🔗 Open {symbol} Cockpit Dashboard]({detail_url})")
            else:
                lines = [
                    f"🧭 *[CANH VỊ THẾ SHORT — ARMED]* `{symbol}`{mode_prefix}",
                    f"• *Trạng thái:* `Tầng 1: Đỉnh Bơm Khung Lớn (ARMED)` | Điểm: *{htf_score:.0f}/100*",
                    f"• *Biên độ bơm:* `+{pump_pct:.0%}` ({pump_days} ngày)",
                    f"• *Giá thị trường:* {price_str}",
                    f"• *Khuyến nghị:* Coin đã vào vùng bơm nóng cực hạn. Chuẩn bị sẵn vốn & mở biểu đồ chờ cò xả 5m.",
                ]
                if detail_url:
                    lines.append(f"[🔗 Mở Radar & Bảng Điều Khiển {symbol}]({detail_url})")
        else:
            if self._lang == "en":
                lines = [
                    f"⚡ *[SHORT EXECUTION — FIRED]* `{symbol}` 🚨{mode_prefix}",
                    f"• *2-Tier Confluence:* `ARMED` + `FIRED` | Total Score: *{total_score:.0f}/100*",
                    f"• *Entry Zone:* `{price_str}`",
                    f"• *Adaptive Stop Loss:* `${sl_price:,.4f}` (+{sl_pct:.1f}% wick buffer)",
                    f"• *Multi-Tier Take Profit:*",
                    f"  🎯 *TP1:* `${tp1_price:,.4f}` (-4.0% — Close 50% & SL to Entry)",
                    f"  🎯 *TP2:* `${tp2_price:,.4f}` (-8.0% — Close 30%)",
                    f"  🎯 *TP3:* `${tp3_price:,.4f}` (-14.0% — Trailing remaining 20%)",
                    f"• *Risk / Reward:* `1 : {rr_ratio:.2f}`",
                    f"• *Direct Terminals:* [Binance Futures]({binance_url}) | [OKX Futures]({okx_url})",
                ]
                if detail_url:
                    lines.append(f"[🔗 Open 1-Click Order Modal]({detail_url})")
            else:
                lines = [
                    f"⚡ *[VÀO LỆNH SHORT NGAY — FIRED]* `{symbol}` 🚨{mode_prefix}",
                    f"• *Hợp lưu 2 Tầng:* `ARMED` + `FIRED` | Điểm tổng: *{total_score:.0f}/100*",
                    f"• *Điểm vào lệnh (Entry):* `{price_str}`",
                    f"• *Cắt lỗ (Adaptive SL):* `${sl_price:,.4f}` (+{sl_pct:.1f}% theo đỉnh râu nến 5m)",
                    f"• *Chiến lược Chốt lời Đa tầng:*",
                    f"  🎯 *TP1:* `${tp1_price:,.4f}` (-4.0% — Đóng 50% & Dời SL về Entry hòa vốn)",
                    f"  🎯 *TP2:* `${tp2_price:,.4f}` (-8.0% — Đóng 30%)",
                    f"  🎯 *TP3:* `${tp3_price:,.4f}` (-14.0% — Gồng Trailing 20% còn lại)",
                    f"• *Tỷ lệ Lợi nhuận / Rủi ro:* `1 : {rr_ratio:.2f}`",
                    f"• *Sàn giao dịch:* [Mở Binance Futures]({binance_url}) | [Mở OKX Futures]({okx_url})",
                ]
                if detail_url:
                    lines.append(f"[🔗 Mở Bảng Vào Lệnh 1-Chạm]({detail_url})")

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

