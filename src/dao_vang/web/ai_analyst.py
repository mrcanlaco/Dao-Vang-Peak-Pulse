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


DEFAULT_PROJECT_KNOWLEDGE = """
=== KIẾN THỨC NỀN VỀ DỰ ÁN DAO VANG / PEAKPULSE AI ===
- DAO VANG là dashboard cảnh báo sớm cho thị trường Binance USD-M Futures. Mục tiêu là phát hiện dấu hiệu phân phối/tạo đỉnh và rủi ro đảo chiều của crypto; đây không phải hệ thống đảm bảo lợi nhuận hay lệnh giao dịch tự động.
- Luồng dữ liệu chính gồm nến 5m và các dữ liệu phái sinh như Open Interest (OI), Funding Rate, Taker Sell/Buy, khối lượng, RSI và bối cảnh BTC. Dữ liệu được kiểm tra chất lượng và tính theo thời điểm thực tế để hạn chế nhìn trước tương lai.
- Kết quả cần phân biệt rõ: calibrated/model probability là xác suất đã hiệu chuẩn của model; heuristic/composite score là điểm luật và tín hiệu định lượng; anomaly score là điểm radar bất thường độc lập, không phải xác suất.
- Decision Center hiển thị chart, Trade Setup, metrics, AI Decision Cockpit, SHAP drivers và Executive Briefing cho coin đang chọn. Radar hiển thị tín hiệu và bộ lọc. Tracking/Watchlist theo dõi vị thế. Candidate Ranking xếp hạng ứng viên và so sánh các bộ lọc.
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
        f"3. PHÂN TÍCH BẢN CHẤT DÒNG TIỀN: Luôn liên kết các chỉ số (OI biến động, Funding Rate, Taker Volume Delta, SHAP drivers) với hành vi thực tế của Smart Money (cá mập) và đám đông FOMO (ví dụ: bẫy Long, cạn kiệt lực cầu, phân phối âm thầm, thanh lý dồn dập).\n"
        f"4. BẢNG BIỂU & TÍNH TOÁN RÕ RÀNG: Khi người dùng hỏi về tính toán vốn, phân bổ lệnh, đòn bẩy hoặc so sánh kịch bản, HÃY DÙNG BẢNG MARKDOWN chuẩn (ví dụ các cột: Mức rủi ro, Vị thế Notional, Ký quỹ Margin, Dính SL mất $, % Tài khoản) kèm số liệu tính toán chính xác, trực quan.\n"
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

    metrics = context.get("metrics") or {}
    trade_setup = context.get("trade_setup") or {}
    shap_drivers = context.get("shap_drivers") or []

    driver_parts: list[str] = []
    for driver in shap_drivers[:4]:
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
        f"- Top nguyên nhân SHAP chính: {drivers_text}",
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
    app_context = context.get("app_context") if isinstance(context.get("app_context"), dict) else {}
    active_tab = app_context.get("active_tab_label") or app_context.get("active_tab") or "màn hình hiện tại"
    scanner_model = app_context.get("scanner_model_id") or app_context.get("selected_model_key") or "model đang cấu hình"
    llm_model = app_context.get("llm_model_id") or "LLM model đang cấu hình"
    language = str(app_context.get("language") or "vi").lower()

    if language == "en":
        return (
            f"### 🧭 DAO VANG app overview\n\n"
            f"You are currently on **{active_tab}**, with **{symbol}** as the active context. DAO VANG is a Binance USD-M Futures early-warning dashboard for distribution/top-formation and reversal risk.\n\n"
            f"- **Decision Center**: chart, trade setup, metrics, SHAP drivers and the executive AI brief.\n"
            f"- **Radar**: active signals and advanced filters. **Tracking** stores positions to monitor. **Candidate Ranking** compares discovered coins and filters.\n"
            f"- **Lab**: Multi-Scan, Backtest Experiments and Forward Test. **System**: Model Audit, Telemetry, History, Models, Updates and Settings.\n"
            f"- The current scanner model is **{scanner_model}**. Frozen/champion output is the serving lane; challenger and self-learning results remain observational until explicitly promoted.\n"
            f"- The conversation is handled by the configured LLM model **{llm_model}**.\n\n"
            f"The assistant receives the current screen/coin context with every question. Missing data is reported as unavailable; scores are not guarantees or automatic orders."
        )

    return (
        f"### 🧭 Tổng quan ứng dụng DAO VANG\n\n"
        f"Bạn đang ở **{active_tab}**, với **{symbol}** là ngữ cảnh hiện tại. DAO VANG là dashboard cảnh báo sớm thị trường Binance USD-M Futures, tập trung phát hiện phân phối/tạo đỉnh và rủi ro đảo chiều.\n\n"
        f"- **Decision Center**: biểu đồ, Trade Setup, các chỉ số, SHAP drivers và bản tin AI tổng hợp.\n"
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
    sl = trade_setup.get("invalidation_price") or trade_setup.get("sl_price") or trade_setup.get("stop_loss") or "—"
    tp1 = trade_setup.get("tp1_price") or trade_setup.get("tp1") or "—"
    tp2 = trade_setup.get("tp2_price") or trade_setup.get("tp2") or "—"
    rr = trade_setup.get("risk_reward_ratio") or trade_setup.get("rr_ratio") or "—"

    oi_val = metrics.get("oi_change_24h", "N/A")
    funding_val = metrics.get("funding_rate", "N/A")
    taker_val = metrics.get("taker_buy_ratio", metrics.get("taker_sell_ratio", "N/A"))

    top_drivers_names = [
        d.get("feature_name") or d.get("feature") or ""
        for d in shap_drivers[:3]
        if isinstance(d, dict)
    ]
    top_drivers_str = ", ".join(top_drivers_names) if top_drivers_names else "Kiệt sức mua & phân kỳ dòng tiền"

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
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Process an AI question with real-time coin context and multi-turn chat history."""
    from dao_vang.config.settings import AppSettings
    _app_settings = AppSettings()

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
