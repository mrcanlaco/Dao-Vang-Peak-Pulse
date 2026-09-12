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

from dao_vang.config.settings import load_runtime_settings

logger = logging.getLogger(__name__)


DEFAULT_PROJECT_KNOWLEDGE = """
=== KIẾN THỨC NỀN VỀ DỰ ÁN DAO VANG / PEAKPULSE AI ===
- DAO VANG là dashboard cảnh báo sớm cho thị trường Binance USD-M Futures. Mục tiêu là phát hiện dấu hiệu phân phối/tạo đỉnh và rủi ro đảo chiều của crypto; đây không phải hệ thống đảm bảo lợi nhuận hay lệnh giao dịch tự động.
- Luồng dữ liệu chính gồm nến 5m và các dữ liệu phái sinh như Open Interest (OI), Funding Rate, Taker Sell/Buy, khối lượng, RSI và bối cảnh BTC. Dữ liệu được kiểm tra chất lượng và tính theo thời điểm thực tế để hạn chế nhìn trước tương lai.
- Kết quả cần phân biệt rõ: calibrated/model probability là xác suất đã hiệu chuẩn của model; heuristic/composite score là điểm luật và tín hiệu định lượng; anomaly score là điểm radar bất thường độc lập, không phải xác suất.
- Decision Center hiển thị chart, Trade Setup, metrics, AI Decision Cockpit, các thành phần điểm có trọng số và Executive Briefing cho coin đang chọn. Các thành phần này không phải SHAP và không chứng minh quan hệ nhân quả. Radar hiển thị tín hiệu và bộ lọc. Tracking/Watchlist theo dõi vị thế. Candidate Ranking xếp hạng ứng viên và so sánh các bộ lọc.
- Nhóm Lab gồm Multi-Scan, Backtest Experiments và Forward Test. Nhóm System gồm Model Audit, Telemetry, System History, Models, Updates và System Settings.
- Có giao diện V1 cổ điển và V2 responsive theo phong cách trading cockpit; V2 có thanh điều hướng mobile. Scanner chạy model frozen/champion đang được cấu hình; challenger/self-learning chỉ dùng để so sánh hoặc đề xuất và không tự động thay champion.
- Model scanner (tạo tín hiệu) và model LLM (trả lời hội thoại) là hai cấu hình khác nhau; khi người dùng hỏi “model hiện tại”, hãy nói rõ đang nói đến loại nào. Trợ lý AI dùng provider/model trong cấu hình LLM hiện tại của ứng dụng; nếu API không khả dụng, hệ thống có thể chuyển sang Built-in Quantitative Engine. Khi trả lời, phải bám dữ liệu hiện tại được cung cấp, nói rõ khi thiếu dữ liệu và không tự bịa chỉ số.
""".strip()


def build_app_context_summary(context: dict[str, Any]) -> str:
    """Serialize safe, current UI state for questions about using the app."""
    app_context = context.get("app_context")
    if not isinstance(app_context, dict):
        return ""

    counts = app_context.get("dashboard_counts")
    count_text = ""
    if isinstance(counts, dict):
        count_text = (
            f"Tín hiệu đang có: {counts.get('active_signals', 'N/A')}; "
            f"ứng viên: {counts.get('candidates', 'N/A')}; "
            f"vị thế theo dõi: {counts.get('tracked_positions', 'N/A')}"
        )

    scan_modes = app_context.get("active_scan_modes")
    scan_text = ", ".join(str(mode) for mode in scan_modes) if isinstance(scan_modes, list) else str(scan_modes or "N/A")
    lines = [
        "=== TRẠNG THÁI GIAO DIỆN HIỆN TẠI ===",
        f"- Ngôn ngữ: {app_context.get('language', 'vi')}",
        f"- Màn hình đang mở: {app_context.get('active_tab_label') or app_context.get('active_tab', 'N/A')}",
        f"- Phiên bản giao diện: {app_context.get('gui_version', 'N/A')}",
        f"- Chế độ quét: {scan_text}",
        f"- Model scanner hiện tại: {app_context.get('scanner_model_id', 'N/A')}",
        f"- Khóa lựa chọn model: {app_context.get('selected_model_key', 'N/A')}",
        f"- Provider/model LLM hội thoại: {app_context.get('llm_provider', 'N/A')} / {app_context.get('llm_model_id', 'N/A')}",
        f"- Trạng thái scanner: {app_context.get('scanner_status', 'N/A')}",
    ]
    if count_text:
        lines.append(f"- {count_text}")
    return "\n".join(lines)


def build_system_prompt(symbol: str, context_str: str, app_context_str: str = "") -> str:
    project_context = app_context_str.strip() or "Không có thêm trạng thái giao diện động."
    return (
        f"Bạn là Đảo Vàng PeakPulse AI — Trợ lý Phân tích Định lượng & Cố vấn Chiến thuật Giao dịch Cấp cao (chuyên sâu thị trường Binance USD-M Futures).\n\n"
        f"{DEFAULT_PROJECT_KNOWLEDGE}\n\n"
        f"{project_context}\n\n"
        f"DƯỚI ĐÂY LÀ DỮ LIỆU ĐỊNH LƯỢNG THỰC TẾ CỦA {symbol} TRÊN SÀN BINANCE:\n"
        f"{context_str}\n\n"
        f"NGUYÊN TẮC GIAO TIẾP & ĐỊNH DẠNG BÁO CÁO:\n"
        f"1. GIAO TIẾP TỰ NHIÊN, CÓ HỒN: Hãy đối thoại tự nhiên, thân thiện và sắc bén như một Pro Trader / Quantitative Analyst dạn dày kinh nghiệm đang trò chuyện trực tiếp 1-1 với trader. Tránh xa lối nói văn mẫu, không lặp lại các tiêu đề mục cứng nhắc nếu người dùng chỉ hỏi một câu cụ thể.\n"
        f"2. ĐI THẲNG VÀO TRỌNG TÂM: Trả lời trực diện câu hỏi của trader trước tiên, sau đó giải thích logic đằng sau (tại sao số liệu lại dẫn đến nhận định đó).\n"
        f"3. BÁM SÁT BẰNG CHỨNG: Chỉ mô tả những gì các chỉ số quan sát được và thành phần điểm có trọng số thực sự cho biết. Không gọi thành phần điểm là SHAP, không suy diễn hành vi cá voi/tổ chức, quan hệ nhân quả hoặc xác suất kịch bản nếu dữ liệu không cung cấp trực tiếp.\n"
        f"4. BẢNG BIỂU & TÍNH TOÁN RÕ RÀNG: Khi người dùng hỏi về vốn, đòn bẩy hoặc so sánh kịch bản, chỉ tính từ số liệu họ đã cung cấp và nêu rõ dữ liệu còn thiếu. Không tự đặt tỷ lệ vốn, đòn bẩy hay xác suất; phân biệt mốc tham chiếu của hệ thống với khuyến nghị cá nhân.\n"
        f"5. TUYỆT ĐỐI KHÔNG DÙNG KÝ HIỆU LATEX: Dùng ký tự Unicode trực tiếp như mũi tên `→`, dấu `≥`, `≤`, `≈`, `×`, `±`. Tuyệt đối không viết `$\\rightarrow$` hay `$\\approx$` vì gây lỗi hiển thị giao diện.\n"
        f"6. LIÊN KẾT MẠCH HỘI THOẠI: Nếu đây là câu hỏi tiếp nối trong cuộc trò chuyện, hãy nhớ ngữ cảnh trước đó để trả lời mượt mà, không lặp lại những gì đã nói."
    )


def build_context_summary(symbol: str, context: dict[str, Any]) -> str:
    current_price = context.get("current_price") or context.get("price") or "N/A"
    signal_price = context.get("signal_price") or "N/A"
    prob = context.get("probability")
    prob_str = f"{prob:.1f}%" if isinstance(prob, (int, float)) else "N/A"
    risk_level = context.get("risk_level") or "N/A"
    btc_regime = context.get("btc_regime") or "NEUTRAL"
    is_pump = context.get("parabolic_pump", False)

    raw_metrics = context.get("metrics")
    metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
    raw_trade_setup = context.get("trade_setup")
    trade_setup = raw_trade_setup if isinstance(raw_trade_setup, dict) else {}
    raw_feature_drivers = context.get("feature_drivers")
    feature_drivers = raw_feature_drivers if isinstance(raw_feature_drivers, list) else []

    driver_parts: list[str] = []
    for driver in feature_drivers[:4]:
        if not isinstance(driver, dict):
            continue
        name = driver.get("feature_name") or driver.get("feature") or "unknown"
        raw_impact = driver.get("impact_percentage", driver.get("impact_score", 0))
        try:
            impact = f"{float(raw_impact):.1f}%"
        except (TypeError, ValueError):
            impact = "N/A"
        driver_parts.append(f"{name} ({impact})")
    drivers_text = ", ".join(driver_parts) or "Chưa có"

    entry = trade_setup.get("entry_price") or signal_price or current_price
    sl = trade_setup.get("invalidation_price") or trade_setup.get("sl_price") or trade_setup.get("stop_loss") or "N/A"
    tp1 = trade_setup.get("tp1_price") or trade_setup.get("tp1") or "N/A"
    tp2 = trade_setup.get("tp2_price") or trade_setup.get("tp2") or "N/A"
    rr = trade_setup.get("risk_reward_ratio") or trade_setup.get("rr_ratio") or "N/A"

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
        f"- Taker Sell/Buy: {metrics.get('taker_buy_ratio', metrics.get('taker_sell_ratio', 'N/A'))}",
        f"- RSI (14): {metrics.get('rsi_14', metrics.get('rsi_15m', 'N/A'))}",
        f"- Khối lượng Vol 24h: {metrics.get('volume_delta_24h', 'N/A')}",
        f"- Vùng vào lệnh (Entry Zone): ${entry}",
        f"- Mức cắt lỗ vi phạm (SL/Invalidation): ${sl}",
        f"- Chốt lời 1 (TP1 -4%): ${tp1}",
        f"- Chốt lời 2 (TP2 -8%): ${tp2}",
        f"- Tỷ lệ Lời/Lỗ (R:R Ratio): {rr}",
        f"- Thành phần đóng góp điểm lớn nhất: {drivers_text}",
        "- Phương pháp diễn giải: trọng số thành phần; không phải SHAP hay quy kết nhân quả",
        "==========================================================",
    ]
    return "\n".join(lines)


def _call_gemini(
    api_key: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    history: list[dict[str, str]] | None = None,
    timeout: int = 25,
) -> str:
    model = model_id or "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    contents = []
    if history:
        for turn in history[-8:]:
            r = "user" if turn.get("role") == "user" else "model"
            c = (turn.get("content") or "").strip()
            if c:
                contents.append({"role": r, "parts": [{"text": c}]})
    contents.append({"role": "user", "parts": [{"text": user_prompt}]})

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "generationConfig": {
            "temperature": 0.4,
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
    history: list[dict[str, str]] | None = None,
    timeout: int = 25,
) -> str:
    endpoint = base_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        url = endpoint + "/chat/completions"
    else:
        url = endpoint

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (compatible; DaoVangAI/2.0)",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    messages = [{"role": "system", "content": system_prompt}]
    if history:
        for turn in history[-8:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": model_id or "gpt-4o-mini",
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 1024,
        "stream": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw_text = resp.read().decode("utf-8")
        try:
            body = json.loads(raw_text)
            choices = body.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                if isinstance(msg, dict):
                    content = msg.get("content", "")
                    if content:
                        return content.strip()
                delta = choices[0].get("delta", {})
                if isinstance(delta, dict) and delta.get("content"):
                    return delta.get("content", "").strip()
        except json.JSONDecodeError:
            # Handle SSE stream fallback if custom proxy responds in text/event-stream
            collected = []
            for line in raw_text.splitlines():
                line = line.strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk = json.loads(line[6:])
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            if isinstance(delta, dict) and delta.get("content"):
                                collected.append(delta["content"])
                    except Exception:
                        pass
            if collected:
                return "".join(collected).strip()
    return "Không nhận được phản hồi từ AI API."


def _call_claude(
    api_key: str,
    model_id: str,
    system_prompt: str,
    user_prompt: str,
    history: list[dict[str, str]] | None = None,
    timeout: int = 25,
) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    messages = []
    if history:
        for turn in history[-8:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": model_id or "claude-3-5-haiku-20241022",
        "system": system_prompt,
        "messages": messages,
        "max_tokens": 1024,
        "temperature": 0.4,
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


def _generate_project_response(symbol: str, context: dict[str, Any]) -> str:
    """Answer common product/how-to questions without requiring an external LLM."""
    raw_app_context = context.get("app_context")
    app_context = raw_app_context if isinstance(raw_app_context, dict) else {}
    active_tab = app_context.get("active_tab_label") or app_context.get("active_tab") or "màn hình hiện tại"
    scanner_model = app_context.get("scanner_model_id") or app_context.get("selected_model_key") or "model đang cấu hình"
    llm_model = app_context.get("llm_model_id") or "LLM model đang cấu hình"
    language = str(app_context.get("language") or "vi").lower()

    if language == "en":
        return (
            f"### 🧭 DAO VANG app overview\n\n"
            f"You are currently on **{active_tab}**, with **{symbol}** as the active context. DAO VANG is a Binance USD-M Futures early-warning dashboard for distribution/top-formation and reversal risk.\n\n"
            f"- **Decision Center**: chart, trade setup, metrics, weighted score components and the executive AI brief. Components are not SHAP or causal attribution.\n"
            f"- **Radar**: active signals and advanced filters. **Tracking** stores positions to monitor. **Candidate Ranking** compares discovered coins and filters.\n"
            f"- **Lab**: Multi-Scan, Backtest Experiments and Forward Test. **System**: Model Audit, Telemetry, History, Models, Updates and Settings.\n"
            f"- The current scanner model is **{scanner_model}**. Frozen/champion output is the serving lane; challenger and self-learning results remain observational until explicitly promoted.\n"
            f"- The conversation is handled by the configured LLM model **{llm_model}**.\n\n"
            f"The assistant receives the current screen/coin context with every question. Missing data is reported as unavailable; scores are not guarantees or automatic orders."
        )

    return (
        f"### 🧭 Tổng quan ứng dụng DAO VANG\n\n"
        f"Bạn đang ở **{active_tab}**, với **{symbol}** là ngữ cảnh hiện tại. DAO VANG là dashboard cảnh báo sớm thị trường Binance USD-M Futures, tập trung phát hiện phân phối/tạo đỉnh và rủi ro đảo chiều.\n\n"
        f"- **Decision Center**: biểu đồ, Trade Setup, các chỉ số, thành phần điểm có trọng số và bản tin AI tổng hợp. Đây không phải SHAP hay quy kết nhân quả.\n"
        f"- **Radar**: tín hiệu đang hoạt động và bộ lọc nâng cao. **Tracking** dùng để theo dõi vị thế. **Xếp hạng ứng viên** dùng để so sánh các coin/bộ lọc.\n"
        f"- **Lab**: Multi-Scan, Backtest Experiments và Forward Test. **System**: Model Audit, Telemetry, History, Models, Updates và Settings.\n"
        f"- Model scanner hiện tại là **{scanner_model}**. Model frozen/champion là luồng phục vụ; challenger và self-learning chỉ mang tính quan sát cho đến khi được duyệt rõ ràng.\n"
        f"- Hội thoại đang dùng model LLM **{llm_model}**.\n\n"
        f"Trợ lý nhận màn hình/coin hiện tại trong mỗi câu hỏi. Nếu thiếu dữ liệu, hệ thống sẽ báo chưa có; mọi điểm số chỉ là hỗ trợ phân tích, không phải cam kết lợi nhuận hay lệnh tự động."
    )


def _generate_rule_based_response(
    question: str,
    symbol: str,
    context: dict[str, Any],
) -> str:
    """Build an evidence-bound summary when an external LLM is unavailable."""
    q_lower = question.lower()
    raw_probability = context.get("probability")
    probability_text = (
        f"{float(raw_probability):.1f}%"
        if isinstance(raw_probability, (int, float)) and not isinstance(raw_probability, bool)
        else "chưa có"
    )
    risk_level = str(context.get("risk_level") or "chưa có")
    raw_metrics = context.get("metrics")
    metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
    raw_trade_setup = context.get("trade_setup")
    trade_setup = raw_trade_setup if isinstance(raw_trade_setup, dict) else {}
    btc_regime = str(context.get("btc_regime") or "chưa có")
    is_pump = context.get("parabolic_pump") is True
    raw_feature_drivers = context.get("feature_drivers")
    feature_drivers = raw_feature_drivers if isinstance(raw_feature_drivers, list) else []

    cur_price = context.get("current_price") or context.get("price") or "—"
    entry = trade_setup.get("entry_price") or cur_price
    sl = trade_setup.get("invalidation_price") or trade_setup.get("sl_price") or trade_setup.get("stop_loss") or "—"
    tp1 = trade_setup.get("tp1_price") or trade_setup.get("tp1") or "—"
    tp2 = trade_setup.get("tp2_price") or trade_setup.get("tp2") or "—"
    rr = trade_setup.get("risk_reward_ratio") or trade_setup.get("rr_ratio") or "—"

    oi_val = metrics.get("oi_change_24h", "N/A")
    funding_val = metrics.get("funding_rate", "N/A")
    taker_val = metrics.get("taker_buy_ratio", metrics.get("taker_sell_ratio", "N/A"))

    top_drivers_names = [
        d.get("feature_name") or d.get("feature") or ""
        for d in feature_drivers[:3]
        if isinstance(d, dict)
    ]
    top_drivers_str = ", ".join(str(name) for name in top_drivers_names if name) or "chưa có dữ liệu thành phần"

    # Product/how-to questions should be answered before trading heuristics so
    # a phrase such as "mô hình của ứng dụng" is not mistaken for a coin setup.
    if any(k in q_lower for k in [
        "tính năng", "tinh nang", "chức năng", "chuc nang", "cách dùng", "cach dung",
        "hướng dẫn", "huong dan", "chi tiết", "chi tiet", "ứng dụng", "ung dung",
        "dự án", "du an", "dao vang", "peakpulse", "tab", "màn hình", "man hinh",
        "radar", "watchlist", "tracking", "backtest", "forward test", "telemetry",
        "audit", "multi-scan", "multiscan", "cài đặt", "cai dat", "setting", "mô hình",
        "mo hinh", "model", "llm", "provider",
    ]):
        return _generate_project_response(symbol, context)

    # 1. Câu hỏi về "Tại sao điểm cao / Tại sao có tín hiệu xả?"
    if any(k in q_lower for k in ["tại sao", "tai sao", "nguyên nhân", "nguyen nhan", "điểm cao", "diem cao", "lý do", "ly do", "why", "score"]):
        return (
            f"### 🔍 Bằng chứng hiện có cho **{symbol}**\n\n"
            f"- Giá trị xác suất/điểm do giao diện cung cấp: **{probability_text}**; mức rủi ro: **{risk_level}**.\n"
            f"- Thành phần đóng góp điểm lớn nhất: `{top_drivers_str}`.\n"
            f"- OI 24h: `{oi_val}`; Funding Rate: `{funding_val}`; Taker ratio: `{taker_val}`.\n"
            f"- Bối cảnh BTC: **{btc_regime}**{'; cờ tăng nóng đang bật' if is_pump else ''}.\n\n"
            "Các thành phần trên là trọng số trong điểm tổng hợp, không phải SHAP và không chứng minh nguyên nhân hay hành vi của một nhóm giao dịch cụ thể. "
            "Nếu một chỉ số đang là N/A, chưa đủ dữ liệu để dùng chỉ số đó làm bằng chứng."
        )

    # 2. Câu hỏi về "Kịch bản nếu BTC tăng / Bối cảnh BTC"
    if any(k in q_lower for k in ["btc", "bitcoin", "thị trường", "thi truong", "kịch bản", "kich ban", "scenario"]):
        invalidation_note = (
            f" Mốc vô hiệu do hệ thống cung cấp hiện là **${sl}**."
            if sl != "—"
            else " Hiện chưa có mốc vô hiệu để lượng hóa rủi ro."
        )
        return (
            f"### 📈 Kịch bản tham chiếu cho **{symbol}** theo BTC\n\n"
            f"Trạng thái Bitcoin hiện tại: **{btc_regime}**.\n\n"
            f"- Nếu BTC mạnh lên, cần quan sát phản ứng thực tế của {symbol}; dữ liệu hiện tại không cung cấp xác suất cho kịch bản này.\n"
            f"- Nếu BTC suy yếu hoặc biến động tăng, theo dõi xem điểm rủi ro và các chỉ số của {symbol} có được xác nhận ở lần quét mới hay không.\n\n"
            f"{invalidation_note} Đây là mốc tham chiếu của hệ thống, không phải dự báo chắc chắn hay lệnh giao dịch."
        )

    # 3. Câu hỏi về "Cắt lỗ ở đâu / Chốt lời / Điểm vào lệnh / SL / TP / Entry"
    if any(k in q_lower for k in ["cắt lỗ", "cat lo", "chốt lời", "chot loi", "vào lệnh", "vao lenh", "sl", "tp", "entry", "stop loss", "take profit"]):
        return (
            f"### 🎯 Các mốc hệ thống đang hiển thị cho **{symbol}**\n\n"
            f"- Giá hiện tại: **${cur_price}**; vùng tham chiếu Entry: **${entry}**.\n"
            f"- Mốc vô hiệu/SL: **${sl}**.\n"
            f"- TP1: **${tp1}**; TP2: **${tp2}**; R:R: **{rr}**.\n\n"
            "Các mốc này được sao chép từ Trade Setup hiện tại. Hãy coi chúng là dữ liệu tham chiếu và kiểm tra độ mới, phí, trượt giá cùng mức chịu lỗ cá nhân trước khi ra quyết định."
        )

    # 4. Câu hỏi về "Đi vốn / Đòn bẩy / Quản lý rủi ro / Leverage / Position Size"
    if any(k in q_lower for k in ["đi vốn", "di von", "đòn bẩy", "don bay", "vốn", "von", "leverage", "rủi ro", "rui ro", "risk", "margin"]):
        distance_note = ""
        if (
            isinstance(entry, (int, float))
            and not isinstance(entry, bool)
            and isinstance(sl, (int, float))
            and not isinstance(sl, bool)
            and float(entry) != 0
        ):
            stop_distance_pct = abs(float(sl) - float(entry)) / abs(float(entry)) * 100
            distance_note = (
                f"\n- Khoảng cách Entry–SL hiện tại: **{stop_distance_pct:.2f}%**. "
                "Công thức tham khảo: notional = mức lỗ tối đa bằng tiền / "
                f"{stop_distance_pct / 100:.6f}, trước khi cộng phí và trượt giá."
            )
        return (
            f"### 🛡️ Dữ liệu cần để tính quy mô vị thế **{symbol}**\n\n"
            f"Trạng thái hiện có: mức rủi ro **{risk_level}**, xác suất/điểm **{probability_text}**, Entry **${entry}**, SL **${sl}**."
            f"{distance_note}\n\n"
            "Chưa thể đề xuất đòn bẩy hoặc tỷ trọng cụ thể nếu thiếu NAV, mức lỗ tối đa chấp nhận được, phí, trượt giá và quy tắc thanh lý của sàn. "
            "Đòn bẩy không làm giảm rủi ro giá; nó chỉ thay đổi ký quỹ và khoảng cách tới thanh lý."
        )

    # 5. Câu hỏi tổng quát mặc định
    return (
        f"### 📊 Tóm tắt dữ liệu **{symbol}**\n\n"
        f"- Xác suất/điểm do giao diện cung cấp: **{probability_text}**; mức rủi ro: **{risk_level}**.\n"
        f"- Giá hiện tại: **${cur_price}**; Entry tham chiếu: **${entry}**.\n"
        f"- Mốc vô hiệu: **${sl}**; TP1: **${tp1}**; TP2: **${tp2}**; R:R: **{rr}**.\n"
        f"- Thành phần điểm lớn nhất: `{top_drivers_str}`; BTC: **{btc_regime}**.\n\n"
        "Đây là bản tóm tắt dữ liệu hiện có, không phải lệnh giao dịch. Thành phần điểm không phải SHAP hoặc bằng chứng nhân quả; cần kiểm tra dữ liệu mới nhất và điều kiện quản trị rủi ro trước khi quyết định."
    )


def ask_ai_analyst(
    question: str,
    symbol: str,
    context: dict[str, Any],
    llm_config: dict[str, Any] | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Process an AI question with real-time coin context and multi-turn chat history."""
    _app_settings = load_runtime_settings()

    cfg = llm_config or {}
    provider = (cfg.get("provider") or "").lower().strip()
    api_key = (cfg.get("apiKey") or cfg.get("api_key") or "").strip()
    model_id = (cfg.get("modelId") or cfg.get("model_id") or "").strip()
    base_url = (cfg.get("baseUrl") or cfg.get("base_url") or "").strip()

    # If client did not specify custom credentials, fall back to server-side default AI
    if not provider and not api_key:
        provider = (_app_settings.ai.provider or "openai").lower().strip()
        api_key = (_app_settings.ai.api_key or "").strip()
        model_id = model_id or (_app_settings.ai.model_id or "antigravity/gemini-3.7-flash-tiered").strip()
        base_url = base_url or (_app_settings.ai.base_url or "https://proxy-ai.comaygiauco.com/v1").strip()
    elif not api_key and provider in ("openai", "proxy", "custom"):
        api_key = (_app_settings.ai.api_key or "").strip()
        if not base_url:
            base_url = (_app_settings.ai.base_url or "https://proxy-ai.comaygiauco.com/v1").strip()
        if not model_id:
            model_id = (_app_settings.ai.model_id or "antigravity/gemini-3.7-flash-tiered").strip()

    enabled = cfg.get("enabled", _app_settings.ai.enabled)

    context_str = build_context_summary(symbol, context)
    app_context_str = build_app_context_summary(context)
    system_prompt = build_system_prompt(symbol, context_str, app_context_str)
    user_prompt = question.strip()

    used_provider = "Built-in Quantitative Engine"
    used_model = "DaoVang-Quant-v2"
    answer = ""

    if enabled and api_key and provider:
        try:
            if provider == "gemini" and not base_url:
                used_provider = "Google Gemini"
                used_model = model_id or "gemini-1.5-flash"
                answer = _call_gemini(api_key, used_model, system_prompt, user_prompt, history=history)
            elif provider in ("openai", "proxy", "custom"):
                if "proxy" in base_url or "proxy" in provider or "tiered" in model_id:
                    used_provider = "Gemini 3.7 Flash Tiered (Proxy)"
                else:
                    used_provider = "OpenAI"
                used_model = model_id or "antigravity/gemini-3.7-flash-tiered"
                answer = _call_openai_compatible(
                    api_key,
                    base_url or "https://proxy-ai.comaygiauco.com/v1",
                    used_model,
                    system_prompt,
                    user_prompt,
                    history=history,
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
                    history=history,
                )
            elif provider == "claude":
                used_provider = "Anthropic Claude"
                used_model = model_id or "claude-3-5-haiku-20241022"
                answer = _call_claude(api_key, used_model, system_prompt, user_prompt, history=history)
            elif provider in ("ollama", "custom"):
                used_provider = "Local Ollama / Custom Proxy"
                used_model = model_id or "llama3.2"
                answer = _call_openai_compatible(
                    api_key,
                    base_url or "http://localhost:11434/v1",
                    used_model,
                    system_prompt,
                    user_prompt,
                    history=history,
                )
        except Exception as exc:
            logger.warning("LLM call failed provider=%s error=%s, falling back to rule-based engine", provider, exc)
            answer = (
                f"> ⚠️ *Không thể kết nối đến {provider.title()} API. "
                "Chi tiết kỹ thuật đã được ghi vào log; đang dùng bộ tóm tắt "
                "định lượng tích hợp:*\n\n"
                + _generate_rule_based_response(question, symbol, context)
            )
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
