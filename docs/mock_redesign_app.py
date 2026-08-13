"""
Mock Streamlit app — Đảo Vàng redesign UX.

Chạy thử:
    streamlit run docs/mock_redesign_app.py

Mục đích: minh hoạ luồng user mới (2 mode + tab gộp + lịch sử cảnh báo)
dùng data giả, không phụ thuộc pipeline thật. Dùng để review UX trước khi
áp dụng vào src/dao_vang/web/app.py.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Đảo Vàng — Redesign Mock",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# FAKE DATA — thay bằng pipeline thật khi áp dụng
# ============================================================
SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT"]
RISK_COLORS = {
    "CAO": "#ff4444",
    "TRUNG BÌNH": "#ffaa00",
    "THẤP": "#44aa44",
    "RẤT THẤP": "#2266aa",
}


def _fake_predictions(symbol: str, n: int = 12) -> list[dict]:
    """Sinh n dự đoán giả cho n nến 5m gần nhất."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    base_price = {"BTCUSDT": 65000, "ETHUSDT": 3200, "SOLUSDT": 150}.get(symbol, 1.0)
    rows = []
    for i in range(n):
        ft = now - timedelta(minutes=5 * (n - 1 - i))
        prob = random.betavariate(2, 8)  # đa số thấp, thỉnh thoảng cao
        if prob >= 0.6:
            risk = "CAO"
        elif prob >= 0.4:
            risk = "TRUNG BÌNH"
        elif prob >= 0.2:
            risk = "THẤP"
        else:
            risk = "RẤT THẤP"
        rows.append({
            "feature_time": ft,
            "symbol": symbol,
            "close": base_price * (1 + random.uniform(-0.01, 0.01)),
            "probability": prob,
            "risk_level": risk,
            "invalidation_time": ft + timedelta(hours=24),
        })
    return rows


def _fake_alert_history(symbol: str | None = None, days: int = 7) -> pd.DataFrame:
    """Lịch sử cảnh báo giả — mô phỏng bảng alert_history trong DuckDB."""
    rows = []
    now = datetime.now(timezone.utc)
    for d in range(days):
        day = now - timedelta(days=d)
        for sym in (SYMBOLS if symbol is None else [symbol]):
            n_alerts = random.randint(0, 3)
            for _ in range(n_alerts):
                ft = day - timedelta(hours=random.uniform(0, 24))
                prob = random.betavariate(2, 8)
                risk = "CAO" if prob >= 0.6 else "TRUNG BÌNH" if prob >= 0.4 else "THẤP"
                rows.append({
                    "signal_time": ft,
                    "symbol": sym,
                    "probability": prob,
                    "risk_level": risk,
                    "hit": random.random() < 0.4 if risk in ("CAO", "TRUNG BÌNH") else None,
                    "expired": (now - ft) > timedelta(hours=24),
                })
    return pd.DataFrame(rows).sort_values("signal_time", ascending=False)


def _fake_backtest_summary(symbol: str) -> dict:
    return {
        "precision": random.uniform(0.25, 0.55),
        "recall": random.uniform(0.4, 0.85),
        "brier": random.uniform(0.12, 0.25),
        "baseline_precision": random.uniform(0.05, 0.15),
        "n_folds": 6,
        "leakage": "passed",
        "calibration_error": random.uniform(0.02, 0.09),
        "threshold": random.uniform(0.35, 0.5),
    }


# ============================================================
# SESSION STATE — cache kết quả theo (symbol, mode)
# ============================================================
if "last_run" not in st.session_state:
    st.session_state.last_run = {}  # {symbol: {"predictions": [...], "ts": datetime}}
if "watchlist" not in st.session_state:
    st.session_state.watchlist = ["BTCUSDT", "SOLUSDT"]


# ============================================================
# SIDEBAR — tối giản: mode + coin + 1 nút chính
# ============================================================
with st.sidebar:
    st.markdown("## 🪙 Đảo Vàng")
    st.caption("Phát hiện Distribution — redesign mock")

    mode = st.radio(
        "Mode",
        ["🚨 Cảnh báo", "🔬 Nghiên cứu"],
        horizontal=True,
        help="Cảnh báo: xem tín hiệu nhanh hằng ngày. Nghiên cứu: backtest + so baseline + leakage.",
    )

    st.markdown("---")

    symbol = st.selectbox("Coin", SYMBOLS, index=0)

    # Mode Cảnh báo: ẩn date range, dùng "mới nhất"
    if mode == "🔬 Nghiên cứu":
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input("Từ", value=datetime.now().date() - timedelta(days=60))
        with col_d2:
            end_date = st.date_input("Đến", value=datetime.now().date())
    else:
        st.caption("📅 Tự động lấy 30 ngày gần nhất")

    with st.expander("⚙️ Nâng cao", expanded=False):
        threshold_mult = st.slider("Hệ số ngưỡng risk", 0.5, 2.0, 1.0, 0.1,
                                   help="CAO = 1.5×, TB = 1×, THẤP = 0.5× ngưỡng. Kéo để tuỳ chỉnh.")
        seed = st.number_input("Seed", value=42, step=1)

    # Watchlist quick view
    st.markdown("---")
    st.markdown(f"**📋 Watchlist** ({len(st.session_state.watchlist)})")
    if st.session_state.watchlist:
        for s in st.session_state.watchlist:
            _c1, _c2 = st.columns([4, 1])
            _c1.caption(f"• {s}")
            if _c2.button("✕", key=f"rm_{s}", help=f"Bỏ {s}"):
                st.session_state.watchlist.remove(s)
                st.rerun()
    if symbol not in st.session_state.watchlist:
        if st.button("➕ Thêm vào watchlist", use_container_width=True):
            st.session_state.watchlist.append(symbol)
            st.rerun()

    st.markdown("---")
    # Nút chính đổi theo mode
    if mode == "🚨 Cảnh báo":
        run_btn = st.button("🔄 Cập nhật & Phát hiện", type="primary", use_container_width=True,
                            help="Chỉ tải data mới + predict. Bỏ qua nếu data đã cập nhật.")
    else:
        run_btn = st.button("🚀 Chạy Backtest", type="primary", use_container_width=True,
                            help="Train + walk-forward + so baseline + leakage.")


# ============================================================
# TABS — gộp: 2 tab chính + 1 reference
# ============================================================
tab_alert, tab_research, tab_ref = st.tabs([
    "🚨 Cảnh báo",
    "🔬 Nghiên cứu",
    "📖 Tham khảo",
])


# ============================================================
# TAB 1: CẢNH BÁO — kết hợp phát hiện + lịch sử + watchlist
# ============================================================
with tab_alert:
    # --- Phần 1: Tín hiệu hiện tại cho coin đang chọn ---
    st.markdown(f"### 🎯 Tín hiệu hiện tại — {symbol}")

    if run_btn and mode == "🚨 Cảnh báo":
        with st.spinner("Cập nhật data mới + predict..."):
            # Mock: layer 3 chỉ — giả vờ data đã cache
            import time as _t
            _t.sleep(0.6)
        preds = _fake_predictions(symbol)
        st.session_state.last_run[symbol] = {"predictions": preds, "ts": datetime.now(timezone.utc)}
        st.toast("✅ Đã cập nhật", icon="🪙")

    cached = st.session_state.last_run.get(symbol)
    if not cached:
        st.info("Bấm **🔄 Cập nhật & Phát hiện** ở sidebar để xem tín hiệu.")
        preds = []
    else:
        preds = cached["predictions"]
        age = (datetime.now(timezone.utc) - cached["ts"]).total_seconds() / 60
        st.caption(f"Cập nhật lần cuối: {age:.0f} phút trước — bấm 🔄 để làm mới")

    if preds:
        high = [p for p in preds if p["risk_level"] == "CAO"]
        med = [p for p in preds if p["risk_level"] == "TRUNG BÌNH"]
        max_prob = max(p["probability"] for p in preds)

        # Alert banner nổi bật
        if high:
            st.error(f"🚨 **{len(high)} nến nguy cơ CAO** — {symbol} có thể xả trong 24h!")
        elif med:
            st.warning(f"⚠️ {len(med)} nến nguy cơ TRUNG BÌNH — theo dõi sát {symbol}.")
        else:
            st.success(f"✅ {symbol} bình thường — không có tín hiệu nguy cơ.")

        # 4 metric gọn (bớt 1 so với cũ)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Xác suất xả cao nhất", f"{max_prob:.1%}")
        c2.metric("🚨 CAO", len(high))
        c3.metric("⚠️ TB", len(med))
        c4.metric("Hết hạn sau", "~24h")

        # Bảng + chart cạnh nhau
        col_t, col_c = st.columns([3, 2])
        with col_t:
            st.markdown("#### Dự đoán 12 nến mới nhất")
            pdf = pd.DataFrame(preds)
            pdf["probability"] = pdf["probability"].apply(lambda x: f"{x:.1%}")
            pdf["close"] = pdf["close"].apply(lambda x: f"{x:,.2f}")
            pdf["feature_time"] = pdf["feature_time"].dt.strftime("%H:%M UTC")
            pdf["invalidation_time"] = pdf["invalidation_time"].dt.strftime("%H:%M UTC")
            pdf = pdf[["feature_time", "close", "probability", "risk_level", "invalidation_time"]]
            pdf.columns = ["Thời gian", "Giá đóng", "Xác suất", "Nguy cơ", "Hết hạn"]

            def _risk_style(val):
                c = RISK_COLORS.get(val, "")
                return f"background-color: {c}; color: white" if c else ""

            st.dataframe(pdf.style.map(_risk_style, subset=["Nguy cơ"]),
                         use_container_width=True, hide_index=True)

        with col_c:
            st.markdown("#### Xác suất theo thời gian")
            cdf = pd.DataFrame(preds)
            cdf["feature_time"] = pd.to_datetime(cdf["feature_time"])
            st.line_chart(cdf.set_index("feature_time")[["probability"]])

    # --- Phần 2: Lịch sử cảnh báo (MỚI — không có ở app cũ) ---
    st.markdown("---")
    st.markdown("### 📜 Lịch sử tín hiệu")

    hist_filter_col, hist_sym_col, _ = st.columns([2, 2, 3])
    with hist_filter_col:
        hist_days = st.selectbox("Khoảng thời gian", [1, 3, 7, 30], index=2, key="hist_days")
    with hist_sym_col:
        hist_sym = st.selectbox("Coin", ["Tất cả"] + SYMBOLS, index=0, key="hist_sym")

    hist = _fake_alert_history(
        symbol=None if hist_sym == "Tất cả" else hist_sym,
        days=hist_days,
    )
    if hist.empty:
        st.caption("Chưa có tín hiệu nào trong khoảng này.")
    else:
        # Tóm tắt theo risk
        sum_c1, sum_c2, sum_c3, sum_c4 = st.columns(4)
        sum_c1.metric("Tổng tín hiệu", len(hist))
        sum_c2.metric("🚨 CAO", len(hist[hist.risk_level == "CAO"]))
        sum_c3.metric("⚠️ TB", len(hist[hist.risk_level == "TRUNG BÌNH"]))
        hit_rate = hist[hist.hit.notna()]
        sum_c4.metric("Tỷ lệ trúng (CAO+TB)",
                      f"{hit_rate.hit.mean():.0%}" if not hit_rate.empty else "N/A")

        hist["probability"] = hist["probability"].apply(lambda x: f"{x:.1%}")
        hist["signal_time"] = hist["signal_time"].dt.strftime("%Y-%m-%d %H:%M")
        hist["hit"] = hist["hit"].map({True: "✅ Trúng", False: "❌ Trượt", None: "⏳ Chờ"})
        hist["expired"] = hist["expired"].map({True: "⌛ Hết hạn", False: "🟢 Còn hạn"})
        hist = hist.rename(columns={
            "signal_time": "Thời gian", "symbol": "Coin",
            "probability": "Xác suất", "risk_level": "Nguy cơ",
            "hit": "Kết quả", "expired": "Trạng thái",
        })
        st.dataframe(
            hist.style.map(_risk_style, subset=["Nguy cơ"]),
            use_container_width=True, hide_index=True,
        )

    # --- Phần 3: Watchlist cảnh báo ---
    st.markdown("---")
    st.markdown(f"### 📋 Watchlist ({len(st.session_state.watchlist)} coin)")
    st.caption("App tự quét các coin này hằng ngày (cron) và lưu tín hiệu vào lịch sử.")
    if st.session_state.watchlist:
        wl_rows = []
        for s in st.session_state.watchlist:
            cached_s = st.session_state.last_run.get(s)
            if cached_s:
                preds_s = cached_s["predictions"]
                high_s = sum(1 for p in preds_s if p["risk_level"] == "CAO")
                max_s = max(p["probability"] for p in preds_s)
                wl_rows.append({"Coin": s, "Xác suất cao nhất": f"{max_s:.1%}",
                                "🚨 CAO": high_s, "Cập nhật": "✅"})
            else:
                wl_rows.append({"Coin": s, "Xác suất cao nhất": "—",
                                "🚨 CAO": "—", "Cập nhật": "⬜ Chưa quét"})
        st.dataframe(pd.DataFrame(wl_rows), use_container_width=True, hide_index=True)
        if st.button("🔄 Quét tất cả watchlist", type="secondary"):
            with st.spinner("Quét watchlist..."):
                import time as _t
                for s in st.session_state.watchlist:
                    _t.sleep(0.3)
                    st.session_state.last_run[s] = {
                        "predictions": _fake_predictions(s),
                        "ts": datetime.now(timezone.utc),
                    }
            st.toast(f"✅ Đã quét {len(st.session_state.watchlist)} coin", icon="🪙")
            st.rerun()


# ============================================================
# TAB 2: NGHIÊN CỨU — backtest + baseline + leakage + compare
# ============================================================
with tab_research:
    st.markdown(f"### 🔬 Đánh giá model — {symbol}")

    if run_btn and mode == "🔬 Nghiên cứu":
        with st.spinner("Train + walk-forward + leakage check..."):
            import time as _t
            _t.sleep(1.2)
        st.session_state.last_bt = {"symbol": symbol, "summary": _fake_backtest_summary(symbol),
                                     "ts": datetime.now(timezone.utc)}
        st.toast("✅ Backtest xong", icon="🧪")

    bt = st.session_state.get("last_bt")
    if not bt or bt["symbol"] != symbol:
        st.info("Bấm **🚀 Chạy Backtest** ở sidebar (mode Nghiên cứu) để đánh giá.")
    else:
        s = bt["summary"]
        # Verdict nổi bật: model có vượt baseline không?
        verdict_c1, verdict_c2 = st.columns([2, 3])
        with verdict_c1:
            if s["precision"] > s["baseline_precision"] * 1.5:
                st.success(f"✅ Model vượt baseline rõ ràng\n\n"
                           f"Precision {s['precision']:.1%} vs baseline {s['baseline_precision']:.1%}")
            elif s["precision"] > s["baseline_precision"]:
                st.warning(f"⚠️ Model nhỉnh hơn baseline\n\n"
                           f"Precision {s['precision']:.1%} vs baseline {s['baseline_precision']:.1%}")
            else:
                st.error(f"❌ Model không vượt baseline\n\n"
                         f"Precision {s['precision']:.1%} vs baseline {s['baseline_precision']:.1%} — sửa giả thuyết.")
        with verdict_c2:
            st.caption("Quy tắc: model không vượt baseline → không triển khai. "
                       "Xem tab Cảnh báo để biết tín hiệu hiện tại.")

        # Metrics chi tiết
        st.markdown("#### Metrics")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Precision", f"{s['precision']:.1%}")
        m2.metric("Recall", f"{s['recall']:.1%}")
        m3.metric("Brier Score", f"{s['brier']:.3f}", help="Thấp hơn = tốt hơn")
        m4.metric("Walk-forward folds", s["n_folds"])
        m5.metric("Threshold", f"{s['threshold']:.2f}")

        # Chất lượng
        st.markdown("#### Kiểm tra chất lượng")
        q1, q2 = st.columns(2)
        with q1:
            leak_color = "🟢" if s["leakage"] == "passed" else "🔴"
            st.metric("Leakage check", f"{leak_color} {s['leakage']}",
                      help="Phải PASS. Fail = feature dùng thông tin tương lai.")
        with q2:
            cal_help = "Sai số calibration — thấp hơn = xác suất báo khớp thực tế."
            st.metric("Calibration error", f"{s['calibration_error']:.3f}", help=cal_help)

        # So sánh baseline dạng bảng
        st.markdown("#### So sánh với baseline")
        cmp_df = pd.DataFrame([
            {"Phương pháp": "LogReg (model)", "Precision": f"{s['precision']:.1%}",
             "Recall": f"{s['recall']:.1%}", "Brier": f"{s['brier']:.3f}"},
            {"Phương pháp": "Prevalence baseline", "Precision": f"{s['baseline_precision']:.1%}",
             "Recall": "100%", "Brier": "—"},
        ])
        st.dataframe(cmp_df, use_container_width=True, hide_index=True)

        # Export
        st.markdown("---")
        e1, e2 = st.columns(2)
        with e1:
            st.download_button("📥 Tải báo cáo Markdown",
                               data=f"# Backtest {symbol}\n\nPrecision: {s['precision']:.1%}\n",
                               file_name=f"backtest_{symbol}.md",
                               mime="text/markdown")
        with e2:
            if st.button("🧊 Freeze model cho forward test", help="Đóng băng model để test trên data mới sinh sau này."):
                st.toast(f"✅ Đã freeze model {symbol}", icon="🧊")


# ============================================================
# TAB 3: THAM KHẢO — thuật ngữ + hướng dẫn (gộp)
# ============================================================
with tab_ref:
    sub = st.radio("Xem", ["📖 Thuật ngữ", "🧭 Hướng dẫn"], horizontal=True, key="ref_sub")

    if sub == "📖 Thuật ngữ":
        st.markdown("#### Từ điển thuật ngữ")
        GLOSSARY = {
            "Distribution": "Coin bắt đầu xả — mất động lượng tăng, sắp giảm mạnh.",
            "Precision": "Trong 100 lần AI báo sắp xả, bao nhiêu lần đúng.",
            "Recall": "Trong 100 lần coin THẬT SỰ xả, AI bắt được bao nhiêu.",
            "Brier Score": "Độ chuẩn xác — AI báo 70% thì thật ~70%. Thấp hơn = tốt.",
            "Threshold": "Ngưỡng cảnh báo — AI báo xác suất bao nhiêu thì phát cảnh báo.",
            "Baseline": "Mốc so sánh đơn giản — model phải giỏi hơn mới đáng dùng.",
            "Walk-Forward": "Train trên quá khứ, test trên tương lai — không trộn lẫn.",
            "Leakage": "AI vô tình dùng thông tin tương lai — phải FAIL nếu phát hiện.",
            "Label": "Kết quả thật — coin có thật sự xả trong 24h sau đó không.",
            "Horizon": "Khung dự báo — 24 giờ tới.",
            "MAE": "Biên tăng tối đa trước khi giảm 8% — quá 4% = false alarm.",
            "Forward Test": "Đóng băng AI → chờ data mới → chấm điểm ngoài phòng lab.",
        }
        search = st.text_input("🔍 Tìm", placeholder="VD: precision, MAE...", key="gloss_s")
        items = list(GLOSSARY.items())
        if search:
            sl = search.lower()
            items = [(k, v) for k, v in items if sl in k.lower() or sl in v.lower()]
        for term, expl in items:
            with st.expander(f"**{term}**"):
                st.markdown(expl)

    else:
        st.markdown("#### Hướng dẫn nhanh")
        st.markdown("""
**2 mode ở sidebar:**

| Mode | Khi nào dùng | Nút chính |
|------|--------------|-----------|
| 🚨 Cảnh báo | Mỗi ngày xem coin có sắp xả không | 🔄 Cập nhật & Phát hiện |
| 🔬 Nghiên cứu | Đánh giá model, so baseline, leakage | 🚀 Chạy Backtest |

**Vòng lặp hằng ngày:**
1. Sidebar → chọn coin → bấm 🔄 Cập nhật & Phát hiện.
2. Đọc alert banner + bảng 12 nến + chart xác suất.
3. Cuộn xuống 📜 Lịch sử tín hiệu để xem tín hiệu đã phát trước đó.
4. Watchlist → bấm 🔄 Quét tất cả để check nhiều coin cùng lúc.

**Vòng lặp nghiên cứu (tuần):**
1. Chuyển mode → 🔬 Nghiên cứu.
2. Chọn coin + date range → bấm 🚀 Chạy Backtest.
3. Đọc verdict (vượt baseline không?) + metrics + leakage + calibration.
4. Tải báo cáo / freeze model cho forward test.
""")
