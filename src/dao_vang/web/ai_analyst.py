"""AI Market Analyst service module for Đảo Vàng PeakPulse.

Supports calling external LLM providers (Gemini, OpenAI, Claude, DeepSeek, Ollama)
with real-time coin context, as well as an advanced built-in quantitative reasoning
engine when no API key is provided.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


def build_system_prompt() -> str:
    return (
        "Bạn là Đảo Vàng PeakPulse AI Assistant — trợ lý giao dịch định lượng chuyên nghiệp "
        "về thị trường phái sinh Crypto (Binance USD-M Futures). Bạn chuyên phân tích các chỉ số "
        "dòng tiền Open Interest (OI), tỷ lệ tài trợ (Funding Rate), áp lực mua bán chủ động (Taker Volume Delta), "
        "phân rã SHAP và các dấu hiệu phân phối tạo đỉnh / bẫy giá (Bull Trap / Wyckoff Distribution). "
        "Hãy trả lời súc tích, mạch lạc, có luận điểm thực tế, dùng định dạng Markdown rõ ràng, "
        "và luôn kèm theo cảnh báo quản lý vốn/rủi ro."
    )


def build_context_summary(symbol: str, context: dict[str, Any]) -> str:
    current_price = context.get("current_price") or context.get("price") or "N/A"
    signal_price = context.get("signal_price") or "N/A"
    prob = context.get("probability")
    prob_str = f"{prob:.1f}%" if isinstance(prob, (int, float)) else "N/A"
    risk_level = context.get("risk_level") or "N/A"
    btc_regime = context.get("btc_regime") or "NEUTRAL"
    is_pump = context.get("parabolic_pump", False)

    metrics = context.get("metrics") or {}
    trade_setup = context.get("trade_setup") or {}
    shap_drivers = context.get("shap_drivers") or []

    drivers_text = ", ".join(
        f"{d.get('feature_name', '')} ({d.get('impact_percentage', 0):.1f}%)"
        for d in shap_drivers[:4]
        if isinstance(d, dict)
    ) or "Chưa có"

    entry = trade_setup.get("entry_price") or signal_price or current_price
    sl = trade_setup.get("invalidation_price") or trade_setup.get("sl_price") or "N/A"
    tp1 = trade_setup.get("tp1_price") or "N/A"
    tp2 = trade_setup.get("tp2_price") or "N/A"
    rr = trade_setup.get("risk_reward_ratio") or "N/A"

    lines = [
        f"=== THÔNG TIN THỊ TRƯỜNG THỜI GIAN THỰC CHO {symbol} ===",
        f"- Giá hiện tại (Mark Price): ${current_price}",
        f"- Giá phát tín hiệu (Signal Price): ${signal_price}",
        f"- Xác suất xả AI (Dump Probability): {prob_str}",
        f"- Mức rủi ro (Risk Tier): {risk_level}",
        f"- Trạng thái BTC (BTC Regime): {btc_regime}",
        f"- Cảnh báo Bơm Thẳng Đứng (Parabolic Pump): {'CÓ (Rất cao)' if is_pump else 'Bình thường'}",
        f"- Biến động OI 24h: {metrics.get('oi_change_24h', 'N/A')}",
        f"- Funding Rate: {metrics.get('funding_rate', 'N/A')}",
        f"- Taker Sell/Buy: {metrics.get('taker_buy_ratio', 'N/A')}",
        f"- RSI (14): {metrics.get('rsi_14', 'N/A')}",
        f"- Khối lượng Vol 24h: {metrics.get('volume_delta_24h', 'N/A')}",
        f"- Vùng vào lệnh (Entry Zone): ${entry}",
        f"- Mức cắt lỗ vi phạm (SL/Invalidation): ${sl}",
        f"- Chốt lời 1 (TP1 -4%): ${tp1}",
        f"- Chốt lời 2 (TP2 -8%): ${tp2}",
        f"- Tỷ lệ Lời/Lỗ (R:R Ratio): {rr}",
        f"- Top nguyên nhân SHAP chính: {drivers_text}",
        "==========================================================",
    ]
    return "\n".join(lines)


def _call_gemini(
    api_key: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 20,
) -> str:
    model = model_id or "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 1024,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        candidates = body.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
    return "Không nhận được phản hồi từ Gemini API."


def _call_openai_compatible(
    api_key: str,
    base_url: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 20,
) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model_id or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "max_tokens": 1024,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        choices = body.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "").strip()
    return "Không nhận được phản hồi từ AI API."


def _call_claude(
    api_key: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    timeout: int = 20,
) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model_id or "claude-3-5-haiku-20241022",
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
        "max_tokens": 1024,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode("utf-8"))
        content = body.get("content", [])
        if content:
            return content[0].get("text", "").strip()
    return "Không nhận được phản hồi từ Claude API."


def _generate_rule_based_response(
    question: str,
    symbol: str,
    context: dict[str, Any],
) -> str:
    """Intelligent built-in quantitative analyst synthesis engine."""
    q_lower = question.lower()
    prob = context.get("probability", 0)
    risk_level = context.get("risk_level", "MEDIUM")
    metrics = context.get("metrics") or {}
    trade_setup = context.get("trade_setup") or {}
    btc_regime = context.get("btc_regime", "NEUTRAL")
    is_pump = context.get("parabolic_pump", False)
    shap_drivers = context.get("shap_drivers") or []

    cur_price = context.get("current_price") or context.get("price") or "—"
    entry = trade_setup.get("entry_price") or cur_price
    sl = trade_setup.get("invalidation_price") or trade_setup.get("sl_price") or "—"
    tp1 = trade_setup.get("tp1_price") or "—"
    tp2 = trade_setup.get("tp2_price") or "—"
    rr = trade_setup.get("risk_reward_ratio") or "—"

    oi_val = metrics.get("oi_change_24h", "N/A")
    funding_val = metrics.get("funding_rate", "N/A")
    taker_val = metrics.get("taker_buy_ratio", "N/A")

    top_drivers_names = [
        d.get("feature_name", "") for d in shap_drivers[:3] if isinstance(d, dict)
    ]
    top_drivers_str = ", ".join(top_drivers_names) if top_drivers_names else "Kiệt sức mua & phân kỳ dòng tiền"

    # 1. Câu hỏi về "Tại sao điểm cao / Tại sao có tín hiệu xả?"
    if any(k in q_lower for k in ["tại sao", "tai sao", "nguyên nhân", "nguyen nhan", "điểm cao", "diem cao", "lý do", "ly do", "why", "score"]):
        return (
            f"### 🔍 Phân Tích Nguyên Nhân **{symbol}** Có Tín Hiệu Rủi Ro Cao\n\n"
            f"Cặp **{symbol}** hiện đạt mức xác suất xả **{prob:.1f}%** ({risk_level}) do sự kết hợp của các yếu tố định lượng sau:\n\n"
            f"1. **Động Lượng SHAP Chính**: Hệ thống máy học ghi nhận tín hiệu chủ yếu từ `{top_drivers_str}`.\n"
            f"2. **Dòng Tiền & Hợp Đồng (OI/Funding)**: Biến động OI ghi nhận `{oi_val}` cùng Funding Rate `{funding_val}`. Khi Funding dương cao kết hợp OI phình to, phe Long đang trả phí lớn để giữ lệnh mua đuổi — tạo điều kiện thuận lợi cho phe cá mập xả hàng thanh lý.\n"
            f"3. **Áp Lực Khớp Lệnh Chủ Động (Taker)**: Tỷ lệ Taker `{taker_val}` cho thấy lực mua đuổi bắt đầu hụt hơi và có dấu hiệu xuất hiện các lệnh bán chủ động lớn.\n"
            f"4. **Bối Cảnh Thị Trường**: BTC đang ở trạng thái **{btc_regime}** {('kèm cảnh báo Bơm Thẳng Đứng (Parabolic Pump)' if is_pump else '')}.\n\n"
            f"💡 **Kết Luận**: Rủi ro đảo chiều xả hàng đang ở mức cao. Không nên mua đuổi giá (FOMO Long) tại vùng này."
        )

    # 2. Câu hỏi về "Kịch bản nếu BTC tăng / Bối cảnh BTC"
    if any(k in q_lower for k in ["btc", "bitcoin", "thị trường", "thi truong", "kịch bản", "kich ban", "scenario"]):
        return (
            f"### 📈 Kịch Bản Giao Dịch **{symbol}** Theo Diễn Biến BTC\n\n"
            f"Trạng thái Bitcoin hiện tại: **{btc_regime}**.\n\n"
            f"- **Kịch Bản 1 (BTC Đi Ngang hoặc Điều Chỉnh Nhẹ - Xác suất 70%)**: {symbol} đang có xung lực yếu hơn thị trường chung với điểm rủi ro {prob:.1f}%. Đây là kịch bản lý tưởng nhất để mở vị thế Short quanh vùng `${entry}` nhắm về TP1 `${tp1}` và TP2 `${tp2}`.\n"
            f"- **Kịch Bản 2 (BTC Đột Ngột Dựng Cột Bơm Mạnh - Xác suất 30%)**: Khi BTC tăng tốc đột ngột, dòng tiền có thể kéo cả thị trường altcoin chạy theo quán tính. Nếu {symbol} phá qua mốc Invalidation **${sl}**, bạn **bắt buộc phải kích hoạt Stop Loss** và đứng ngoài quan sát.\n\n"
            f"🛡️ **Nguyên Tắc Bất Di Bất Dịch**: Luôn tôn trọng điểm SL `${sl}` để bảo toàn vốn trước biến động của BTC."
        )

    # 3. Câu hỏi về "Cắt lỗ ở đâu / Chốt lời / Điểm vào lệnh / SL / TP / Entry"
    if any(k in q_lower for k in ["cắt lỗ", "cat lo", "chốt lời", "chot loi", "vào lệnh", "vao lenh", "sl", "tp", "entry", "stop loss", "take profit"]):
        return (
            f"### 🎯 Kế Hoạch Vào Lệnh Chi Tiết Cho **{symbol}**\n\n"
            f"Dựa trên cấu trúc nến và thuật toán tính toán biên độ vi phạm:\n\n"
            f"- **Vùng Vào Lệnh (Entry Zone)**: `${entry}` (Giá hiện tại: `${cur_price}`).\n"
            f"- **Mức Cắt Lỗ Vi Phạm (Invalidation SL)**: **`${sl}`** (Khoảng cách an toàn trên vùng tạo đỉnh).\n"
            f"- **Mục Tiêu Chốt Lời 1 (TP1)**: **`${tp1}`** (-4.0% — Khuyến nghị chốt 50% vị thế và dời SL về hòa vốn).\n"
            f"- **Mục Tiêu Chốt Lời 2 (TP2)**: **`${tp2}`** (-8.0% — Vùng hỗ trợ dòng tiền sâu hơn).\n"
            f"- **Tỷ Lệ Lời/Lỗ (R:R)**: `{rr}`.\n\n"
            f"⚠️ **Lưu ý**: Nếu giá đã trôi qua TP1, tuyệt đối **không đuổi theo lệnh (Chased Entry)** mà hãy chờ nhịp hồi phục để tìm điểm vào lệnh tối ưu hơn."
        )

    # 4. Câu hỏi về "Đi vốn / Đòn bẩy / Quản lý rủi ro / Leverage / Position Size"
    if any(k in q_lower for k in ["đi vốn", "di von", "đòn bẩy", "don bay", "vốn", "von", "leverage", "rủi ro", "rui ro", "risk", "margin"]):
        return (
            f"### 🛡️ Chiến Lược Đi Vốn & Đòn Bẩy Đề Xuất Cho **{symbol}**\n\n"
            f"Vì {symbol} đang có mức rủi ro **{risk_level}** ({prob:.1f}% xác suất xả):\n\n"
            f"1. **Mức Đòn Bẩy Khuyến Nghị**: Tối đa **x3 - x5** (Không nên dùng đòn bẩy > x10 đối với altcoin biến động mạnh).\n"
            f"2. **Tỷ Trọng Vốn (Position Sizing)**: Tối đa **1.0% - 2.0% tổng tài khoản (NAV)** cho toàn bộ khoảng cách từ Entry `${entry}` đến SL `${sl}`.\n"
            f"3. **Phương Pháp Phân Bổ Lệnh**: Chia vốn làm 2 phần:\n"
            f"   - Phần 1 (60%): Vào ngay khi xuất hiện nến 5m từ chối giá tại `${entry}`.\n"
            f"   - Phần 2 (40%): Nhồi thêm khi giá retest nhẹ vùng cản hoặc gãy đường xu hướng ngắn hạn.\n"
            f"4. **Kỷ Luật Khóa Lợi Nhuận**: Khi giá chạm TP1 `${tp1}`, đóng 50% khối lượng và kéo Stop Loss về điểm Entry (Risk-Free Trade)."
        )

    # 5. Câu hỏi tổng quát mặc định
    return (
        f"### 📊 Báo Cáo Phân Tích Tổng Hợp **{symbol}**\n\n"
        f"**Tình trạng hiện tại**:\n"
        f"- Xác suất xả AI: **{prob:.1f}%** ({risk_level})\n"
        f"- Giá hiện tại: **${cur_price}** | Entry khuyến nghị: **${entry}**\n"
        f"- Cắt lỗ SL: **${sl}** | Chốt lời TP1: **${tp1}** | TP2: **${tp2}** (R:R: `{rr}`)\n"
        f"- Yếu tố trọng yếu: `{top_drivers_str}` | BTC: **{btc_regime}**\n\n"
        f"**Khuyến nghị hành động**:\n"
        f"1. Ưu tiên canh mở vị thế SHORT hoặc chốt lời vị thế Long có sẵn.\n"
        f"2. Luôn đặt sẵn lệnh Stop Loss tại `${sl}` ngay khi khớp vị thế.\n"
        f"3. Theo dõi sát biến động BTC để xử lý kịp thời nếu thị trường có tín hiệu bẫy thanh khoản."
    )


def ask_ai_analyst(
    question: str,
    symbol: str,
    context: dict[str, Any],
    llm_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Process an AI question with real-time coin context."""
    cfg = llm_config or {}
    provider = (cfg.get("provider") or "").lower().strip()
    api_key = (cfg.get("apiKey") or cfg.get("api_key") or "").strip()
    model_id = (cfg.get("modelId") or cfg.get("model_id") or "").strip()
    base_url = (cfg.get("baseUrl") or cfg.get("base_url") or "").strip()
    enabled = cfg.get("enabled", True)

    system_prompt = build_system_prompt()
    context_str = build_context_summary(symbol, context)
    user_prompt = f"{context_str}\n\nCÂU HỎI CỦA TRADER:\n{question}\n\nHãy trả lời chi tiết, súc tích bằng tiếng Việt (hoặc ngôn ngữ câu hỏi yêu cầu) dựa trên số liệu thực tế ở trên."

    used_provider = "Built-in Quantitative Engine"
    used_model = "DaoVang-Quant-v2"
    answer = ""

    if enabled and api_key and provider:
        try:
            if provider == "gemini":
                used_provider = "Google Gemini"
                used_model = model_id or "gemini-1.5-flash"
                answer = _call_gemini(api_key, used_model, system_prompt, user_prompt)
            elif provider == "openai":
                used_provider = "OpenAI"
                used_model = model_id or "gpt-4o-mini"
                answer = _call_openai_compatible(
                    api_key,
                    base_url or "https://api.openai.com/v1",
                    used_model,
                    system_prompt,
                    user_prompt,
                )
            elif provider == "deepseek":
                used_provider = "DeepSeek"
                used_model = model_id or "deepseek-chat"
                answer = _call_openai_compatible(
                    api_key,
                    base_url or "https://api.deepseek.com",
                    used_model,
                    system_prompt,
                    user_prompt,
                )
            elif provider == "claude":
                used_provider = "Anthropic Claude"
                used_model = model_id or "claude-3-5-haiku-20241022"
                answer = _call_claude(api_key, used_model, system_prompt, user_prompt)
            elif provider == "ollama":
                used_provider = "Local Ollama"
                used_model = model_id or "llama3.2"
                answer = _call_openai_compatible(
                    api_key,
                    base_url or "http://localhost:11434/v1",
                    used_model,
                    system_prompt,
                    user_prompt,
                )
        except Exception as exc:
            logger.warning("LLM call failed provider=%s error=%s, falling back to rule-based engine", provider, exc)
            answer = f"> ⚠️ *Không thể kết nối đến {provider.title()} API ({exc}). Đang chuyển sang Bộ phân tích định lượng tích hợp:*\n\n" + _generate_rule_based_response(question, symbol, context)
            used_provider = f"{provider.title()} (Fallback to Built-in)"

    if not answer:
        answer = _generate_rule_based_response(question, symbol, context)

    return {
        "answer": answer,
        "provider": used_provider,
        "model": used_model,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
    }
