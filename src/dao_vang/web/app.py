import json as _json
import streamlit as st
import time
import duckdb
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
    "Feature Time": "Timestamp mà feature vector đại diện. Dùng close time của nến 5 phút đã đóng.",
    "Signal Price": "Giá tham chiếu tại thời điểm tín hiệu. Dùng close của nến futures 5 phút đã đóng.",
    "Horizon": "Khoảng thời gian tương lai dùng để xác định outcome. Mặc định: 24 giờ.",
    "Target Drawdown": "Mức giảm tối thiểu từ signal price cần đạt trong horizon để label dương. Mặc định: 8%.",
    "MAE": "Max Adverse Excursion — mức tăng bất lợi lớn nhất so với signal price trước khi target đạt. Mặc định: ≤4%.",
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


def _render_guide_tab():
    """Render hướng dẫn dùng tool (web app) và CLI."""
    st.markdown("#### 🧭 Hướng dẫn sử dụng tool & ứng dụng")
    st.caption("Tổng hợp cách dùng giao diện web và CLI để thu thập dữ liệu, quét tín hiệu, chạy backtest và xuất báo cáo.")

    guide_search = st.text_input(
        "🔍 Tìm trong hướng dẫn",
        placeholder="VD: backtest, CLI, watchlist, collect...",
        key="guide_search",
    )

    def _match(text: str) -> bool:
        if not guide_search:
            return True
        return guide_search.lower() in text.lower()

    # ---------- 1. WEB APP ----------
    if _match("Web app giao diện Streamlit Phát hiện Distribution Backtest Thuật ngữ Hướng dẫn Quan sát thị trường"):
        with st.expander("🌐 1. Giao diện web (Streamlit app)", expanded=False):
            st.markdown(
                """
App web gồm **5 tab** — sắp xếp theo ưu tiên:

| # | Tab | Mục đích | Ưu tiên |
|---|-----|----------|---------|
| 1 | 🎯 **Phát hiện Distribution** | Tính probability + risk level + so sánh baseline cho BTCUSDT | **Core** |
| 2 | 🧪 **Backtest** | Đánh giá model trên lịch sử (walk-forward, leakage, calibration) | Kiểm chứng |
| 3 | 📖 **Thuật ngữ** | Tra cứu khái niệm (precision, MAE, funding...) | Reference |
| 4 | 🧭 **Hướng dẫn** | (Tab này) Hướng dẫn dùng web + CLI | Reference |
| 5 | 📊 **Quan sát thị trường** | Top gainers/losers, watchlist multi-coin | Phụ |

**Mục tiêu tối cao:** Phát hiện sớm coin có xác suất cao chuyển từ tăng giá sang phân phối.

**Khởi động web:**
```bash
python -m dao_vang.web.run
# hoặc
streamlit run src/dao_vang/web/app.py
```
"""
            )

    # ---------- 2. TAB PHÁT HIỆN DISTRIBUTION ----------
    if _match("Phát hiện Distribution probability risk baseline threshold feature BTCUSDT"):
        with st.expander("🎯 2. Tab Phát hiện Distribution — core", expanded=False):
            st.markdown(
                """
**Đây là tab ưu tiên #1** — trả lời câu hỏi cốt lõi: *dữ liệu tối thiểu có tạo lợi thế thống kê trong phát hiện Distribution không?*

**Quy trình:**
1. Chọn mã coin ở thanh bên (mặc định **BTCUSDT**).
2. Chọn khoảng thời gian (mặc định 30 ngày).
3. Bấm **"🔍 Phát hiện Distribution"**.
4. App tự thu thập klines/funding/OI/taker ratios từ Binance → build feature → train LogReg → dự đoán 12 nến mới nhất.

**Label spec (v0.1):** horizon 24h, target drawdown ≥8%, MAE ≤4%.

**Kết quả hiển thị:**
- **Probability + Risk Level** cho 12 nến mới nhất:
  - 🔴 **CAO**: probability ≥ 1.5×threshold
  - 🟠 **TRUNG BÌNH**: probability ≥ threshold
  - 🟡 **THẤP**: probability ≥ 0.5×threshold
  - ⚪ **RẤT THẤP**: probability < 0.5×threshold
- **Chart giá** + **Probability theo thời gian**.
- **Top 5 feature quan trọng** (feature importance).
- **So sánh Model vs Baseline** (prevalence baseline) — trả lời: có lợi thế thống kê không?
"""
            )

    # ---------- 3. TAB BACKTEST ----------
    if _match("Backtest experiment baseline walk-forward metrics calibration leakage"):
        with st.expander("🧪 3. Tab Backtest — đánh giá model", expanded=False):
            st.markdown(
                """
6 sub-tab bên trong:

| Sub-tab | Nội dung |
|---------|----------|
| 📈 Metrics | Precision / Recall / Brier Score / walk-forward folds |
| 📊 Baselines | So sánh model với baseline — model phải vượt baseline mới triển khai |
| 🏷️ Nhãn | Phân phối label, prevalence, label spec |
| 🔍 Chất lượng | Leakage check, calibration, embargo |
| 📄 Báo cáo | Markdown report của experiment |
| 📖 Thuật ngữ | Tra cứu thuật ngữ |

**Lưu ý:** backtest dùng **walk-forward** (không shuffle) + **embargo 12h** giữa train/test để tránh lookahead bias.
"""
            )

    # ---------- 4. CLI ----------
    if _match("CLI command line typer data labels features experiment report"):
        with st.expander("⌨️ 4. CLI (dòng lệnh) — tự động hóa & batch", expanded=False):
            st.markdown(
                """
CLI dùng **Typer**. Cài: `pip install -e .` (hoặc `uv sync`). Gọi: `dao-vang --help`.

**Nhóm lệnh:**

```bash
# Data — thu thập & chuẩn hóa
dao-vang data collect --start-timestamp 1700000000 --end-timestamp 1700086400 --run-id manual_run
dao-vang data normalize

# Labels — tạo nhãn từ dữ liệu đã chuẩn hóa
dao-vang labels generate --db-path ./data/duckdb --source-table klines_5m

# Features — build feature vector
dao-vang features generate \
    --db-path ./data/duckdb \
    --source-table klines_5m \
    --target-table features_v1

# Experiment — train + đánh giá + lưu artifact
dao-vang experiment run \
    --hypothesis-id H1 \
    --baseline-model rules \
    --dataset-version ds_v1 \
    --label-version lbl_v1 \
    --feature-set-version feat_v1 \
    --split-version wf_v1 \
    --seed 42 \
    --metrics precision,recall \
    --artifact-dir ./artifacts

# Report — xuất markdown từ artifact
dao-vang report generate \
    --artifact-id <ARTIFACT_ID> \
    --artifact-dir ./artifacts \
    --output-file ./reports/exp_H1.md
```

**Workflow điển hình (tự động hoá):**
```bash
dao-vang data collect ... && \
dao-vang labels generate ... && \
dao-vang features generate ... && \
dao-vang experiment run ... && \
dao-vang report generate ...
```
"""
            )

    # ---------- 5. WORKFLOW END-TO-END ----------
    if _match("workflow end-to-end pipeline thu thập train triển khai forward test"):
        with st.expander("🔁 5. Workflow end-to-end (web + CLI)", expanded=False):
            st.markdown(
                """
**Vòng lặp khuyến nghị:**

1. **Phát hiện** (web → tab #1 Phát hiện Distribution): xem probability + risk level + so sánh baseline hằng ngày.
2. **Đánh giá định kỳ** (web → tab #2 Backtest hoặc CLI `experiment run`):
   - Chạy walk-forward trên dữ liệu mới.
   - So sánh với baseline — nếu không vượt → sửa giả thuyết / thêm feature / thu thập thêm dữ liệu.
   - Kiểm tra calibration & leakage.
3. **Xuất báo cáo** (CLI `report generate` hoặc web sub-tab 📄 Báo cáo) để lưu vết experiment.
4. **Forward test**: áp dụng model đã đóng băng lên dữ liệu mới sinh ra *sau* khi đóng băng — kiểm tra stability thực tế trước khi dùng thật.
5. **Quan sát thị trường** (web → tab #5, phụ): tham khảo top gainers/losers khi cần mở rộng sang coin khác.

**Quy tắc cốt lõi:** không bao giờ dùng label làm feature; mọi feature phải point-in-time; model không vượt baseline thì không triển khai.
"""
            )

    # ---------- 6. TROUBLESHOOTING ----------
    if _match("lỗi error troubleshooting binance api duckdb không có dữ liệu"):
        with st.expander("🛠️ 6. Xử lý lỗi thường gặp", expanded=False):
            st.markdown(
                """
- **Phát hiện Distribution không có kết quả**: đảm bảo có đủ dữ liệu 30 ngày cho BTCUSDT. Nếu chưa có, app sẽ tự tải khi bấm chạy.
- **Model precision = 0**: quá ít event phân phối trong dữ liệu — mở rộng khoảng thời gian.
- **Không vượt baseline**: feature hiện tại chưa đủ — thử thêm feature hoặc kiểm tra drift.
- **Backtest fail leakage check**: feature đang dùng thông tin tương lai — rà `feature_set_version` và đảm bảo feature chỉ dùng dữ liệu ≤ feature time.
- **CLI `dao-vang: command not found`**: chạy `pip install -e .` hoặc `uv sync` rồi `uv run dao-vang --help`.
- **DuckDB file lock**: đảm bảo không có process khác đang mở cùng file `*.duckdb`.
- **Calibration lệch nhiều**: tăng lượng dữ liệu train hoặc kiểm tra drift trên window mới.
"""
            )

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


# --- Fetch tickers once (cached in session state) ---
if "_tickers_cache" not in st.session_state:
    st.session_state._tickers_cache = _fetch_24h_tickers()
_tickers = st.session_state._tickers_cache


# --- Header ---
st.title("🪙 Đảo Vàng")
st.caption("Phát hiện coin sắp xả phân phối")

# Ticker marquee (always visible)
_col_ticker, _col_refresh = st.columns([8, 1])
with _col_ticker:
    _render_ticker_marquee(_tickers, top_n=20)
with _col_refresh:
    if st.button("🔄", help="Làm mới ticker"):
        st.session_state._tickers_cache = _fetch_24h_tickers()
        st.rerun()

st.markdown("---")


# ============================================================
# MAIN TABS — Phát hiện Distribution là ưu tiên #1
# ============================================================
tab_detect, tab_scan, tab_backtest, tab_glossary, tab_guide, tab_market = st.tabs([
    "🎯 Phát hiện Distribution",
    "🔍 Quét Multi-Coin",
    "🧪 Backtest",
    "📖 Thuật ngữ",
    "🧭 Hướng dẫn",
    "📊 Quan sát thị trường",
])

# Containers for dynamic content (filled later)
_detect_container = tab_detect.container()
_scan_container = tab_scan.container()
_backtest_container = tab_backtest.container()
_glossary_container = tab_glossary.container()
_guide_container = tab_guide.container()
_market_container = tab_market.container()


# ============================================================
# TAB: QUÉT MULTI-COIN — scan top volatile coins for distribution edge
# ============================================================
with _scan_container:
    st.markdown("#### 🔍 Quét Multi-Coin — tìm coin có edge phát hiện Distribution")
    st.caption(
        "Quét top coin biến động → thu thập 90 ngày klines → chạy labels → đếm events → chạy experiment. "
        "Altcoin biến động lớn có nhiều distribution events hơn BTC → đủ data để validate. "
        "Label v0.1: 8% drawdown trong 24h, MAE ≤4%."
    )

    _scan_db_path = "./data/scan_volatile.duckdb"
    _scan_db_exists = Path(_scan_db_path).exists()

    # --- Controls ---
    _scan_col1, _scan_col2, _scan_col3 = st.columns([2, 1, 1])
    with _scan_col1:
        _n_coins = st.slider(
            "Số coin volatile nhất cần quét",
            min_value=5, max_value=30, value=15, step=5,
            help="Lấy top N coin theo |24h price change|, min $10M volume",
        )
    with _scan_col2:
        _scan_days = st.selectbox("Số ngày lịch sử", [30, 60, 90], index=2)
    with _scan_col3:
        _min_events = st.selectbox("Min events để chạy experiment", [30, 50, 100], index=1)

    _scan_run = st.button(
        "🚀 Chạy quét multi-coin",
        help="Thu thập klines 90 ngày + funding cho top volatile coins, chạy labels + experiment",
        type="primary",
    )

    # --- Display existing results if DB exists ---
    if _scan_db_exists and not _scan_run:
        try:
            _scan_conn = duckdb.connect(_scan_db_path, read_only=True)

            # Check if labels table exists
            _has_labels = _scan_conn.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_name = 'labels'"
            ).fetchone()[0] > 0

            if _has_labels:
                _coin_stats = _scan_conn.execute("""
                    SELECT
                        l.symbol,
                        count(*) AS total,
                        sum(CASE WHEN l.label_value = 1 THEN 1 ELSE 0 END) AS pos,
                        sum(CASE WHEN l.label_value = 0 THEN 1 ELSE 0 END) AS neg,
                        min(l.signal_time) AS first_ts,
                        max(l.signal_time) AS last_ts
                    FROM labels l
                    GROUP BY l.symbol
                    ORDER BY pos DESC
                """).fetchall()

                if _coin_stats:
                    st.markdown("##### 📊 Distribution events per coin (data đã thu thập)")
                    _stats_data = []
                    for sym, total, pos, neg, first_ts, last_ts in _coin_stats:
                        prev = pos / total if total > 0 else 0
                        days = (last_ts - first_ts).total_seconds() / 86400 if first_ts and last_ts else 0
                        _stats_data.append({
                            "Coin": sym,
                            "Total rows": total,
                            "Events (label=1)": pos,
                            "Negative": neg,
                            "Prevalence": f"{prev:.2%}",
                            "Days": f"{days:.1f}",
                        })
                    st.dataframe(pd.DataFrame(_stats_data), use_container_width=True, hide_index=True)

                    # Show experiment artifacts for scanned coins
                    _registry = ArtifactRegistry(Path("./artifacts"))
                    _artifacts = _registry.list_artifacts()
                    _scan_artifacts = [
                        a for a in _artifacts
                        if "volatile" in a.get("config", {}).get("hypothesis_id", "")
                    ]

                    if _scan_artifacts:
                        st.markdown("##### 🧪 Kết quả experiment (artifacts)")
                        _exp_data = []
                        for a in reversed(_scan_artifacts):
                            cfg = a.get("config", {})
                            res = a.get("results", {})
                            agg = res.get("aggregate", {})
                            baselines = res.get("baselines", {})
                            leak = res.get("leakage_report", {})
                            ci = agg.get("confidence_intervals", {}).get("precision", {})

                            model_p = agg.get("precision_mean", 0)
                            best_bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
                            n_valid = agg.get("n_valid_folds", 0)
                            n_skip = agg.get("n_skipped_folds", 0)
                            leak_status = leak.get("status", "?")

                            # Determine status
                            if leak_status != "passed":
                                status = "🔴 Leakage"
                            elif n_valid == 0:
                                status = "⚪ Không đủ fold"
                            elif model_p > best_bp and model_p > 0:
                                status = "🟢 Edge"
                            else:
                                status = "🟡 No edge"

                            sym = cfg.get("hypothesis_id", "").replace("hyp_volatile_", "")
                            _exp_data.append({
                                "Coin": sym,
                                "Status": status,
                                "Model P": f"{model_p:.4f}",
                                "Best Baseline P": f"{best_bp:.4f}",
                                "CI 95%": f"[{ci.get('ci_lower', 0):.3f}, {ci.get('ci_upper', 0):.3f}]",
                                "Valid folds": n_valid,
                                "Skipped": n_skip,
                                "Leakage": leak_status,
                                "Artifact": a.get("artifact_id", "")[:20],
                            })

                        if _exp_data:
                            st.dataframe(pd.DataFrame(_exp_data), use_container_width=True, hide_index=True)

                            # Highlight edge coins
                            _edge_coins = [e for e in _exp_data if "Edge" in e["Status"]]
                            if _edge_coins:
                                st.success(
                                    f"🟢 **{len(_edge_coins)} coin có edge sạch** (model > baseline, leakage passed): "
                                    + ", ".join(e["Coin"] for e in _edge_coins)
                                )
                            else:
                                st.info("Chưa có coin nào với edge sạch. Thử quét thêm hoặc thu thập thêm data.")
                    else:
                        st.info("Chưa có experiment artifacts cho scan. Bấm 'Chạy quét' để bắt đầu.")
                else:
                    st.info("Database có nhưng chưa có labels. Bấm 'Chạy quét' để bắt đầu.")
            else:
                st.info("Database có nhưng chưa có labels table. Bấm 'Chạy quét' để bắt đầu.")

            _scan_conn.close()
        except Exception as e:
            st.warning(f"Không đọc được scan DB: {e}")

    # --- Run scan on button click ---
    if _scan_run:
        if not _tickers:
            st.error("Không lấy được ticker data từ Binance.")
        else:
            import time as _time
            import logging as _logging
            _logging.getLogger("dao_vang").setLevel(_logging.WARNING)

            _scan_settings = AppSettings()
            _scan_client = BinanceClient()

            # Step 1: Select top volatile coins
            with st.spinner(f"Lấy top {_n_coins} coin volatile nhất..."):
                _usdt_pairs = [
                    d for d in _tickers
                    if d.get("symbol", "").endswith("USDT")
                    and float(d.get("quoteVolume", 0)) > 10_000_000
                ]
                _usdt_pairs.sort(
                    key=lambda x: abs(float(x.get("priceChangePercent", 0))), reverse=True
                )
                _scan_coins = _usdt_pairs[:_n_coins]
                # Ensure BTC included
                _scan_syms = [d["symbol"] for d in _scan_coins]
                if "BTCUSDT" not in _scan_syms:
                    _btc = next((d for d in _tickers if d["symbol"] == "BTCUSDT"), None)
                    if _btc:
                        _scan_coins.insert(0, _btc)

            st.markdown(f"**Top {len(_scan_coins)} coin volatile:** "
                        + ", ".join(d["symbol"] for d in _scan_coins))

            # Step 2: Collect klines + funding
            _now = datetime.now(timezone.utc)
            _start = _now - timedelta(days=_scan_days)
            _run_id = f"scan_ui_{int(_now.timestamp())}"

            _progress = st.progress(0.0, text="Bắt đầu thu thập...")
            _collected = []
            for i, d in enumerate(_scan_coins):
                sym = d["symbol"]
                _scan_settings.binance.symbol = sym
                _progress.progress(
                    (i / len(_scan_coins)) * 0.5,
                    text=f"[{i+1}/{len(_scan_coins)}] Thu thập {sym}..."
                )
                try:
                    _kl = KlinesCollector(_scan_client, _scan_settings)
                    _kl.collect(_start, _now, _run_id)
                    _fc = FundingCollector(_scan_client, _scan_settings)
                    _fc.collect(_start, _now, _run_id)
                    _collected.append(sym)
                except Exception as e:
                    st.warning(f"Lỗi thu thập {sym}: {e}")
                _time.sleep(0.15)

            _progress.progress(0.5, text=f"Đã thu thập {len(_collected)}/{len(_scan_coins)} coins. Normalize...")

            # Step 3: Normalize + timeline + labels
            try:
                process_raw_to_parquet(_scan_settings)
                _scan_db = DuckDBQueryLayer(_scan_db_path)
                build_raw_timeline(_scan_db, _scan_settings)

                _progress.progress(0.6, text="Tính labels...")
                _engine = DistributionLabelEngine()
                _n_total, _n_pos, _n_neg = _engine.compute_all_to_table(
                    _scan_db.conn, "raw_timeline", "labels"
                )

                # Count events per coin
                _coin_stats = _scan_db.conn.execute("""
                    SELECT symbol, count(*) AS total,
                           sum(CASE WHEN label_value = 1 THEN 1 ELSE 0 END) AS pos
                    FROM labels GROUP BY symbol ORDER BY pos DESC
                """).fetchall()

                _viable = [r[0] for r in _coin_stats if r[2] >= _min_events]

                _progress.progress(0.7, text=f"Build features + chạy experiment cho {len(_viable)} coin...")

                # Build features
                build_features(_scan_db, "raw_timeline", "feature_results")

                _registry = ArtifactRegistry(Path("./artifacts"))
                _results_summary = []

                for j, sym in enumerate(_viable):
                    _progress.progress(
                        0.7 + (j / max(len(_viable), 1)) * 0.3,
                        text=f"Experiment [{j+1}/{len(_viable)}]: {sym}"
                    )
                    # Swap to coin-only tables
                    _scan_db.conn.execute("DROP TABLE IF EXISTS _fr_bak")
                    _scan_db.conn.execute("CREATE TABLE _fr_bak AS SELECT * FROM feature_results")
                    _scan_db.conn.execute("DROP TABLE feature_results")
                    _scan_db.conn.execute(f"CREATE TABLE feature_results AS SELECT * FROM _fr_bak WHERE symbol = '{sym}'")
                    _scan_db.conn.execute("DROP TABLE IF EXISTS _lb_bak")
                    _scan_db.conn.execute("CREATE TABLE _lb_bak AS SELECT * FROM labels")
                    _scan_db.conn.execute("DROP TABLE labels")
                    _scan_db.conn.execute(f"CREATE TABLE labels AS SELECT * FROM _lb_bak WHERE symbol = '{sym}'")

                    try:
                        _cfg = ExperimentConfig(
                            hypothesis_id=f"hyp_volatile_{sym}",
                            baseline_model="logreg_walkforward",
                            dataset_version=f"v_scan_{sym}",
                            label_version="v1",
                            feature_set_version="v1",
                            split_version="v1",
                            seed=42,
                            metrics=["precision", "recall", "brier"],
                            db_path=_scan_db_path,
                        )
                        _result = run_experiment(_cfg, conn=_scan_db.conn)
                        _aid = _registry.save_experiment(_result)

                        _agg = _result.get("results", {}).get("aggregate", {})
                        _bl = _result.get("results", {}).get("baselines", {})
                        _lk = _result.get("results", {}).get("leakage_report", {})
                        _ci = _agg.get("confidence_intervals", {}).get("precision", {})
                        _mp = _agg.get("precision_mean", 0)
                        _bp = max((m.get("precision_mean", 0) for m in _bl.values()), default=0)
                        _nv = _agg.get("n_valid_folds", 0)
                        _ls = _lk.get("status", "?")

                        if _ls != "passed":
                            _st = "🔴 Leakage"
                        elif _nv == 0:
                            _st = "⚪ Không đủ fold"
                        elif _mp > _bp and _mp > 0:
                            _st = "🟢 Edge"
                        else:
                            _st = "🟡 No edge"

                        _n = _scan_db.conn.execute("SELECT count(*) FROM feature_results").fetchone()[0]
                        _np = _scan_db.conn.execute("SELECT count(*) FROM labels WHERE label_value = 1").fetchone()[0]
                        _results_summary.append({
                            "Coin": sym, "Status": _st, "N": _n, "Pos": _np,
                            "Model P": f"{_mp:.4f}", "Best Baseline P": f"{_bp:.4f}",
                            "CI 95%": f"[{_ci.get('ci_lower', 0):.3f}, {_ci.get('ci_upper', 0):.3f}]",
                            "Valid folds": _nv, "Leakage": _ls,
                        })
                    except Exception as e:
                        _results_summary.append({"Coin": sym, "Status": "❌ Error", "Error": str(e)})
                    finally:
                        _scan_db.conn.execute("DROP TABLE IF EXISTS feature_results")
                        _scan_db.conn.execute("CREATE TABLE feature_results AS SELECT * FROM _fr_bak")
                        _scan_db.conn.execute("DROP TABLE _fr_bak")
                        _scan_db.conn.execute("DROP TABLE labels")
                        _scan_db.conn.execute("CREATE TABLE labels AS SELECT * FROM _lb_bak")
                        _scan_db.conn.execute("DROP TABLE _lb_bak")

                _scan_db.conn.close()
                _progress.progress(1.0, text="Hoàn tất!")

                # Display results
                st.markdown("##### 📊 Kết quả quét")
                st.dataframe(pd.DataFrame(_results_summary), use_container_width=True, hide_index=True)

                _edge = [r for r in _results_summary if "Edge" in r.get("Status", "")]
                if _edge:
                    st.success(
                        f"🟢 **{len(_edge)} coin có edge sạch**: "
                        + ", ".join(r["Coin"] for r in _edge)
                    )
                else:
                    st.info("Chưa có coin với edge sạch. Thử tăng số ngày hoặc giảm min events.")

            except Exception as e:
                st.error(f"Lỗi chạy pipeline: {e}")
                import traceback
                st.code(traceback.format_exc())


# ============================================================
# TAB 5 (REFERENCE): QUAN SÁT THỊ TRƯỜNG — multi-coin overview
# ============================================================
with _market_container:
    if _tickers:
        _top_gainers = _tickers[:15]
        _top_losers = sorted(_tickers, key=lambda x: float(x.get("priceChangePercent", 0)))[:5]

        # --- Top gainers as clickable buttons ---
        st.markdown("##### 🟢 Top 15 tăng mạnh nhất — bấm để xem")
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
        st.markdown("##### 🔴 Top 5 giảm mạnh nhất")
        _loser_grid = st.columns(5)
        for i, d in enumerate(_top_losers):
            sym = d["symbol"]
            pct = float(d["priceChangePercent"])
            price = float(d["lastPrice"])
            col = _loser_grid[i % 5]
            label = f"{sym}\n{pct:+.2f}%"
            if col.button(label, key=f"loser_{sym}", use_container_width=True, help=f"Giá: {price:.6f} | Volume: {float(d['quoteVolume']):,.0f}"):
                st.session_state.selected_gainer = sym

        # --- Manual search ---
        st.markdown("---")
        _search_col, _view_col = st.columns([4, 1])
        with _search_col:
            _all_ticker_symbols = [d["symbol"] for d in _tickers[:50]]
            _detail_symbol = st.selectbox(
                "Hoặc chọn coin từ danh sách top 50",
                options=_all_ticker_symbols,
                index=0 if not st.session_state.selected_gainer else _all_ticker_symbols.index(st.session_state.selected_gainer) if st.session_state.selected_gainer in _all_ticker_symbols else 0,
                key="detail_gainer_select",
            )
        with _view_col:
            st.write("")
            if st.button("🔍 Xem chart", key="view_chart_btn", use_container_width=True):
                st.session_state.selected_gainer = _detail_symbol

        # Use selected_gainer if set, otherwise use selectbox
        _show_symbol = st.session_state.selected_gainer or _detail_symbol

        if _show_symbol:
            _klines = _fetch_recent_klines(_show_symbol, "1h", 48)
            if _klines:
                _kdf = pd.DataFrame(_klines)
                _ticker_info = next((d for d in _tickers if d["symbol"] == _show_symbol), {})

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
                    import streamlit.components.v1 as components
                    _tv_embed = f"""
                    <iframe
                        src="https://s.tradingview.com/widgetembed/?frameElementId=tv_chart&symbol=BINANCE%3A{_show_symbol}&interval={_tf}&hidesidetoolbar=false&symboledit=true&saveimage=false&toolbarbg=%231a1a2e&theme=dark&style=1&hideideas=true&locale=vi_VN"
                        style="width:100%;height:500px;border:0;margin:0;padding:0;"
                        allowfullscreen
                        allow="autoplay; clipboard-read; clipboard-write"
                    ></iframe>
                    """
                    components.html(_tv_embed, height=520)
                    st.caption("ℹ️ Nếu chart trắng — coin chưa có trên TradingView. Bấm ô symbol trên chart để đổi.")

                # --- Action buttons ---
                st.markdown("---")
                _wl_cols = st.columns([2, 1, 1, 1])
                with _wl_cols[0]:
                    if _show_symbol in st.session_state.watchlist:
                        st.success(f"✅ {_show_symbol} đã có trong watchlist")
                    else:
                        if st.button(f"➕ Thêm {_show_symbol} vào watchlist", key="add_wl"):
                            st.session_state.watchlist.append(_show_symbol)
                            _save_watchlist(st.session_state.watchlist)
                            st.success(f"✅ Đã thêm {_show_symbol}!")
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

    # --- Watchlist panel ---
    if st.session_state.watchlist:
        st.markdown("---")
        st.markdown(f"##### 📋 Watchlist ({len(st.session_state.watchlist)} coin)")
        _wl_df = pd.DataFrame([
            {"Coin": s, "Trạng thái": "Đã lưu"}
            for s in st.session_state.watchlist
        ])
        st.dataframe(_wl_df, use_container_width=True, hide_index=True)

        _wl_action = st.columns([1, 2, 1])
        with _wl_action[0]:
            if st.button("🗑️ Xóa tất cả"):
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
# SIDEBAR — shared config (symbol, date range, advanced)
# ============================================================
with st.sidebar:
    st.markdown("## 🪙 Đảo Vàng")
    st.caption("Phát hiện Distribution")

    st.markdown("---")

    # --- Symbol selection ---
    _data_dir_scan = Path("data")
    _downloaded = scan_downloaded_data(_data_dir_scan)
    _all_symbols = sorted(_downloaded.keys())

    # If user clicked "Quét coin này" from top gainers, prefill symbol
    _scan_from_gainer = st.session_state.get("scan_symbol")
    if _scan_from_gainer:
        symbol = _scan_from_gainer
        st.info(f"🎯 Đã chọn {_scan_from_gainer} từ thị trường")
        st.session_state.scan_symbol = None  # consume
    elif _all_symbols:
        _symbol_labels = {}
        for sym in _all_symbols:
            klines_info = _downloaded.get(sym, {}).get("klines", {})
            date_range = ""
            if klines_info:
                date_range = f" ({klines_info['first_date'][:10]})"
            _symbol_labels[sym] = f"{sym}{date_range}"

        # Default to BTCUSDT if available
        _default_idx = 0
        if "BTCUSDT" in _symbol_labels:
            _default_idx = list(_symbol_labels.keys()).index("BTCUSDT")

        selected_label = st.selectbox(
            "Mã coin",
            options=list(_symbol_labels.keys()),
            index=_default_idx,
            format_func=lambda s: _symbol_labels[s],
        )
        symbol = selected_label

        with st.expander("➕ Thêm coin mới", expanded=False):
            custom_symbol = st.text_input(
                "Nhập mã", value="", placeholder="VD: ETHUSDT, SOLUSDT...", key="custom_sym"
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
        hypothesis_id = st.text_input("Hypothesis ID", value="hyp_dashboard_001")
        baseline_model = st.selectbox("Model", ["logreg_walkforward", "dummy"])
        seed = st.number_input("Seed", value=42, step=1)

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

    # --- Action buttons ---
    st.markdown("---")
    run_scan = st.button("🔍 Phát hiện Distribution", type="primary", use_container_width=True)
    run_bt = st.button("🚀 Chạy Backtest", use_container_width=True)


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
# TAB 1 (ƯU TIÊN #1): PHÁT HIỆN DISTRIBUTION
# Core: tính probability + risk level + so sánh baseline cho BTCUSDT
# ============================================================
with _detect_container:
    # --- Label spec reminder ---
    _ls_c1, _ls_c2, _ls_c3, _ls_c4 = st.columns(4)
    _ls_c1.metric("Symbol mặc định", "BTCUSDT", help="Mặc định: BTCUSDT")
    _ls_c2.metric("Horizon", "24h", help=_glossary_tooltip("Horizon"))
    _ls_c3.metric("Target drawdown", "≥8%", help=_glossary_tooltip("Target Drawdown"))
    _ls_c4.metric("MAE tối đa", "≤4%", help=_glossary_tooltip("MAE"))

    st.markdown("---")

    if run_scan:
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

                # Historical distribution events (label=1) for chart markers
                _hist_dist = df[df['is_distribution'] == 1][['feature_time', 'symbol']].copy()
                _hist_dist['feature_time'] = pd.to_datetime(_hist_dist['feature_time'])

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

                    # Lead time from historical labels (how early does the signal warn?)
                    _hist_lead = df[df['is_distribution'] == 1]['lead_time_minutes'].dropna() if 'lead_time_minutes' in df.columns else pd.Series(dtype=float)
                    _median_lead = float(_hist_lead.median()) if len(_hist_lead) > 0 else None

                    c1, c2, c3, c4, c5 = st.columns(5)
                    c1.metric("Probability cao nhất", f"{max_prob:.1%}", help=_glossary_tooltip("Probability"))
                    c2.metric("Tín hiệu CAO", len(high_risk), help=_glossary_tooltip("Risk Level"))
                    c3.metric("Tín hiệu TB", len(med_risk), help=_glossary_tooltip("Risk Level"))
                    c4.metric("Val Precision", f"{model_metrics.get('precision', 0):.1%}", help=_glossary_tooltip("Precision"))
                    if _median_lead is not None:
                        c5.metric("Median lead time", f"{_median_lead:.0f}m", f"~{_median_lead/60:.1f}h", help="Thời gian trung bình từ tín hiệu đến khi phân phối xảy ra (từ lịch sử)")
                    else:
                        c5.metric("Median lead time", "N/A", help="Chưa đủ event phân phối lịch sử")

                    # === Alert ===
                    if high_risk:
                        _alert_msg = f"🚨 **{len(high_risk)} nến nguy cơ CAO** — coin có thể xả trong 24h!"
                        if _median_lead is not None:
                            _alert_msg += f" Lịch sử: tín hiệu cảnh báo trước ~{_median_lead/60:.1f}h."
                        st.error(_alert_msg)
                    elif med_risk:
                        st.warning(f"⚠️ {len(med_risk)} nến nguy cơ TRUNG BÌNH — theo dõi sát")
                    else:
                        st.success("✅ Không có tín hiệu nguy cơ. Thị trường bình thường.")

                    # === Predictions table + chart side by side ===
                    col_table, col_chart = st.columns([3, 2])

                    with col_table:
                        st.markdown("#### Dự đoán 12 nến mới nhất")
                        st.caption("Probability = xác suất coin phân phối trong 24h tới. Risk = phân loại dựa trên threshold. Hết hạn = khi tín hiệu hết giá trị (24h).")
                        pred_df = pd.DataFrame(predictions)
                        pred_df["probability"] = pred_df["probability"].apply(lambda x: f"{x:.1%}")
                        pred_df["close"] = pred_df["close"].apply(lambda x: f"{x:.6f}" if x else "N/A")
                        pred_df["feature_time"] = pred_df["feature_time"].str[:19]
                        if "invalidation_time" in pred_df.columns:
                            pred_df["invalidation_time"] = pred_df["invalidation_time"].str[:19]
                            pred_df = pred_df[["feature_time", "symbol", "close", "probability", "risk_level", "invalidation_time"]]
                            pred_df.columns = ["Thời gian", "Coin", "Giá close", "Probability", "Risk", "Hết hạn"]
                        else:
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

                    # === Price chart for scanned coin ===
                    st.markdown("---")
                    st.markdown(f"#### 📊 Biểu đồ giá {symbol}")

                    _scan_chart_col, _scan_tf_col = st.columns([3, 1])
                    with _scan_chart_col:
                        _scan_chart_type = st.radio(
                            "Loại chart",
                            ["🕯️ Nến", "📈 Đường", "📊 TradingView"],
                            horizontal=True,
                            key="scan_chart_type",
                        )
                    with _scan_tf_col:
                        _scan_tf = st.selectbox(
                            "Khung thời gian",
                            ["5m", "15m", "1h", "4h", "1d"],
                            index=2,
                            key="scan_chart_tf",
                        )

                    if _scan_chart_type == "📊 TradingView":
                        import streamlit.components.v1 as components
                        _tv_embed = f"""
                        <iframe
                            src="https://s.tradingview.com/widgetembed/?frameElementId=tv_scan&symbol=BINANCE%3A{symbol}&interval={_scan_tf}&hidesidetoolbar=false&symboledit=true&saveimage=false&toolbarbg=%231a1a2e&theme=dark&style=1&hideideas=true&locale=vi_VN"
                            style="width:100%;height:500px;border:0;margin:0;padding:0;"
                            allowfullscreen
                            allow="autoplay; clipboard-read; clipboard-write"
                        ></iframe>
                        """
                        components.html(_tv_embed, height=520)
                        st.caption("ℹ️ Nếu chart trắng — coin chưa có trên TradingView. Bấm ô symbol trên chart để đổi.")
                    else:
                        _scan_klines = _fetch_recent_klines(symbol, _scan_tf, 200)
                        if _scan_klines:
                            _skdf = pd.DataFrame(_scan_klines)
                            if _scan_chart_type == "🕯️ Nến":
                                import plotly.graph_objects as go
                                _sfig = go.Figure(data=[go.Candlestick(
                                    x=_skdf["time"],
                                    open=_skdf["open"],
                                    high=_skdf["high"],
                                    low=_skdf["low"],
                                    close=_skdf["close"],
                                    name=symbol,
                                )])
                                # Mark high-risk candles on chart (predictions)
                                if high_risk:
                                    _hr_times = [pd.to_datetime(p["feature_time"]) for p in high_risk]
                                    _hr_probs = [p["probability"] for p in high_risk]
                                    _sfig.add_trace(go.Scatter(
                                        x=_hr_times,
                                        y=[_skdf.loc[_skdf["time"] == t, "high"].values[0] if len(_skdf.loc[_skdf["time"] == t, "high"]) > 0 else None for t in _hr_times],
                                        mode="markers",
                                        marker=dict(symbol="triangle-down", size=14, color="red"),
                                        name="🚨 Dự đoán CAO",
                                        text=[f"Prob: {p:.1%}" for p in _hr_probs],
                                        hovertemplate="%{text}<br>%{x}<extra></extra>",
                                    ))
                                # Mark historical distribution events (actual labels)
                                if not _hist_dist.empty:
                                    _hd_times = [t for t in _hist_dist['feature_time'] if t in set(_skdf['time'])]
                                    _hd_y = [_skdf.loc[_skdf['time'] == t, 'low'].values[0] * 0.995 if len(_skdf.loc[_skdf['time'] == t, 'low']) > 0 else None for t in _hd_times]
                                    _sfig.add_trace(go.Scatter(
                                        x=_hd_times,
                                        y=_hd_y,
                                        mode="markers",
                                        marker=dict(symbol="diamond", size=10, color="orange", line=dict(width=1, color="white")),
                                        name="📉 Phân phối lịch sử",
                                        text=["Label: 1 (đã xả)"] * len(_hd_times),
                                        hovertemplate="%{text}<br>%{x}<extra></extra>",
                                    ))
                                _sfig.update_layout(
                                    template="plotly_dark",
                                    height=450,
                                    margin=dict(l=0, r=0, t=30, b=0),
                                    xaxis_rangeslider_visible=False,
                                    yaxis_title="Giá",
                                )
                                st.plotly_chart(_sfig, use_container_width=True, config={"displayModeBar": False})
                                st.caption("🔻 Tam giác đỏ = dự đoán CAO (sắp xả) | ◆ Cam = phân phối lịch sử (đã xả)")
                            else:  # Line
                                _sline_data = _skdf.set_index("time")[["close"]]
                                st.line_chart(_sline_data, use_container_width=True)
                        else:
                            st.warning(f"Không lấy được klines cho {symbol} ở khung {_scan_tf}")

                    # === Feature importance ===
                    top_feats = model_info.get("top_features", [])
                    if top_feats:
                        with st.expander("🔍 Top 5 feature quan trọng nhất", expanded=False):
                            st.caption("Hệ số dương = feature tăng → xác suất phân phối tăng. Hệ số âm = ngược lại.")
                            feat_df = pd.DataFrame(top_feats)
                            feat_df["coefficient"] = feat_df["coefficient"].apply(lambda x: f"{x:+.4f}")
                            feat_df.columns = ["Feature", "Hệ số"]
                            st.dataframe(feat_df, use_container_width=True, hide_index=True)

                    # === Baseline comparison (core: có lợi thế thống kê?) ===
                    st.markdown("---")
                    st.markdown("#### ⚖️ So sánh Model vs Baseline")
                    st.caption("Câu hỏi cốt lõi: model có vượt baseline đơn giản không? Không vượt → không triển khai.")

                    _train_pos = model_info.get("train_positives", 0)
                    _train_size = model_info.get("train_size", 1)
                    _prevalence = _train_pos / _train_size if _train_size > 0 else 0.0
                    _model_prec = model_metrics.get("precision", 0.0)
                    _model_recall = model_metrics.get("recall", 0.0)
                    _model_brier = model_metrics.get("brier", 0.0)
                    _thresh = model_metrics.get("threshold", 0.5)

                    # Prevalence baseline: predict all positive → precision = prevalence
                    _base_prec = _prevalence
                    _base_recall = 1.0 if _prevalence > 0 else 0.0
                    _base_brier = (_prevalence * (1 - _prevalence) ** 2 + (1 - _prevalence) * _prevalence ** 2) if _prevalence > 0 else 0.0

                    _cmp_c1, _cmp_c2, _cmp_c3 = st.columns(3)
                    with _cmp_c1:
                        st.metric("Precision", f"{_model_prec:.4f}", f"{_model_prec - _base_prec:+.4f} vs baseline", help=_glossary_tooltip("Precision"))
                    with _cmp_c2:
                        st.metric("Recall", f"{_model_recall:.4f}", f"{_model_recall - _base_recall:+.4f} vs baseline", help=_glossary_tooltip("Recall"))
                    with _cmp_c3:
                        st.metric("Brier Score", f"{_model_brier:.4f}", f"{_model_brier - _base_brier:+.4f} vs baseline", help=_glossary_tooltip("Brier Score"))

                    _cmp_df = pd.DataFrame([
                        {"Model": "LogReg (walk-forward)", "Precision": _model_prec, "Recall": _model_recall, "Brier": _model_brier},
                        {"Model": "Prevalence baseline", "Precision": _base_prec, "Recall": _base_recall, "Brier": _base_brier},
                    ])
                    st.dataframe(
                        _cmp_df.style.format({"Precision": "{:.4f}", "Recall": "{:.4f}", "Brier": "{:.4f}"}),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.bar_chart(_cmp_df.set_index("Model")[["Precision", "Recall"]])

                    if _model_prec > _base_prec and _model_prec > 0:
                        if _train_pos < 100:
                            st.warning(f"🟡 **TIẾP TỤC (thận trọng)** — model precision {_model_prec:.4f} > baseline {_base_prec:.4f}, nhưng chỉ {_train_pos} event phân phối. Cần thêm dữ liệu.")
                        else:
                            st.success(f"🟢 **CÓ LỢI THẾ THỐNG KÊ** — model precision {_model_prec:.4f} > baseline {_base_prec:.4f}. Tiếp tục kiểm chứng bằng Backtest + Forward Test.")
                    elif _model_prec > 0:
                        st.warning(f"🟡 **CHƯA VƯỢT BASELINE** — model precision {_model_prec:.4f} ≤ baseline {_base_prec:.4f}. Sửa giả thuyết hoặc thêm feature.")
                    else:
                        st.error("🔴 **KHÔNG HOẠT ĐỘNG** — model precision = 0. Kiểm tra dữ liệu/split/imbalance.")

                    st.caption(f"📌 Prevalence = {_prevalence:.4f} ({_train_pos}/{_train_size} event phân phối trong train) | Threshold = {_thresh:.2f}")

            db.conn.close()
        except Exception as e:
            status.error(f"❌ Lỗi: {str(e)}")
            progress.empty()


# ============================================================
# TAB 2: BACKTEST — đánh giá model trên lịch sử (walk-forward)
# ============================================================
with _backtest_container:
    st.caption("Chạy pipeline đầy đủ: thu thập → nhãn → feature → model → baseline → leakage audit. Kết luận: tiếp tục / sửa giả thuyết / dừng.")

    if run_bt:
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
                lt = results_data.get("lead_time_stats", {})

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

                # --- Lead time + invalidation ---
                if lt and lt.get("status") == "ok":
                    st.markdown("---")
                    st.markdown("##### ⏱️ Lead Time — cảnh báo trước bao lâu?")
                    st.caption("Lead time = thời gian từ tín hiệu phát đến khi phân phối thực sự xảy ra. Invalidation = khi tín hiệu hết hạn (24h).")
                    lc = st.columns(4)
                    lc[0].metric("Median lead time", f"{lt.get('median_minutes', 0):.0f} min", f"~{lt.get('median_hours', 0):.1f}h", help="Thời gian trung bình từ tín hiệu đến khi giá giảm ≥8%")
                    lc[1].metric("p25–p75", f"{lt.get('p25_minutes', 0):.0f}–{lt.get('p75_minutes', 0):.0f} min")
                    lc[2].metric("Range", f"{lt.get('min_minutes', 0):.0f}–{lt.get('max_minutes', 0):.0f} min")
                    lc[3].metric("Invalidation", f"{lt.get('horizon_minutes', 1440)} min", "24h horizon", help="Tín hiệu hết hạn sau 24h — nếu không xảy ra = false positive")
                    st.info(f"📊 {lt.get('summary', '')}")
                elif lt and lt.get("status") == "no_positive_labels":
                    st.markdown("---")
                    st.markdown("##### ⏱️ Lead Time")
                    st.warning("Không có event phân phối — không tính được lead time.")

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

    # Idle state for detect tab
    if not run_scan:
        st.markdown("""
        ### 🎯 Phát hiện Distribution

        **Mục tiêu tối cao:** Phát hiện sớm coin có xác suất cao chuyển từ tăng giá sang phân phối.

        **Cách dùng:**
        1. Chọn mã coin ở thanh bên (mặc định **BTCUSDT**)
        2. Chọn khoảng thời gian (mặc định 30 ngày)
        3. Bấm **"🔍 Phát hiện Distribution"** ở thanh bên

        App sẽ: thu thập dữ liệu → tính feature → train model → dự đoán probability trên 12 nến mới nhất → so sánh với baseline.
        """)


# ============================================================
# IDLE STATE — Backtest tab instructions
# ============================================================
with _backtest_container:
    if not run_bt:
        st.markdown("""
        ### 🧪 Backtest — Đánh giá model

        **Cách dùng:**
        1. Chọn mã coin + khoảng thời gian ở thanh bên
        2. Bấm **"🚀 Chạy Backtest"** ở thanh bên

        App sẽ chạy pipeline 5 bước: thu thập → chuẩn hóa → nhãn → feature → model.
        Kết quả: metrics, baseline comparison, data quality, leakage audit, conclusion.
        """)

    # ============================================================
    # FORWARD TEST — đóng băng model → chấm điểm trên dữ liệu mới
    # ============================================================
    st.markdown("---")
    st.markdown("### 🔒 Forward Test")
    st.caption(
        "Đóng băng model (lock code + config + threshold) → chấm điểm trên dữ liệu MỚI sinh ra SAU khi đóng băng. "
        "Kiểm tra stability thực tế trước khi dùng thật. Model không vượt baseline trong forward test → không triển khai."
    )

    from dao_vang.experiments.forward_test import (
        evaluate_frozen,
        freeze_model as _freeze_model,
        list_frozen_models as _list_frozen,
    )

    _ft_c1, _ft_c2 = st.columns(2)
    with _ft_c1:
        if st.button("🔒 Đóng băng model hiện tại", help="Train LogReg trên tất cả dữ liệu đã có nhãn, lock threshold, lưu model + metadata. Data sau train_cutoff = forward test data."):
            try:
                from sklearn.linear_model import LogisticRegression as _LR
                import numpy as _np

                _ft_db = DuckDBQueryLayer(db_path)
                _ft_df = _ft_db.conn.execute(
                    """
                    SELECT f.*, l.label_value AS is_distribution
                    FROM feature_results f
                    INNER JOIN labels l
                        ON f.feature_time = l.signal_time AND f.symbol = l.symbol
                    """
                ).df()
                _ft_db.conn.close()

                if _ft_df.empty or len(_ft_df) < 200:
                    st.warning("Cần ít nhất 200 dòng dữ liệu đã có nhãn. Chạy Backtest trước để build feature + labels.")
                elif _ft_df["is_distribution"].nunique() < 2:
                    st.warning("Cần cả 2 class (có/không phân phối) trong dữ liệu.")
                else:
                    _ft_df = _ft_df.sort_values("feature_time").reset_index(drop=True)
                    _ft_exclude = ["feature_time", "decision_time", "is_distribution", "quality_status", "symbol", "lead_time_minutes", "invalidation_time"]
                    _ft_feats = [c for c in _ft_df.columns if c not in _ft_exclude]

                    # Tune threshold on last 20%
                    _val_cut = _ft_df["feature_time"].quantile(0.8)
                    _tr = _ft_df[_ft_df["feature_time"] < _val_cut]
                    _va = _ft_df[_ft_df["feature_time"] >= _val_cut]
                    _m = _LR(max_iter=1000, random_state=42, class_weight="balanced")
                    _m.fit(_tr[_ft_feats].fillna(0), _tr["is_distribution"])

                    _best_t, _best_f1 = 0.5, 0.0
                    if len(_va) > 0 and _va["is_distribution"].nunique() >= 2:
                        _yp = _m.predict_proba(_va[_ft_feats].fillna(0))[:, 1]
                        _yv = _va["is_distribution"].values
                        for _t in _np.arange(0.05, 0.95, 0.05):
                            _yp_t = (_yp >= _t).astype(int)
                            _tp = int(((_yp_t == 1) & (_yv == 1)).sum())
                            _fp = int(((_yp_t == 1) & (_yv == 0)).sum())
                            _fn = int(((_yp_t == 0) & (_yv == 1)).sum())
                            if _tp + _fp == 0 or _tp + _fn == 0:
                                continue
                            _p = _tp / (_tp + _fp)
                            _r = _tp / (_tp + _fn)
                            _f1 = 2 * _p * _r / (_p + _r) if (_p + _r) > 0 else 0.0
                            if _f1 > _best_f1:
                                _best_f1 = _f1
                                _best_t = _t

                    # Retrain on ALL data
                    _final_m = _LR(max_iter=1000, random_state=42, class_weight="balanced")
                    _final_m.fit(_ft_df[_ft_feats].fillna(0), _ft_df["is_distribution"])

                    _info = _freeze_model(
                        model=_final_m,
                        threshold=float(_best_t),
                        feature_cols=_ft_feats,
                        config={"hypothesis_id": hypothesis_id, "dataset_version": "v1", "label_version": "v1", "feature_set_version": "v1", "seed": seed},
                        train_cutoff=_ft_df["feature_time"].max(),
                        training_stats={
                            "train_size": len(_ft_df),
                            "train_positives": int(_ft_df["is_distribution"].sum()),
                            "threshold": float(_best_t),
                            "n_features": len(_ft_feats),
                        },
                        artifact_dir=Path(artifact_dir),
                    )
                    st.success(f"✅ Model đã đóng băng: `{_info.model_id}`")
                    st.info(f"Train cutoff: {_info.train_cutoff[:19]} | Threshold: {_info.threshold:.4f} | Features: {len(_info.feature_cols)} | Train rows: {len(_ft_df)} ({int(_ft_df['is_distribution'].sum())}+)")
            except Exception as _e:
                st.error(f"❌ Lỗi đóng băng: {_e}")

    with _ft_c2:
        _frozen_models = _list_frozen(Path(artifact_dir))
        if not _frozen_models:
            st.info("Chưa có model nào đóng băng. Bấm **🔒 Đóng băng** để tạo.")
        else:
            st.markdown(f"**{len(_frozen_models)} model đã đóng băng:**")
            _fm_options = {f"{m.model_id}  (cutoff: {m.train_cutoff[:10]}, thresh: {m.threshold:.3f})": m.model_id for m in _frozen_models}
            _sel_fm = st.selectbox("Chọn model để đánh giá forward", options=list(_fm_options.keys()))
            _sel_id = _fm_options[_sel_fm]

            if st.button("📊 Chấm điểm forward test", type="primary"):
                try:
                    _ft_db2 = DuckDBQueryLayer(db_path)
                    _ft_df2 = _ft_db2.conn.execute(
                        """
                        SELECT f.*, l.label_value AS is_distribution
                        FROM feature_results f
                        INNER JOIN labels l
                            ON f.feature_time = l.signal_time AND f.symbol = l.symbol
                        """
                    ).df()
                    _ft_db2.conn.close()

                    _ft_result = evaluate_frozen(_sel_id, _ft_df2, artifact_dir=Path(artifact_dir))

                    if _ft_result["status"] != "ok":
                        st.warning(f"Không thể đánh giá: {_ft_result.get('message', _ft_result['status'])}")
                    else:
                        _ft_m = _ft_result["metrics"]
                        _ft_tm = _ft_result["training_metrics"]
                        _ft_drift = _ft_result["drift_check"]

                        st.markdown("#### Kết quả Forward Test")
                        _ftc1, _ftc2, _ftc3 = st.columns(3)
                        _ftc1.metric("Precision", f"{_ft_m['precision']:.4f}", f"{_ft_m['precision'] - _ft_tm['precision']:+.4f} vs train", help=_glossary_tooltip("Precision"))
                        _ftc2.metric("Recall", f"{_ft_m['recall']:.4f}", f"{_ft_m['recall'] - _ft_tm['recall']:+.4f} vs train", help=_glossary_tooltip("Recall"))
                        _ftc3.metric("Brier", f"{_ft_m['brier']:.4f}", help=_glossary_tooltip("Brier Score"))

                        st.info(f"📊 {_ft_result['summary']}")

                        # Drift alert
                        if _ft_drift["precision_drift"]:
                            st.error("🔴 **DRIFT detected** — precision thay đổi >0.1 so với training. Model có thể không còn ổn định.")
                        else:
                            st.success("✅ Không có drift đáng kể — model ổn định trong forward test.")

                        # Risk breakdown
                        _rb = _ft_result["risk_breakdown"]
                        if _rb:
                            st.markdown("##### Phân tích theo Risk Level")
                            _rb_rows = []
                            for _lvl in ["CAO", "TRUNG BÌNH", "THẤP", "RẤT THẤP"]:
                                _d = _rb.get(_lvl, {})
                                _rb_rows.append({
                                    "Risk": _lvl,
                                    "Số tín hiệu": _d.get("n_signals", 0),
                                    "Thực xả": _d.get("n_actual_distribution", 0),
                                    "Precision": f"{_d.get('precision', 0):.4f}",
                                })
                            st.dataframe(pd.DataFrame(_rb_rows), use_container_width=True, hide_index=True)

                        st.caption(f"Forward rows: {_ft_result['n_forward_rows']} | Actual distributions: {_ft_result['n_positive_labels']} | Predicted positive: {_ft_result['n_predicted_positive']}")
                except Exception as _e:
                    st.error(f"❌ Lỗi forward test: {_e}")

# ============================================================
# TAB 4: THUẬT NGỮ (Glossary)
# ============================================================
with _glossary_container:
    _render_glossary_tab()


# ============================================================
# TAB 5: HƯỚNG DẪN (Guide)
# ============================================================
with _guide_container:
    _render_guide_tab()
