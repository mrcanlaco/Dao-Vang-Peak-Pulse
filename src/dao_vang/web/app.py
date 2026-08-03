import streamlit as st
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pandas as pd

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.collectors.funding import FundingCollector
from dao_vang.data.collectors.open_interest import OpenInterestCollector
from dao_vang.data.collectors.ratios import GlobalRatioCollector, TopRatioCollector
from dao_vang.data.collectors.taker import TakerRatioCollector
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.experiments.artifacts import ArtifactRegistry
from dao_vang.experiments.runner import ExperimentConfig, run_experiment
from dao_vang.features.builder import build_features
from dao_vang.labels.engine import DistributionLabelEngine
from dao_vang.reports.generator import generate_markdown_report
from dao_vang.data.pipeline import (
    process_raw_to_parquet,
    build_raw_timeline,
    get_incremental_start,
    scan_downloaded_data,
)

st.set_page_config(
    page_title="Đảo Vàng",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# GLOSSARY — giải nghĩa thuật ngữ (từ GLOSSARY.md)
# ============================================================
GLOSSARY = {
    "Distribution": "Trạng thái chuyển tiếp: tài sản mất động lượng tăng, xác suất cao xuất hiện nhịp giảm đạt điều kiện Label Spec. Không phải nhận định bằng mắt — chỉ có ý nghĩa khi gắn với label version.",
    "Phân phối": "Distribution — trạng thái coin bắt đầu xả. Label=1 nghĩa là trong 24h tới, giá giảm ≥8% (target drawdown) và MAE ≤4%.",
    "Precision": "Trong số tín hiệu dương đã phát, tỷ lệ đạt label dương. Precision cao = ít báo sai (false positive thấp).",
    "Recall": "Trong số label dương thực tế, tỷ lệ được hệ thống phát hiện. Recall cao = ít bỏ sót (false negative thấp).",
    "Brier Score": "Mức độ phù hợp giữa xác suất dự báo và kết quả thực tế. Brier thấp = calibration tốt (dự báo 70% thì thực sự ~70%).",
    "Threshold": "Ngưỡng probability để quyết định tín hiệu dương/âm. Threshold thấp = phát hiện nhiều nhưng sai nhiều; cao = chính xác nhưng bỏ sót.",
    "Baseline": "Phương pháp đơn giản dùng làm mốc so sánh. Model phức tạp không vượt baseline thì không được triển khai.",
    "Walk-Forward": "Quy trình train/validate/test theo thời gian, cửa sổ tiến về phía sau. Không shuffle — đảm bảo không dùng dữ liệu tương lai.",
    "Leakage": "Data leakage — feature/evaluation sử dụng thông tin không hợp pháp tại thời điểm dự báo (dữ liệu tương lai). Phải fail.",
    "Label": "Kết quả mục tiêu tạo bằng thuật toán từ dữ liệu tương lai. Chỉ dùng cho training/evaluation, KHÔNG dùng làm feature.",
    "Feature Time": "Timestamp mà feature vector đại diện. MVP dùng close time của nến 5 phút đã đóng.",
    "Signal Price": "Giá tham chiếu tại thời điểm tín hiệu. MVP v0.1 dùng close của nến futures 5 phút đã đóng.",
    "Horizon": "Khoảng thời gian tương lai dùng để xác định outcome. MVP: 24 giờ.",
    "Target Drawdown": "Mức giảm tối thiểu từ signal price cần đạt trong horizon để label dương. MVP: 8%.",
    "MAE": "Max Adverse Excursion — mức tăng bất lợi lớn nhất so với signal price trước khi target đạt. MVP: ≤4%.",
    "Probability": "Xác suất model dự đoán coin sẽ phân phối trong 24h tới. >Threshold = tín hiệu dương.",
    "Risk Level": "Phân loại nguy cơ dựa trên probability vs threshold: CAO (≥1.5×threshold), TRUNG BÌNH (≥threshold), THẤP (≥0.5×threshold), RẤT THẤP (<0.5×threshold).",
    "Prevalence": "Tỷ lệ label dương trong dataset. Prevalence thấp = dataset mất cân bằng, model khó học.",
    "Embargo": "Khoảng thời gian (12h) giữa train và test để tránh lookahead bias từ horizon overlap.",
    "Open Interest (OI)": "Tổng số hợp đồng futures đang mở. OI tăng + giá giảm = phe short vào mạnh.",
    "Funding Rate": "Lãi suất định kỳ (8h) mà long trả short (hoặc ngược lại). Funding âm = short trả long = thị trường oversold.",
    "Taker Buy/Sell Ratio": "Tỷ lệ volume mua/bán chủ động của taker. >1 = mua mạnh, <1 = bán mạnh.",
    "Long/Short Ratio": "Tỷ lệ tài khoản long/short. L/S cao = nhiều long = nguy cơ squeeze ngược.",
    "Calibration": "Mức độ phù hợp giữa xác suất dự báo và tần suất thực tế. Nhóm 70% phải xảy ra ~70%.",
    "Forward Test": "Đánh giá trên dữ liệu phát sinh SAU khi phương pháp đã đóng băng — kiểm tra stability thực tế.",
    "Point-in-Time": "Mọi dữ liệu dùng tại thời điểm T thực sự có thể biết tại hoặc trước T. Vi phạm = leakage.",
    "Artifact": "Bản ghi bất biến của một experiment: config, metrics, predictions, report. Có version và hash.",
    "Feature Importance": "Hệ số (coefficient) cho biết feature nào ảnh hưởng nhiều nhất đến dự đoán. Dương = tăng xác suất phân phối, âm = giảm.",
}


def _glossary_tooltip(term: str) -> str:
    """Return glossary explanation for a term, or empty string if not found."""
    return GLOSSARY.get(term, "")


def _render_glossary_tab():
    """Render a glossary tab with searchable term explanations."""
    st.markdown("#### 📖 Từ điển thuật ngữ")
    st.caption("Nguồn: GLOSSARY.md — bấm vào từng mục để xem giải thích đầy đủ")

    search = st.text_input("🔍 Tìm thuật ngữ", placeholder="VD: precision, distribution, MAE...", key="glossary_search")

    items = list(GLOSSARY.items())
    if search:
        search_lower = search.lower()
        items = [(k, v) for k, v in items if search_lower in k.lower() or search_lower in v.lower()]

    for term, explanation in items:
        with st.expander(f"**{term}**", expanded=False):
            st.markdown(explanation)

# --- CSS for compact UI + ticker marquee ---
st.markdown("""
<style>
    .stMetric { padding: 4px 0 !important; }
    .stMetric > div > div { gap: 2px !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { padding: 6px 12px; font-size: 14px; }
    .stAlert { padding: 8px 12px !important; }
    div[data-testid="stSidebar"] { width: 320px !important; }
    div[data-testid="stSidebar"] > div { padding-top: 1rem; }

    /* Ticker marquee */
    .dv-ticker {
        overflow: hidden;
        white-space: nowrap;
        background: #1a1a2e;
        border-radius: 8px;
        padding: 8px 0;
        margin-bottom: 12px;
    }
    .dv-ticker-track {
        display: inline-block;
        animation: dv-scroll 60s linear infinite;
    }
    .dv-ticker-item {
        display: inline-block;
        padding: 0 16px;
        font-size: 14px;
        font-family: monospace;
    }
    .dv-ticker-up { color: #0ecb81; }
    .dv-ticker-down { color: #f6465d; }
    .dv-ticker-symbol { font-weight: bold; }
    @keyframes dv-scroll {
        0% { transform: translateX(0); }
        100% { transform: translateX(-50%); }
    }
    .dv-ticker:hover .dv-ticker-track { animation-play-state: paused; }

    /* Coin buttons in top gainers grid */
    .stButton > button[kind="secondary"] {
        font-size: 13px;
        padding: 6px 4px;
        text-align: center;
        white-space: pre-line;
        line-height: 1.3;
    }
</style>
""", unsafe_allow_html=True)


# ============================================================
# TOP GAINERS — 24h ticker (like dex screener)
# ============================================================
import json as _json

_WATCHLIST_FILE = Path("data/watchlist.json")


def _fetch_24h_tickers() -> list[dict]:
    """Fetch 24h ticker stats for all USDT futures from Binance."""
    try:
        client = BinanceClient()
        data = client.get("fapi/v1/ticker/24hr")
        # Filter USDT pairs, sort by priceChangePercent desc
        usdt_pairs = [
            d for d in data
            if d.get("symbol", "").endswith("USDT")
            and float(d.get("quoteVolume", 0)) > 1_000_000  # min volume filter
        ]
        usdt_pairs.sort(key=lambda x: float(x.get("priceChangePercent", 0)), reverse=True)
        return usdt_pairs
    except Exception:
        return []


def _fetch_recent_klines(symbol: str, interval: str = "1h", limit: int = 48) -> list[dict]:
    """Fetch recent klines for mini chart display."""
    try:
        client = BinanceClient()
        data = client.get("fapi/v1/klines", {
            "symbol": symbol,
            "interval": interval,
            "limit": limit,
        })
        # Each kline: [openTime, open, high, low, close, volume, closeTime, ...]
        return [
            {
                "time": datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc),
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
            }
            for k in data
        ]
    except Exception:
        return []


def _load_watchlist() -> list[str]:
    """Load watchlist from persistent file."""
    if _WATCHLIST_FILE.exists():
        try:
            return _json.loads(_WATCHLIST_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_watchlist(symbols: list[str]):
    """Save watchlist to persistent file."""
    _WATCHLIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    _WATCHLIST_FILE.write_text(_json.dumps(symbols, indent=2), encoding="utf-8")


def _render_ticker_marquee(tickers: list[dict], top_n: int = 20):
    """Render scrolling ticker marquee with top gainers/losers."""
    if not tickers:
        return

    items = tickers[:top_n] + tickers[-5:]  # top gainers + top losers
    # Build HTML items (duplicate for seamless loop)
    html_items = []
    for d in items:
        sym = d["symbol"]
        pct = float(d.get("priceChangePercent", 0))
        price = float(d.get("lastPrice", 0))
        cls = "dv-ticker-up" if pct >= 0 else "dv-ticker-down"
        arrow = "▲" if pct >= 0 else "▼"
        # Format price nicely
        if price > 1000:
            price_str = f"${price:,.0f}"
        elif price > 1:
            price_str = f"${price:.2f}"
        else:
            price_str = f"${price:.6f}"
        html_items.append(
            f'<span class="dv-ticker-item {cls}">'
            f'<span class="dv-ticker-symbol">{sym}</span> '
            f'{price_str} {arrow}{abs(pct):.2f}%</span>'
        )

    items_html = "".join(html_items)
    # Duplicate for seamless scroll
    st.markdown(f"""
    <div class="dv-ticker">
        <div class="dv-ticker-track">{items_html}{items_html}</div>
    </div>
    """, unsafe_allow_html=True)


# --- Session state for watchlist ---
if "watchlist" not in st.session_state:
    st.session_state.watchlist = _load_watchlist()
if "selected_gainer" not in st.session_state:
    st.session_state.selected_gainer = None


# --- Render ticker + top gainers panel ---
st.title("🪙 Đảo Vàng")
st.caption("Phát hiện coin sắp xả phân phối")

_col_ticker, _col_refresh = st.columns([6, 1])
with _col_ticker:
    _tickers = _fetch_24h_tickers()
    _render_ticker_marquee(_tickers, top_n=20)
with _col_refresh:
    if st.button("🔄", help="Làm mới ticker"):
        st.rerun()

# --- Top gainers panel (clickable buttons) ---
if _tickers:
    with st.expander("🔥 Top tăng/giảm 24h — bấm vào coin để xem chart", expanded=True):
        _top_gainers = _tickers[:15]
        _top_losers = sorted(_tickers, key=lambda x: float(x.get("priceChangePercent", 0)))[:5]

        # --- Top gainers as clickable buttons ---
        st.markdown("**🟢 Top 15 tăng mạnh nhất — bấm để xem**")
        _gainer_grid = st.columns(5)
        for i, d in enumerate(_top_gainers):
            sym = d["symbol"]
            pct = float(d["priceChangePercent"])
            price = float(d["lastPrice"])
            col = _gainer_grid[i % 5]
            label = f"{sym}\n{pct:+.2f}%"
            if col.button(label, key=f"gainer_{sym}", use_container_width=True, help=f"Giá: {price:.6f} | Volume: {float(d['quoteVolume']):,.0f}"):
                st.session_state.selected_gainer = sym

        # --- Top losers ---
        st.markdown("**🔴 Top 5 giảm mạnh nhất — bấm để xem**")
        _loser_grid = st.columns(5)
        for i, d in enumerate(_top_losers):
            sym = d["symbol"]
            pct = float(d["priceChangePercent"])
            price = float(d["lastPrice"])
            col = _loser_grid[i % 5]
            label = f"{sym}\n{pct:+.2f}%"
            if col.button(label, key=f"loser_{sym}", use_container_width=True, help=f"Giá: {price:.6f} | Volume: {float(d['quoteVolume']):,.0f}"):
                st.session_state.selected_gainer = sym

        # --- Also allow manual search ---
        st.markdown("---")
        _search_col, _scan_col = st.columns([3, 1])
        with _search_col:
            _all_ticker_symbols = [d["symbol"] for d in _tickers[:50]]
            _detail_symbol = st.selectbox(
                "Hoặc chọn coin từ danh sách",
                options=_all_ticker_symbols,
                index=0 if not st.session_state.selected_gainer else _all_ticker_symbols.index(st.session_state.selected_gainer) if st.session_state.selected_gainer in _all_ticker_symbols else 0,
                key="detail_gainer_select",
            )
        with _scan_col:
            st.write("")  # spacer
            st.write("")  # spacer
            if st.button("🔍 Xem chart", key="view_chart_btn", use_container_width=True):
                st.session_state.selected_gainer = _detail_symbol

        # Use selected_gainer if set, otherwise use selectbox
        _show_symbol = st.session_state.selected_gainer or _detail_symbol

        if _show_symbol:
            _klines = _fetch_recent_klines(_show_symbol, "1h", 48)
            if _klines:
                _kdf = pd.DataFrame(_klines)
                _ticker_info = next((d for d in _tickers if d["symbol"] == _show_symbol), {})

                st.markdown("---")
                st.markdown(f"### 📊 {_show_symbol}")

                dc1, dc2, dc3, dc4 = st.columns(4)
                dc1.metric("Giá hiện tại", f"{float(_ticker_info.get('lastPrice', 0)):.6f}")
                dc2.metric("Thay đổi 24h", f"{float(_ticker_info.get('priceChangePercent', 0)):+.2f}%")
                dc3.metric("Volume 24h", f"{float(_ticker_info.get('quoteVolume', 0)):,.0f}")
                dc4.metric("High/Low 24h", f"{float(_ticker_info.get('highPrice', 0)):.6f} / {float(_ticker_info.get('lowPrice', 0)):.6f}")

                # --- Chart type selector ---
                _chart_type_col, _tf_col, _tv_col = st.columns([2, 2, 2])
                with _chart_type_col:
                    _chart_type = st.radio(
                        "Loại chart",
                        ["🕯️ Nến (Candlestick)", "📈 Đường (Line)", "📊 TradingView"],
                        horizontal=True,
                        key="chart_type_radio",
                    )
                with _tf_col:
                    _tf = st.selectbox(
                        "Khung thời gian",
                        ["15m", "1h", "4h", "1d"],
                        index=1,
                        key="chart_tf_select",
                    )
                with _tv_col:
                    _n_candles = st.selectbox(
                        "Số nến",
                        [48, 96, 200, 500],
                        index=0,
                        key="chart_n_select",
                    )

                # Re-fetch with selected timeframe if not 1h/48
                if _tf != "1h" or _n_candles != 48:
                    _klines = _fetch_recent_klines(_show_symbol, _tf, _n_candles)
                    _kdf = pd.DataFrame(_klines) if _klines else _kdf

                if _chart_type == "🕯️ Nến (Candlestick)":
                    import plotly.graph_objects as go
                    _fig = go.Figure(data=[go.Candlestick(
                        x=_kdf["time"],
                        open=_kdf["open"],
                        high=_kdf["high"],
                        low=_kdf["low"],
                        close=_kdf["close"],
                        name=_show_symbol,
                    )])
                    _fig.update_layout(
                        template="plotly_dark",
                        height=400,
                        margin=dict(l=0, r=0, t=30, b=0),
                        xaxis_rangeslider_visible=False,
                        yaxis_title="Giá",
                    )
                    _fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(50,50,50,0.3)')
                    st.plotly_chart(_fig, use_container_width=True, config={"displayModeBar": False})

                elif _chart_type == "📈 Đường (Line)":
                    _chart_data = _kdf.set_index("time")[["close"]]
                    st.line_chart(_chart_data, use_container_width=True)

                elif _chart_type == "📊 TradingView":
                    # Embed TradingView widget
                    # Use spot symbol (BINANCE:BTCUSDT) — more universally available than .P
                    # User can switch to perpetual within the widget via allow_symbol_change
                    import streamlit.components.v1 as components
                    _tv_html = f"""
                    <div class="tradingview-widget-container" style="height:500px;">
                        <div id="tradingview_chart"></div>
                        <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
                        <script type="text/javascript">
                        new TradingView.widget({{
                            "autosize": true,
                            "symbol": "BINANCE:{_show_symbol}",
                            "interval": "{_tf}",
                            "timezone": "Etc/UTC",
                            "theme": "dark",
                            "style": "1",
                            "locale": "vi_VN",
                            "toolbar_bg": "#1a1a2e",
                            "enable_publishing": false,
                            "allow_symbol_change": true,
                            "hide_side_toolbar": false,
                            "details": true,
                            "hotlist": true,
                            "calendar": false,
                            "studies": ["STD;SMA", "STD;RSI", "STD;MACD"],
                            "container_id": "tradingview_chart"
                        }});
                        </script>
                    </div>
                    """
                    components.html(_tv_html, height=520)

                # Add to watchlist + scan + external links
                st.markdown("---")
                _wl_cols = st.columns([2, 1, 1, 1])
                with _wl_cols[0]:
                    if _show_symbol in st.session_state.watchlist:
                        st.success(f"✅ {_show_symbol} đã có trong watchlist")
                    else:
                        if st.button(f"➕ Thêm {_show_symbol} vào watchlist", key="add_wl"):
                            st.session_state.watchlist.append(_show_symbol)
                            _save_watchlist(st.session_state.watchlist)
                            st.success(f"✅ Đã thêm {_show_symbol} vào watchlist!")
                            st.rerun()
                with _wl_cols[1]:
                    if st.button("🔄 Làm mới chart"):
                        st.rerun()
                with _wl_cols[2]:
                    if st.button("🚀 Quét coin này", key="scan_gainer"):
                        st.session_state.scan_symbol = _show_symbol
                        st.rerun()
                with _wl_cols[3]:
                    _binance_url = f"https://www.binance.com/en/futures/{_show_symbol}"
                    st.link_button("📈 Binance", _binance_url, use_container_width=True)


# --- Watchlist panel (persistent) ---
if st.session_state.watchlist:
    st.markdown("---")
    st.markdown(f"#### 📋 Watchlist thủ công ({len(st.session_state.watchlist)} coin)")
    _wl_df = pd.DataFrame([
        {"Coin": s, "Trạng thái": "Đã lưu"}
        for s in st.session_state.watchlist
    ])
    st.dataframe(_wl_df, use_container_width=True, hide_index=True)

    _wl_action = st.columns([1, 1, 1])
    with _wl_action[0]:
        if st.button("🗑️ Xóa watchlist"):
            st.session_state.watchlist = []
            _save_watchlist([])
            st.rerun()
    with _wl_action[1]:
        _remove_sym = st.selectbox(
            "Chọn coin để xóa",
            options=st.session_state.watchlist,
            key="remove_wl_select",
        )
    with _wl_action[2]:
        if st.button("➖ Xóa coin", key="remove_wl_btn"):
            if _remove_sym in st.session_state.watchlist:
                st.session_state.watchlist.remove(_remove_sym)
                _save_watchlist(st.session_state.watchlist)
                st.rerun()

# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.markdown("## 🪙 Đảo Vàng")
    st.caption("Phát hiện coin sắp xả phân phối")

    # --- Mode selection ---
    mode = st.radio(
        "Chế độ",
        ["🔍 Watchlist", "🧪 Backtest"],
        help="Watchlist: quét tín hiệu hiện tại | Backtest: đánh giá model trên lịch sử",
    )

    st.markdown("---")

    # --- Symbol selection ---
    _data_dir_scan = Path("data")
    _downloaded = scan_downloaded_data(_data_dir_scan)
    _all_symbols = sorted(_downloaded.keys())

    # If user clicked "Quét coin này" from top gainers, prefill symbol
    _scan_from_gainer = st.session_state.get("scan_symbol")
    if _scan_from_gainer:
        symbol = _scan_from_gainer
        st.info(f"🎯 Đã chọn {_scan_from_gainer} từ top gainers")
        st.session_state.scan_symbol = None  # consume
    elif _all_symbols:
        _symbol_labels = {}
        for sym in _all_symbols:
            klines_info = _downloaded.get(sym, {}).get("klines", {})
            date_range = ""
            if klines_info:
                date_range = f" ({klines_info['first_date'][:10]})"
            _symbol_labels[sym] = f"{sym}{date_range}"

        selected_label = st.selectbox(
            "Mã coin",
            options=list(_symbol_labels.keys()),
            format_func=lambda s: _symbol_labels[s],
        )
        symbol = selected_label

        with st.expander("➕ Thêm coin mới", expanded=False):
            custom_symbol = st.text_input(
                "Nhập mã", value="", placeholder="VD: SOLUSDT, DOGEUSDT...", key="custom_sym"
            ).strip().upper()
            if custom_symbol:
                symbol = custom_symbol
    else:
        symbol = st.text_input(
            "Mã coin", value="BTCUSDT", placeholder="VD: BTCUSDT, ETHUSDT..."
        ).strip().upper()

    # --- Date range ---
    now = datetime.now()
    default_start = now - timedelta(days=30)

    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("Từ", value=default_start)
    with col_d2:
        end_date = st.date_input("Đến", value=now)

    # --- Advanced config (collapsed) ---
    with st.expander("⚙️ Nâng cao", expanded=False):
        db_path = st.text_input("Database", value="./data/dev.duckdb")
        artifact_dir = st.text_input("Artifact dir", value="./artifacts")
        if mode == "🧪 Backtest":
            hypothesis_id = st.text_input("Hypothesis ID", value="hyp_dashboard_001")
            baseline_model = st.selectbox("Model", ["logreg_walkforward", "dummy"])
            seed = st.number_input("Seed", value=42, step=1)
        else:
            hypothesis_id = "hyp_dashboard_001"
            baseline_model = "logreg_walkforward"
            seed = 42

    # --- Main action button ---
    st.markdown("---")
    if mode == "🔍 Watchlist":
        run_button = st.button("🔍 Quét tín hiệu", type="primary", use_container_width=True)
    else:
        run_button = st.button("🚀 Chạy Backtest", type="primary", use_container_width=True)

    # --- Data status (compact) ---
    if symbol and symbol in _downloaded:
        with st.expander(f"📦 Dữ liệu {symbol}", expanded=False):
            sym_data = _downloaded[symbol]
            _dtype_names = {
                "klines": "Nến 5m",
                "funding": "Funding",
                "open_interest": "OI",
                "taker_ratio": "Taker Vol",
                "global_ratio": "Global L/S",
                "top_ratio": "Top L/S",
            }
            for dt in ["klines", "funding", "open_interest", "taker_ratio", "global_ratio", "top_ratio"]:
                if dt in sym_data:
                    d = sym_data[dt]
                    st.caption(f"✅ {_dtype_names.get(dt, dt)}: {d['rows']:,} dòng")
                else:
                    st.caption(f"⬜ {_dtype_names.get(dt, dt)}: chưa có")
    elif symbol:
        st.caption(f"⬜ Chưa có dữ liệu {symbol} — sẽ tải khi bấm chạy")


# ============================================================
# HELPER: Run pipeline steps (shared by both modes)
# ============================================================
def _run_pipeline_steps(
    symbol: str, start_dt, end_dt, db_path: str, settings: AppSettings,
    progress_cb=None, status_cb=None,
) -> tuple[DuckDBQueryLayer, int, int, int, int, int, int, float]:
    """
    Run collect → normalize → labels → features.
    Incremental: skips collectors if data already covers range,
    skips parquet files already processed, reuses DuckDB if exists.

    progress_cb: optional callback(step_pct, step_text)
    status_cb: optional callback(status_text)
    Returns (db, n_total, n_pos, n_neg, n_exc, n_rows, n_cols, elapsed).
    """
    t0 = time.perf_counter()
    client = BinanceClient()
    run_id = f"run_{int(time.time())}"
    data_dir = Path(settings.paths.data_dir)

    def _p(pct, txt):
        if progress_cb:
            progress_cb(pct, txt)

    def _s(txt):
        if status_cb:
            status_cb(txt)

    # --- Step 1: Incremental collect (skip if already covered) ---
    _s("📡 Kiểm tra & tải dữ liệu mới...")
    _p(10, "Thu thập (incremental)")
    collectors = [
        ("klines", "Nến 5m", KlinesCollector(client, settings)),
        ("funding", "Funding Rate", FundingCollector(client, settings)),
        ("open_interest", "Open Interest", OpenInterestCollector(client, settings)),
        ("taker_ratio", "Taker Volume", TakerRatioCollector(client, settings)),
        ("global_ratio", "Global L/S", GlobalRatioCollector(client, settings)),
        ("top_ratio", "Top L/S", TopRatioCollector(client, settings)),
    ]
    n_fetched = 0
    n_skipped = 0
    for data_type, label, collector in collectors:
        inc_start = get_incremental_start(data_dir, data_type, symbol, start_dt)
        if inc_start > end_dt:
            n_skipped += 1
            continue
        collector.collect(inc_start, end_dt, run_id)
        n_fetched += 1

    if n_fetched == 0:
        _s(f"✓ Dữ liệu đã cập nhật (tất cả {n_skipped} nguồn đã có) — bỏ qua tải")
    else:
        _s(f"✓ Đã tải {n_fetched} nguồn mới, {n_skipped} nguồn đã có")

    # --- Step 2: Normalize (skip files already processed) ---
    _s("🔄 Chuẩn hóa dữ liệu...")
    _p(30, "Chuẩn hóa Parquet")
    process_raw_to_parquet(settings)

    # --- Step 3: Build timeline (recreate views — fast, in-memory) ---
    _s("🔗 Xây dựng timeline...")
    _p(40, "Timeline + Align")
    db = DuckDBQueryLayer(db_path)
    build_raw_timeline(db, settings)

    # --- Step 4: Labels (recompute — fast with SQL CREATE TABLE AS) ---
    _s("🏷️ Tính nhãn phân phối...")
    _p(60, "Sinh nhãn")
    engine = DistributionLabelEngine()
    n_total, n_pos, n_neg = engine.compute_all_to_table(db.conn, "raw_timeline", "labels")
    n_exc = n_total - n_pos - n_neg

    # --- Step 5: Features (recompute) ---
    _s("⚙️ Tính feature...")
    _p(80, "Tính feature")
    build_features(db, "raw_timeline", "feature_results")
    n_rows = db.conn.execute("SELECT count(*) FROM feature_results").fetchone()[0]
    n_cols = db.conn.execute(
        "SELECT count(*) FROM information_schema.columns WHERE table_name='feature_results'"
    ).fetchone()[0]

    elapsed = time.perf_counter() - t0
    return db, n_total, n_pos, n_neg, n_exc, n_rows, n_cols, elapsed


# ============================================================
# WATCHLIST MODE
# ============================================================
if run_button and mode == "🔍 Watchlist":
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    progress = st.progress(0, text="Đang quét...")
    status = st.empty()

    try:
        settings = AppSettings()
        settings.binance.symbol = symbol

        def _wl_progress(pct, txt):
            progress.progress(pct, text=txt)

        def _wl_status(txt):
            status.info(txt)

        db, n_total, n_pos, n_neg, n_exc, n_rows, n_cols, t_pipe = _run_pipeline_steps(
            symbol, start_dt, end_dt, db_path, settings,
            progress_cb=_wl_progress, status_cb=_wl_status,
        )

        if n_pos == 0:
            status.warning(
                f"⚠️ Không có event phân phối nào trong dữ liệu {symbol}. "
                "Thử coin biến động hơn hoặc khoảng thời gian dài hơn."
            )
            progress.empty()
        else:
            status.info("🧠 Đang train model + dự đoán...")
            progress.progress(90, text="Train + Predict")

            from dao_vang.experiments.walk_forward import train_and_predict_latest

            query = """
                SELECT f.*, l.label_value AS is_distribution
                FROM feature_results f
                LEFT JOIN labels l ON f.feature_time = l.signal_time AND f.symbol = l.symbol
            """
            df = db.conn.execute(query).df()
            df = df.dropna(subset=['is_distribution'])

            exclude_cols = ['feature_time', 'decision_time', 'is_distribution', 'quality_status', 'symbol']
            feature_cols = [c for c in df.columns if c not in exclude_cols]

            result_w = train_and_predict_latest(df, feature_cols, n_latest=12)
            predictions = result_w.get("predictions", [])
            model_metrics = result_w.get("model_metrics", {})
            model_info = result_w.get("model_info", {})

            progress.progress(100, text="Hoàn thành!")
            status.success(f"✅ Quét xong trong {t_pipe:.1f}s — {n_pos} event phân phối trong lịch sử")

            if not predictions:
                st.warning("Không đủ dữ liệu để dự đoán (cần ít nhất 200 nến có nhãn).")
            else:
                # === Summary row ===
                high_risk = [p for p in predictions if p["risk_level"] == "CAO"]
                med_risk = [p for p in predictions if p["risk_level"] == "TRUNG BÌNH"]
                max_prob = max(p["probability"] for p in predictions)

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Probability cao nhất", f"{max_prob:.1%}", help=_glossary_tooltip("Probability"))
                c2.metric("Tín hiệu CAO", len(high_risk), help=_glossary_tooltip("Risk Level"))
                c3.metric("Tín hiệu TB", len(med_risk), help=_glossary_tooltip("Risk Level"))
                c4.metric("Val Precision", f"{model_metrics.get('precision', 0):.1%}", help=_glossary_tooltip("Precision"))

                # === Alert ===
                if high_risk:
                    st.error(f"🚨 **{len(high_risk)} nến nguy cơ CAO** — coin có thể xả trong 24h!")
                elif med_risk:
                    st.warning(f"⚠️ {len(med_risk)} nến nguy cơ TRUNG BÌNH — theo dõi sát")
                else:
                    st.success("✅ Không có tín hiệu nguy cơ. Thị trường bình thường.")

                # === Predictions table + chart side by side ===
                col_table, col_chart = st.columns([3, 2])

                with col_table:
                    st.markdown("#### Dự đoán 12 nến mới nhất")
                    st.caption("Probability = xác suất coin phân phối trong 24h tới. Risk = phân loại dựa trên threshold.")
                    pred_df = pd.DataFrame(predictions)
                    pred_df["probability"] = pred_df["probability"].apply(lambda x: f"{x:.1%}")
                    pred_df["close"] = pred_df["close"].apply(lambda x: f"{x:.6f}" if x else "N/A")
                    pred_df["feature_time"] = pred_df["feature_time"].str[:19]
                    pred_df = pred_df[["feature_time", "symbol", "close", "probability", "risk_level"]]
                    pred_df.columns = ["Thời gian", "Coin", "Giá close", "Probability", "Risk"]

                    def _risk_style(val):
                        colors = {"CAO": "#ff4444", "TRUNG BÌNH": "#ffaa00", "THẤP": "#44aa44", "RẤT THẤP": "#2266aa"}
                        c = colors.get(val, "")
                        return f"background-color: {c}; color: white" if c else ""

                    st.dataframe(
                        pred_df.style.map(_risk_style, subset=["Risk"]),
                        use_container_width=True,
                        hide_index=True,
                    )

                with col_chart:
                    st.markdown("#### Probability theo thời gian")
                    chart_df = pd.DataFrame(predictions)
                    chart_df["feature_time"] = pd.to_datetime(chart_df["feature_time"])
                    chart_df = chart_df.set_index("feature_time")[["probability"]]
                    thresh = model_metrics.get("threshold", 0.5)
                    st.line_chart(chart_df)
                    st.caption(f"🔴 Threshold = {thresh:.2f} — probability vượt đường này = tín hiệu phân phối (xem 📖 Thuật ngữ)")

                # === Feature importance ===
                top_feats = model_info.get("top_features", [])
                if top_feats:
                    with st.expander("🔍 Top 5 feature quan trọng nhất", expanded=False):
                        st.caption("Hệ số dương = feature tăng → xác suất phân phối tăng. Hệ số âm = ngược lại.")
                        feat_df = pd.DataFrame(top_feats)
                        feat_df["coefficient"] = feat_df["coefficient"].apply(lambda x: f"{x:+.4f}")
                        feat_df.columns = ["Feature", "Hệ số"]
                        st.dataframe(feat_df, use_container_width=True, hide_index=True)

                # === Glossary ===
                st.markdown("---")
                _render_glossary_tab()

        db.conn.close()
    except Exception as e:
        status.error(f"❌ Lỗi: {str(e)}")
        progress.empty()


# ============================================================
# BACKTEST MODE
# ============================================================
elif run_button and mode == "🧪 Backtest":
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(artifact_dir).mkdir(parents=True, exist_ok=True)

    progress = st.progress(0, text="Khởi động...")
    status = st.empty()
    log_lines: list[str] = []

    def log(msg: str):
        log_lines.append(msg)

    t_start = time.perf_counter()

    try:
        settings = AppSettings()
        settings.binance.symbol = symbol

        def _bt_progress(pct, txt):
            progress.progress(pct, text=txt)

        def _bt_status(txt):
            status.info(txt)

        # Steps 1-5 (with detailed progress)
        db, n_total, n_positive, n_negative, n_excluded, row_count, col_count, t_pipe = _run_pipeline_steps(
            symbol, start_dt, end_dt, db_path, settings,
            progress_cb=_bt_progress, status_cb=_bt_status,
        )
        log(f"Pipeline 1→4: {t_pipe:.1f}s ({n_total} nhãn, {n_positive}+/{n_negative}-/{n_excluded}exc)")

        # Step 5: Experiment
        status.info("🧪 Đang chạy model + báo cáo...")
        progress.progress(90, text="Model + Report")
        t0 = time.perf_counter()

        config = ExperimentConfig(
            hypothesis_id=hypothesis_id,
            baseline_model=baseline_model,
            dataset_version="v1", label_version="v1",
            feature_set_version="v1", split_version="v1",
            seed=seed, metrics=["precision", "recall", "brier"],
            db_path=db_path,
        )
        result = run_experiment(config, conn=db.conn)
        registry = ArtifactRegistry(Path(artifact_dir))
        artifact_id = registry.save_experiment(result)
        artifact = registry.load_experiment(artifact_id)
        md_content = generate_markdown_report(artifact)

        total_time = time.perf_counter() - t_start
        progress.progress(100, text="Hoàn thành!")
        status.success(f"✅ Backtest xong trong {total_time:.1f}s — Artifact: `{artifact_id}`")
        log(f"Bước 5: model xong ({time.perf_counter() - t0:.1f}s)")
        log(f"Tổng: {total_time:.1f}s")

        # === Conclusion card ===
        st.markdown("---")
        results_data = result.get("results", {})
        model_p = results_data.get("aggregate", {}).get("precision_mean", 0.0)
        baselines_data = results_data.get("baselines", {})
        best_bp = max((m.get("precision_mean", 0) for m in baselines_data.values()), default=0)
        leak_status = results_data.get("leakage_report", {}).get("status", "unknown")
        n_pos = results_data.get("data_quality", {}).get("label_distribution", {}).get("positive", 0)

        if results_data.get("warning"):
            st.error(f"⚠️ {results_data['warning']}")
        elif model_p > best_bp and model_p > 0:
            if n_pos < 100:
                st.warning(f"🟡 **TIẾP TỤC (thận trọng)** — precision {model_p:.4f} > baseline {best_bp:.4f}, nhưng chỉ {n_pos} event.")
            else:
                st.success(f"🟢 **TIẾP TỤC** — precision {model_p:.4f} > baseline {best_bp:.4f}, leakage: {leak_status}")
        elif model_p > 0:
            st.warning(f"🟡 **SỬA GIẢ THUYẾT** — precision {model_p:.4f} ≤ baseline {best_bp:.4f}")
        else:
            st.error("🔴 **DỪNG** — Model không hoạt động (metrics = 0)")

        # === Results tabs ===
        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "📈 Metrics", "📊 Baselines", "🏷️ Nhãn", "🔍 Chất lượng", "📄 Báo cáo", "📖 Thuật ngữ"
        ])

        # --- Tab: Metrics ---
        with tab1:
            agg = results_data.get("aggregate", {})
            per_fold = results_data.get("per_fold", [])

            if agg:
                # Compact metric row with tooltips
                mc = st.columns(6)
                metrics_display = [
                    ("Precision", agg.get("precision_mean", 0), _glossary_tooltip("Precision")),
                    ("±", agg.get("precision_std", 0), ""),
                    ("Recall", agg.get("recall_mean", 0), _glossary_tooltip("Recall")),
                    ("±", agg.get("recall_std", 0), ""),
                    ("Brier", agg.get("brier_mean", 0), _glossary_tooltip("Brier Score")),
                    ("±", agg.get("brier_std", 0), ""),
                ]
                for col, (k, v, tip) in zip(mc, metrics_display):
                    if k == "±":
                        col.caption(f"±{v:.4f}")
                    else:
                        col.metric(k, f"{v:.4f}", help=tip if tip else None)

                if per_fold:
                    st.markdown("#### Walk-Forward Folds")
                    st.caption("Mỗi fold: train trên quá khứ, test trên tương lai. Thresh = threshold tối ưu. Train/Test = rows (số positive).")
                    fold_rows = []
                    for fold in per_fold:
                        row = {"Fold": fold.get("fold_idx", "?")}
                        if fold.get("skipped"):
                            row["Status"] = f"SKIP: {fold.get('reason', '')}"
                        else:
                            m = fold.get("metrics", {})
                            row["P"] = f"{m.get('precision', 0):.3f}"
                            row["R"] = f"{m.get('recall', 0):.3f}"
                            row["Brier"] = f"{m.get('brier', 0):.3f}"
                            row["Thresh"] = f"{m.get('threshold', 0.5):.2f}"
                            row["Train"] = f"{fold.get('train_size', 0)} ({fold.get('train_positives', 0)}+)"
                            row["Test"] = f"{fold.get('test_size', 0)} ({fold.get('test_positives', 0)}+)"
                        fold_rows.append(row)
                    st.dataframe(pd.DataFrame(fold_rows), use_container_width=True, hide_index=True)

                all_zero = all(v == 0 for v in agg.values() if isinstance(v, (int, float)))
                if all_zero:
                    st.error("❌ Metrics = 0 — model không học được. Kiểm tra data/split/imbalance.")
            else:
                st.info("Không có metrics.")

        # --- Tab: Baselines ---
        with tab2:
            baselines = results_data.get("baselines", {})
            if baselines:
                st.caption("Baseline = phương pháp đơn giản làm mốc. Model phải vượt baseline tốt nhất mới được triển khai.")
                rows = [{"Model": "LogReg", "Precision": model_p, "Recall": agg.get("recall_mean", 0), "Brier": agg.get("brier_mean", 0)}]
                for name, m in baselines.items():
                    rows.append({"Model": name, "Precision": m.get("precision_mean", 0), "Recall": m.get("recall_mean", 0), "Brier": m.get("brier_mean", 0)})
                df_comp = pd.DataFrame(rows)
                st.dataframe(
                    df_comp.style.format({"Precision": "{:.4f}", "Recall": "{:.4f}", "Brier": "{:.4f}"}),
                    use_container_width=True, hide_index=True,
                )
                st.bar_chart(df_comp.set_index("Model")[["Precision", "Recall"]])

                if model_p > best_bp:
                    st.success(f"✅ Model vượt baseline ({model_p:.4f} > {best_bp:.4f})")
                else:
                    st.warning(f"⚠️ Model chưa vượt baseline ({model_p:.4f} ≤ {best_bp:.4f})")
            else:
                st.info("Không có baseline.")

        # --- Tab: Labels ---
        with tab3:
            st.caption("Phân phối (1) = coin giảm ≥8% trong 24h tới, MAE ≤4%. Bình thường (0) = không đạt. Loại trừ = không đủ dữ liệu tương lai.")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Tổng", f"{n_total:,}")
            c2.metric("Phân phối (1)", n_positive, help=_glossary_tooltip("Phân phối"))
            c3.metric("Bình thường (0)", f"{n_negative:,}")
            c4.metric("Loại trừ", n_excluded, help="Rows không đủ dữ liệu tương lai trong horizon 24h để gán label.")

            chart_data = pd.DataFrame({
                "Nhãn": ["Phân phối", "Bình thường", "Loại trừ"],
                "Số lượng": [n_positive, n_negative, n_excluded],
            })
            st.bar_chart(chart_data.set_index("Nhãn"))

            if n_positive == 0:
                st.warning("⚠️ Không có event phân phối. Thử coin biến động hơn.")
            elif n_positive < 50:
                st.warning(f"⚠️ Chỉ {n_positive} event — quá ít. Cần thêm dữ liệu.")

        # --- Tab: Quality ---
        with tab4:
            dq = results_data.get("data_quality", {})
            leak = results_data.get("leakage_report", {})

            st.caption("Leakage = dùng dữ liệu tương lai trong feature/evaluation. Phải PASS mới được triển khai.")
            leak_status = leak.get("status", "unknown")
            if leak_status == "passed":
                st.success("✅ Không phát hiện leakage")
            else:
                st.error(f"❌ Leakage: {leak.get('forbidden_columns', [])}")

            if dq:
                qc = st.columns(4)
                qc[0].metric("Rows", f"{dq.get('total_rows', 0):,}")
                qc[1].metric("Duplicates", dq.get("duplicate_count", 0))
                qc[2].metric("Prevalence", f"{dq.get('label_distribution', {}).get('prevalence', 0):.4f}", help=_glossary_tooltip("Prevalence"))
                qc[3].metric("Days", f"{dq.get('time_range', {}).get('duration_days', 0):.1f}")

                nc = dq.get("null_counts", {})
                if nc:
                    with st.expander("Top null columns", expanded=False):
                        st.dataframe(
                            pd.DataFrame(list(nc.items()), columns=["Cột", "Null"]),
                            use_container_width=True, hide_index=True,
                        )

        # --- Tab: Report ---
        with tab5:
            with st.expander("📄 Markdown Report", expanded=True):
                st.markdown(md_content)
            with st.expander("📋 Log", expanded=False):
                st.code("\n".join(log_lines), language="text")

        # --- Tab: Glossary ---
        with tab6:
            _render_glossary_tab()

        db.conn.close()
    except Exception as e:
        status.error(f"❌ Lỗi: {str(e)}")
        progress.empty()


# ============================================================
# IDLE STATE
# ============================================================
elif not run_button:
    st.markdown("---")
    if mode == "🔍 Watchlist":
        st.markdown("""
        ### 🔍 Watchlist — Phát hiện coin sắp xả

        **Cách dùng:**
        1. Chọn mã coin ở thanh bên
        2. Chọn khoảng thời gian (mặc định 30 ngày)
        3. Bấm **"Quét tín hiệu"**

        App sẽ train model trên lịch sử → dự đoán probability phân phối trên 12 nến mới nhất.
        """)
    else:
        st.markdown("""
        ### 🧪 Backtest — Đánh giá model

        **Cách dùng:**
        1. Chọn mã coin + khoảng thời gian
        2. Bấm **"Chạy Backtest"**

        App sẽ chạy pipeline 5 bước: thu thập → chuẩn hóa → nhãn → feature → model.
        Kết quả: metrics, baseline comparison, data quality, leakage audit, conclusion.
        """)

    # Glossary always available in idle state
    st.markdown("---")
    _render_glossary_tab()
