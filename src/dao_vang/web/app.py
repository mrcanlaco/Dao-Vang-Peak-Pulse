import json as _json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from dao_vang.config.settings import AppSettings
from dao_vang.data.binance_listing import (
    DEFAULT_HISTORY_PATH as _LISTING_HISTORY_PATH,
)
from dao_vang.data.binance_listing import (
    get_stats_for_today as _get_listing_snapshot,
)
from dao_vang.data.binance_listing import (
    is_today as _listing_is_today,
)
from dao_vang.data.binance_listing import (
    load_history as _load_listing_history,
)
from dao_vang.data.binance_listing import (
    run_daily_scan as _run_listing_scan,
)
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.funding import FundingCollector
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.collectors.open_interest import OpenInterestCollector
from dao_vang.data.collectors.ratios import GlobalRatioCollector, TopRatioCollector
from dao_vang.data.collectors.taker import TakerRatioCollector
from dao_vang.data.pipeline import (
    build_raw_timeline,
    get_incremental_start,
    process_raw_to_parquet,
    scan_downloaded_data,
)
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.domain.time import SYSTEM_TIMEZONE, as_system_timezone, system_now
from dao_vang.experiments.artifacts import ArtifactRegistry
from dao_vang.experiments.runner import ExperimentConfig, run_experiment
from dao_vang.features.builder import build_features
from dao_vang.labels.engine import DistributionLabelEngine
from dao_vang.logging import get_logger
from dao_vang.reports.generator import generate_markdown_report

logger = get_logger(__name__)


def _display_datetime(value: datetime | None, fmt: str) -> str:
    if value is None:
        return "—"
    return as_system_timezone(value).strftime(fmt)


st.set_page_config(
    page_title="Đảo Vàng",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============================================================
# GLOSSARY — giải nghĩa thuật ngữ (từ GLOSSARY.md)
# ============================================================
GLOSSARY = {
    "Distribution": "Coin bắt đầu 'xả' — mất động lượng tăng, sắp giảm mạnh. Không phải đoán bằng mắt, mà do AI tính từ dữ liệu.",
    "Phân phối": "Distribution — coin bắt đầu xả. Label=1 nghĩa là trong 24h tới, giá giảm ≥8% và không tăng quá 4% trước khi giảm.",
    "Precision": "Độ chính xác — trong 100 lần AI báo 'sắp xả', bao nhiêu lần đúng? Cao = ít báo sai. VD: Precision 35% = 35/100 lần báo là đúng thật.",
    "Recall": "Tỷ lệ bắt được — trong 100 lần coin THẬT SỰ xả, AI bắt được bao nhiêu? Cao = ít bỏ sót. VD: Recall 90% = bắt được 90/100 sự kiện thật.",
    "Brier Score": "Độ chuẩn xác — AI báo 70% thì thật sự ~70% chứ không phải 30%? Số càng THẤP càng tốt (0 = hoàn hảo, 1 = sai hoàn toàn).",
    "Threshold": "Ngưỡng cảnh báo — AI báo xác suất bao nhiêu thì mới phát cảnh báo? Thấp = báo nhiều nhưng sai nhiều; cao = chính xác nhưng bỏ sót.",
    "Baseline": "Mốc so sánh đơn giản — VD: 'luôn luôn báo sắp xả' hoặc 'giá giảm thì báo'. AI phải GIỎI HƠN cái này mới đáng dùng.",
    "Walk-Forward": "Kiểm tra theo thời gian — train trên quá khứ, test trên tương lai. Không trộn lẫn dữ liệu → đảm bảo không 'nhìn trộm' tương lai.",
    "Leakage": "Rò rỉ dữ liệu — AI vô tình dùng thông tin tương lai để dự đoán. Như coi trước đáp án thi → điểm cao giả tạo. Phải FAIL nếu phát hiện.",
    "Label": "Kết quả thật — coin có thật sự xả trong 24h sau đó không? Chỉ dùng để chấm điểm AI, KHÔNG cho AI biết trước.",
    "Feature Time": "Thời điểm dự đoán — timestamp của nến 5 phút đã đóng.",
    "Signal Price": "Giá tại thời điểm dự đoán — giá close của nến 5 phút.",
    "Horizon": "Khung thời gian dự báo — 24 giờ tới. Sau 24h, nếu coin không xả thì cảnh báo hết giá trị.",
    "Target Drawdown": "Mức giảm mục tiêu — coin phải giảm ít nhất 8% trong 24h mới tính là 'xả'.",
    "MAE": "Biên tăng tối đa — trước khi giảm 8%, coin được phép tăng tối đa 4%. Tăng quá 4% rồi mới giảm = không tính (báo sai).",
    "Probability": "Xác suất xả — AI tính % cơ hội coin sẽ xả trong 24h tới. VD: 65% = khá nguy.",
    "Risk Level": "Mức nguy cơ — CAO (≥1.5×ngưỡng), TRUNG BÌNH (≥ngưỡng), THẤP (≥0.5×ngưỡng), RẤT THẤP (<0.5×ngưỡng).",
    "Prevalence": "Tần suất sự kiện — bao nhiêu % thời gian coin THẬT SỰ xả? VD: 5% = 5/100 nến có xả thật. Thấp = hiếm → AI khó học.",
    "Embargo": "Khoảng cách 12h giữa train và test — tránh 'nhìn trộm' dữ liệu chồng lấp do horizon 24h.",
    "Open Interest (OI)": "Tổng hợp đồng futures đang mở. OI tăng + giá giảm = phe short vào mạnh → dấu hiệu xả.",
    "Funding Rate": "Lãi suất 8h mà long trả short (hoặc ngược). Funding âm = short trả long = thị trường quá bán.",
    "Taker Buy/Sell Ratio": "Tỷ lệ volume mua/bán chủ động. >1 = mua mạnh, <1 = bán mạnh (đang xả).",
    "Long/Short Ratio": "Tỷ lệ tài khoản long/short. Cao = nhiều long = nguy cơ bóp ngắn ngược.",
    "Calibration": "Độ tin cậy — AI báo 70% thì tần suất thật ~70%. Nhóm 'AI báo 80-90%' phải xảy ra ~80-90% thật.",
    "Forward Test": "Đóng băng AI → chờ dữ liệu mới sinh ra → chấm điểm. Kiểm tra AI có hoạt động ngoài phòng lab không.",
    "Point-in-Time": "Mọi dữ liệu tại thời điểm T phải THẬT SỰ biết được tại/sau T. Vi phạm = rò rỉ.",
    "Artifact": "Bản ghi bất biến của 1 lần thử: cấu hình, kết quả, dự đoán. Có version + hash để truy vết.",
    "Feature Importance": "Yếu tố ảnh hưởng — AI dựa vào cái gì để quyết định? Hệ số dương = yếu tố này tăng → xác suất xả tăng.",
    # === Bổ sung: Trading jargon ===
    "Short": "Bán khống — đặt cược giá sẽ GIẢM. Mua lại sau khi giá giảm → ăn chênh lệch.",
    "Long": "Mua — đặt cược giá sẽ TĂNG. Bán sau khi giá tăng → ăn chênh lệch.",
    "Pump": "Tăng giá nhanh và mạnh (VD: +100% trong 1-5 ngày). Thường do nhóm thao túng hoặc FOMO.",
    "Dump": "Xả giá mạnh sau pump. 'Pump hard → dump hard' — coin pump càng mạnh, xả càng đau.",
    "FOMO": "Sợ bỏ lỡ — tâm lý thấy coin tăng thì mua theo vì sợ错过 cơ hội. FOMO đẩy giá lên cao rồi xả.",
    "Squeeze": "Bóp ngắn — phe bị ép đóng vị thế ngược chiều khi giá đi mạnh. Long squeeze = long bị ép đóng → giá giảm thêm.",
    "Oversold": "Quá bán — thị trường bán quá nhiều, giá giảm quá mức → có thể hồi phục.",
    "Spot": "Giao ngay — mua bán coin thật, không dùng đòn bẩy.",
    "Futures": "Hợp đồng tương lai — giao dịch có đòn bẩy, có thể long/short.",
    "USD-M": "Ký quỹ bằng USDT — futures tính lãi/lỗ bằng USD.",
    "COIN-M": "Ký quỹ bằng coin gốc — futures tính lãi/lỗ bằng coin (VD: BTC).",
    "Margin": "Ký quỹ — tiền đặt cọc để mở vị thế đòn bẩy.",
    "Candlestick": "Biểu đồ nến — mỗi nến thể hiện giá mở/đóng/cao/thấp trong 1 khoảng thời gian.",
    "Ticker": "Bảng giá thời gian thực — giá + khối lượng + thay đổi 24h.",
    "Watchlist": "Danh sách theo dõi — các coin bạn quan tâm, được lưu để quét định kỳ.",
    "Scanner": "Bộ quét tự động — chạy 24/7, quét thị trường và gửi cảnh báo qua Telegram.",
    "Hit rate": "Tỷ lệ trúng — trong các cảnh báo đã ra, bao nhiêu % đúng (coin thật sự xả).",
    "Signal": "Tín hiệu — cảnh báo từ AI rằng coin có thể xả trong 24h tới.",
    "Invalidation time": "Thời gian hết hạn — sau 24h, nếu coin không xả thì cảnh báo không còn giá trị.",
    "Lead time": "Thời gian cảnh báo trước — AI báo trước bao lâu trước khi coin thật sự xả. Càng sớm càng tốt.",
    # === Bổ sung: ML/Stats jargon ===
    "Drift": "Sự trôi dịch — performance của AI thay đổi theo thời gian. VD: precision giảm từ 40% → 25% = drift.",
    "Frozen Model": "Model đóng băng — AI đã khóa code + config + ngưỡng, không thay đổi nữa. Dùng cho production.",
    "Train cutoff": "Mốc thời gian cắt — data TRƯỚC cutoff dùng train, data SAU cutoff dùng forward test.",
    "Fold": "Lần kiểm tra — mỗi lần huấn luyện/kiểm tra trong kiểm tra theo thời gian. VD: 5 lần = 5 lần huấn luyện quá khứ + kiểm tra tương lai.",
    "Train": "Huấn luyện — dạy AI từ dữ liệu lịch sử để học pattern.",
    "Test": "Kiểm tra — đánh giá AI trên dữ liệu mới (không dùng để train).",
    "Feature": "Đặc trưng — thông tin AI dùng để dự đoán (VD: funding rate, volume, OI change).",
    "Pipeline": "Quy trình — chuỗi các bước: thu thập → chuẩn hóa → gán nhãn → tính đặc trưng → huấn luyện AI.",
    "Confidence interval": "Khoảng tin cậy — phạm vi giá trị có khả năng đúng. VD: precision 35% ±5% = nằm trong 30-40%.",
    "False alarm": "Cảnh báo sai — AI báo sẽ xả nhưng coin không xả. Càng ít càng tốt.",
    "Seed": "Hạt giống ngẫu nhiên — số cố định để tái hiện kết quả. Cùng seed = cùng kết quả.",
    # === Bổ sung: Scoring system ===
    "Composite Score": "Tổng điểm 0-100 — chấm điểm coin dựa trên 8 tín hiệu. ≥70 = ứng viên bán.",
    "Price-Volume Divergence": "Phân kỳ giá-khối lượng — giá tăng nhưng volume giảm → pump giả, không có nhu cầu thật.",
    "Funding Spike": "Funding tăng vọt — lãi suất funding tăng đột biến (z-score cao) → long đang trả nhiều tiền, sắp unwind.",
    "Momentum Exhaustion": "Động lượng cạn kiệt — tốc độ tăng giá giảm dần → pump đang yếu đi.",
    "Distance From High": "Khoảng cách từ đỉnh — giá hiện tại cách đỉnh 24h bao xa. Gần đỉnh = R:R tốt cho short.",
    "Taker Sell Pressure": "Áp lực bán chủ động — phe bán chủ động mạnh hơn phe mua → đang xả.",
    "OI Divergence": "Phân kỳ OI — giá tăng nhưng Open Interest giảm → phe đang rút lui, pump không bền.",
    "BTC Context": "Bối cảnh BTC — BTC đang FOMO/NEUTRAL/WEAK. Ảnh hưởng toàn thị trường altcoin.",
    "Fake Breakout": "Phá vỡ giả (bull trap) — nến phá trên đỉnh gần nhất rồi đóng cửa lại bên dưới → dụ FOMO mua rồi xả. Tín hiệu strong-short.",
    "SHORT_CANDIDATE": "Ứng viên bán — điểm ≥70, có thể cân nhắc vị thế short.",
    "WATCH": "Theo dõi — điểm 50-70, chưa đủ cao để hành động nhưng cần để ý.",
    "WAIT": "Chờ — điểm <50, chưa có dấu hiệu xả rõ ràng.",
    # === Bổ sung: Recommendation ===
    "Recommendation": "Khuyến nghị — SHORT_CANDIDATE (điểm ≥70), WATCH (50-70), WAIT (<50).",
}


def _glossary_tooltip(term: str) -> str:
    """Return glossary explanation for a term, or empty string if not found."""
    return GLOSSARY.get(term, "")


def _render_glossary_tab(key_prefix: str = "glossary"):
    """Render a glossary tab with searchable term explanations.

    Args:
        key_prefix: Unique prefix for widget keys (avoids duplicate key
            errors when rendered multiple times in the same run).
    """
    st.markdown("#### 📖 Từ điển thuật ngữ")
    st.caption("Nguồn: GLOSSARY.md — bấm vào từng mục để xem giải thích đầy đủ")

    search = st.text_input(
        "🔍 Tìm thuật ngữ",
        placeholder="VD: precision, distribution, MAE...",
        key=f"{key_prefix}_search",
    )

    items = list(GLOSSARY.items())
    if search:
        search_lower = search.lower()
        items = [(k, v) for k, v in items if search_lower in k.lower() or search_lower in v.lower()]

    for term, explanation in items:
        with st.expander(f"**{term}**", expanded=False):
            st.markdown(explanation)


def _render_guide_tab(key_prefix: str = "guide"):
    """Render hướng dẫn dùng tool (web app) và CLI.

    Args:
        key_prefix: Unique prefix for widget keys.
    """
    st.markdown("#### 🧭 Hướng dẫn sử dụng tool & ứng dụng")
    st.caption("Tổng hợp cách dùng giao diện web và CLI để thu thập dữ liệu, quét tín hiệu, chạy backtest và xuất báo cáo.")

    guide_search = st.text_input(
        "🔍 Tìm trong hướng dẫn",
        placeholder="VD: backtest, CLI, watchlist, collect...",
        key=f"{key_prefix}_search",
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
| 1 | 🎯 **Phát hiện xả** | Tính xác suất + mức nguy cơ + so sánh mốc cho BTCUSDT | **Core** |
| 2 | 🧪 **Backtest** | Đánh giá AI trên lịch sử (kiểm tra theo thời gian, rò rỉ, độ tin cậy) | Kiểm chứng |
| 3 | 📖 **Thuật ngữ** | Tra cứu khái niệm (precision, MAE, funding...) | Reference |
| 4 | 🧭 **Hướng dẫn** | (Tab này) Hướng dẫn dùng web + CLI | Reference |
| 5 | 📊 **Quan sát thị trường** | Coin tăng/giảm mạnh, danh sách theo dõi | Phụ |

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
        with st.expander("🎯 2. Tab Phát hiện xả — tính năng chính", expanded=False):
            st.markdown(
                """
**Đây là tab ưu tiên #1** — trả lời câu hỏi cốt lõi: *dữ liệu tối thiểu có tạo lợi thế thống kê trong phát hiện Distribution không?*

**Quy trình:**
1. Chọn mã coin ở thanh bên (mặc định **BTCUSDT**).
2. Chọn khoảng thời gian (mặc định 30 ngày).
3. Bấm **"🔍 Phát hiện xả"**.
4. App tự thu thập klines/funding/OI/taker ratios từ Binance → build feature → train LogReg → dự đoán 12 nến mới nhất.

**Quy tắc gán nhãn (v0.1):** khung dự báo 24h, mức giảm mục tiêu ≥8%, biên tăng tối đa ≤4%.

**Kết quả hiển thị:**
- **Probability + Risk Level** cho 12 nến mới nhất:
  - 🔴 **CAO**: xác suất ≥ 1.5×ngưỡng
  - 🟠 **TRUNG BÌNH**: xác suất ≥ ngưỡng
  - 🟡 **THẤP**: xác suất ≥ 0.5×ngưỡng
  - ⚪ **RẤT THẤP**: xác suất < 0.5×ngưỡng
- **Chart giá** + **Probability theo thời gian**.
- **Top 5 đặc trưng quan trọng** (AI dựa vào yếu tố nào).
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
| 📈 Kết quả | Độ chính xác / Tỷ lệ bắt được / Độ chuẩn xác / các lần kiểm tra |
| 📊 Mốc so sánh | So sánh AI với mốc đơn giản — AI phải vượt mốc mới triển khai |
| 🏷️ Nhãn | Phân phối nhãn, tần suất sự kiện, quy tắc gán nhãn |
| 🔍 Chất lượng | Kiểm tra rò rỉ, độ tin cậy, khoảng cách |
| 📄 Báo cáo | Báo cáo Markdown của thử nghiệm |
| 📖 Thuật ngữ | Tra cứu thuật ngữ |

**Lưu ý:** backtest dùng **kiểm tra theo thời gian** (không trộn dữ liệu) + **khoảng cách 12h** giữa huấn luyện/kiểm tra để tránh nhìn trộm tương lai.
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

1. **Phát hiện** (web → tab #1 Phát hiện xả): xem xác suất + mức nguy cơ + so sánh mốc hằng ngày.
2. **Đánh giá định kỳ** (web → tab #2 Backtest hoặc CLI `experiment run`):
   - Chạy kiểm tra theo thời gian trên dữ liệu mới.
   - So sánh với mốc — nếu không vượt → sửa giả thuyết / thêm đặc trưng / thu thập thêm dữ liệu.
   - Kiểm tra calibration & leakage.
3. **Xuất báo cáo** (CLI `report generate` hoặc web sub-tab 📄 Báo cáo) để lưu vết thử nghiệm.
4. **Forward test (kiểm tra tiến lên)**: áp dụng AI đã đóng băng lên dữ liệu mới sinh ra *sau* khi đóng băng — kiểm tra độ ổn định thực tế trước khi dùng thật.
5. **Quan sát thị trường** (web → tab #5, phụ): tham khảo coin tăng/giảm mạnh khi cần mở rộng sang coin khác.

**Quy tắc cốt lõi:** không bao giờ dùng nhãn làm đặc trưng; mọi đặc trưng phải đúng thời điểm; AI không vượt mốc so sánh thì không triển khai.
"""
            )

    # ---------- 6. TROUBLESHOOTING ----------
    if _match("lỗi error troubleshooting binance api duckdb không có dữ liệu"):
        with st.expander("🛠️ 6. Xử lý lỗi thường gặp", expanded=False):
            st.markdown(
                """
- **Phát hiện xả không có kết quả**: đảm bảo có đủ dữ liệu 30 ngày cho BTCUSDT. Nếu chưa có, app sẽ tự tải khi bấm chạy.
- **AI độ chính xác = 0**: quá ít sự kiện phân phối trong dữ liệu — mở rộng khoảng thời gian.
- **Không vượt mốc**: đặc trưng hiện tại chưa đủ — thử thêm đặc trưng hoặc kiểm tra trôi dịch.
- **Backtest fail leakage check**: feature đang dùng thông tin tương lai — rà `feature_set_version` và đảm bảo feature chỉ dùng dữ liệu ≤ feature time.
- **CLI `dao-vang: command not found`**: chạy `pip install -e .` hoặc `uv sync` rồi `uv run dao-vang --help`.
- **DuckDB file lock**: đảm bảo không có process khác đang mở cùng file `*.duckdb`.
- **Calibration lệch nhiều**: tăng lượng dữ liệu train hoặc kiểm tra drift trên window mới.
"""
            )

# --- CSS for compact UI + ticker marquee + mobile optimization ---
st.markdown("""
<style>
    /* ===== GLOBAL COMPACT ===== */
    .stMetric { padding: 2px 0 !important; }
    .stMetric > div > div { gap: 1px !important; }
    .stMetric [data-testid="stMetricLabel"] { font-size: 13px !important; }
    .stMetric [data-testid="stMetricValue"] { font-size: 20px !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 2px; overflow-x: auto; flex-wrap: nowrap; }
    .stTabs [data-baseweb="tab"] { padding: 6px 10px; font-size: 13px; white-space: nowrap; }
    .stAlert { padding: 6px 10px !important; margin-top: 4px !important; margin-bottom: 4px !important; }
    div[data-testid="stSidebar"] { width: 280px !important; }
    div[data-testid="stSidebar"] > div { padding-top: 0.5rem; }

    /* Reduce block/element spacing */
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
    .stMarkdown { margin-bottom: 0 !important; }
    h1 { margin-top: 0 !important; padding-top: 0 !important; font-size: 1.6rem !important; }
    h2 { font-size: 1.3rem !important; margin-top: 0.3rem !important; }
    h3 { font-size: 1.1rem !important; margin-top: 0.3rem !important; }
    h4 { font-size: 1rem !important; margin-top: 0.2rem !important; }
    hr { margin: 6px 0 !important; }
    .stCaption { margin-top: 0 !important; margin-bottom: 2px !important; }

    /* Compact info/alerts (BTC context banner) */
    .stAlert > div { padding: 6px 10px !important; }
    .stAlert [data-testid="stMarkdownContainer"] p { margin: 0 !important; line-height: 1.3 !important; }

    /* Reduce expander padding */
    .streamlit-expanderHeader { padding: 6px 10px !important; font-size: 14px !important; }
    .streamlit-expanderContent { padding: 6px 10px !important; }

    /* Ticker marquee */
    .dv-ticker {
        overflow: hidden;
        white-space: nowrap;
        background: #1a1a2e;
        border-radius: 6px;
        padding: 5px 0;
        margin-bottom: 6px;
    }
    .dv-ticker-track {
        display: inline-block;
        animation: dv-scroll 60s linear infinite;
    }
    .dv-ticker-item {
        display: inline-block;
        padding: 0 12px;
        font-size: 13px;
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
        font-size: 12px;
        padding: 4px 2px;
        text-align: center;
        white-space: pre-line;
        line-height: 1.2;
    }

    /* ===== MOBILE RESPONSIVE (≤768px) ===== */
    @media (max-width: 768px) {
        /* Main container: tighter padding */
        .block-container {
            padding-left: 0.5rem !important;
            padding-right: 0.5rem !important;
            padding-top: 0.5rem !important;
            max-width: 100% !important;
        }

        /* Title smaller on mobile */
        h1 { font-size: 1.3rem !important; margin-bottom: 0 !important; }
        h2 { font-size: 1.1rem !important; }
        h3 { font-size: 1rem !important; }
        h4 { font-size: 0.9rem !important; }

        /* Sidebar: narrower on mobile */
        div[data-testid="stSidebar"] { width: 240px !important; }
        div[data-testid="stSidebar"] > div { padding: 0.5rem 0.5rem !important; }

        /* Metrics: more compact */
        .stMetric [data-testid="stMetricLabel"] { font-size: 11px !important; }
        .stMetric [data-testid="stMetricValue"] { font-size: 16px !important; }
        .stMetric [data-testid="stMetricDelta"] { font-size: 10px !important; }

        /* Tabs: scrollable, smaller text */
        .stTabs [data-baseweb="tab-list"] {
            gap: 1px;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
        }
        .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; }
        .stTabs [data-baseweb="tab"] {
            padding: 5px 8px;
            font-size: 12px;
            min-width: fit-content;
        }

        /* Columns: let Streamlit stack but force smaller gaps */
        [data-testid="column"] { padding: 0 2px !important; }
        .stHorizontalBlock { gap: 4px !important; flex-wrap: wrap; }

        /* Tables: horizontal scroll */
        .stDataFrame { overflow-x: auto !important; }
        .stDataFrame table { font-size: 12px !important; }

        /* Buttons: card-style, left-aligned text on mobile */
        .stButton > button {
            font-size: 13px !important;
            padding: 8px 10px !important;
            border-radius: 8px !important;
            justify-content: flex-start !important;
            text-align: left !important;
            min-height: 40px !important;
            margin-bottom: 4px !important;
        }

        /* Top-gainer grid buttons stay centered/small (override above) */
        .stButton > button[kind="secondary"] {
            justify-content: center !important;
            text-align: center !important;
            padding: 4px 2px !important;
            font-size: 11px !important;
            min-height: auto !important;
        }

        /* Ticker: hide on mobile to reduce visual noise */
        .dv-ticker { display: none !important; }

        /* Header: keep title and refresh inline, very compact */
        [data-testid="stHorizontalBlock"]:has(h1) { flex-wrap: nowrap !important; align-items: center !important; }
        [data-testid="stHorizontalBlock"]:has(h1) [data-testid="column"] { flex: 1 1 auto !important; min-width: 0 !important; }
        [data-testid="stHorizontalBlock"]:has(h1) [data-testid="column"]:last-child { flex: 0 0 auto !important; max-width: 48px !important; }
        [data-testid="stHorizontalBlock"]:has(h1) [data-testid="column"]:last-child button { padding: 4px 8px !important; min-width: 40px !important; }

        /* Reduce whitespace between elements */
        .element-container { margin-bottom: 4px !important; }
        .stMarkdown + .stButton { margin-top: -2px !important; }

        /* Focused coin report: back button inline with title */
        [data-testid="stHorizontalBlock"]:has(h2) { flex-wrap: nowrap !important; align-items: center !important; }

        /* Focused score card smaller on mobile */
        div[style*="background:#ff"][style*="text-align:center"] h1 { font-size: 1.8rem !important; }
        div[style*="background:#ff"][style*="text-align:center"] p { font-size: 0.95rem !important; }

        /* Compact info/alerts */
        .stAlert { padding: 6px 8px !important; margin: 4px 0 !important; }

        /* Expander */
        .streamlit-expanderHeader { font-size: 13px !important; padding: 4px 8px !important; }

        /* Selectbox / inputs */
        .stSelectbox, .stTextInput { margin-bottom: 4px !important; }

        /* Caption smaller */
        .stCaption p { font-size: 11px !important; }

        /* Progress bar */
        .stProgress { margin: 4px 0 !important; }

        /* Remove extra gap after st.columns on mobile */
        .stHorizontalBlock + .stHorizontalBlock { margin-top: 0 !important; }
    }

    /* ===== SMALL MOBILE (≤480px) ===== */
    @media (max-width: 480px) {
        .block-container {
            padding-left: 0.3rem !important;
            padding-right: 0.3rem !important;
            padding-top: 0.3rem !important;
        }
        h1 { font-size: 1.1rem !important; }
        .stMetric [data-testid="stMetricValue"] { font-size: 14px !important; }
        .stTabs [data-baseweb="tab"] { padding: 4px 6px; font-size: 11px; }
        .dv-ticker { display: none !important; }
        .stDataFrame table { font-size: 11px !important; }
        .stAlert { padding: 5px 6px !important; }
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


def _get_listing_stats() -> dict:
    """Get today's listing snapshot.

    Logic: only fetch from Binance once per UTC+7 day. If today's snapshot is
    already persisted to ``data/binance_listing_history.json`` → return it
    (no API call). Otherwise fetch, persist, and return. The 🔄 Listing button
    forces a fresh scan for today.

    Returns the snapshot dict (may be empty on first run + API failure).
    """
    cache = st.session_state.get("_listing_stats_cache")
    if cache and _listing_is_today(cache) and not st.session_state.get("_listing_force"):
        return cache

    force = st.session_state.get("_listing_force", False)
    if force:
        snapshot = _run_listing_scan(_LISTING_HISTORY_PATH)
        st.session_state._listing_force = False
    else:
        snapshot = _get_listing_snapshot(_LISTING_HISTORY_PATH, auto_scan=True)

    if snapshot:
        st.session_state._listing_stats_cache = snapshot
    return snapshot or cache or {}


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
                "time": as_system_timezone(
                    datetime.fromtimestamp(k[0] / 1000, tz=timezone.utc)
                ),
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
if "rank_goto_coin" not in st.session_state:
    st.session_state.rank_goto_coin = None
if "rank_step" not in st.session_state:
    st.session_state.rank_step = None
if "active_tab" not in st.session_state:
    st.session_state.active_tab = "🏆 Xếp Hạng"
if "focus_coin" not in st.session_state:
    st.session_state.focus_coin = None
if "focus_mode" not in st.session_state:
    st.session_state.focus_mode = False
if "focus_run_scan" not in st.session_state:
    st.session_state.focus_run_scan = False


# --- Fetch tickers once (cached in session state) ---
if "_tickers_cache" not in st.session_state:
    st.session_state._tickers_cache = _fetch_24h_tickers()
_tickers = st.session_state._tickers_cache


# --- Header ---
_hdr_col1, _hdr_col2 = st.columns([6, 1])
with _hdr_col1:
    st.markdown("# 🪙 Đảo Vàng")
    st.caption("Phát hiện coin sắp xả — cảnh báo trước 24h")
with _hdr_col2:
    if st.button("🔄", help="Làm mới ticker", use_container_width=True):
        st.session_state._tickers_cache = _fetch_24h_tickers()
        st.rerun()

# Ticker marquee (hidden in focused coin view to reduce distraction)
if not st.session_state.get("focus_mode", False):
    _render_ticker_marquee(_tickers, top_n=20)


# ============================================================
# MODE SELECTOR — Cảnh báo (trader) vs Nghiên cứu (QA)
# ============================================================
if "app_mode" not in st.session_state:
    st.session_state.app_mode = "Cảnh báo"

_focus_coin = st.session_state.get("focus_coin")
_focus_mode = st.session_state.get("focus_mode", False)

with st.sidebar:
    if _focus_mode and _focus_coin:
        st.markdown("## 🎯 Báo cáo coin")
        st.caption(f"Đang xem: **{_focus_coin}**")
        st.markdown("---")
        _app_mode = st.session_state.app_mode
    else:
        st.markdown("## 🪙 Đảo Vàng")
        st.caption("Phát hiện xả phân phối")
        st.markdown("---")

        st.session_state.app_mode = st.radio(
            "Chế độ sử dụng",
            options=["🚨 Cảnh báo", "🔬 Nghiên cứu"],
            key="mode_selector",
            help="Cảnh báo: bảng xếp hạng + cảnh báo + phân tích coin (trader). Nghiên cứu: quét + backtest + forward test (QA).",
        )
        _app_mode = st.session_state.app_mode
        st.markdown("---")


# ============================================================
# MAIN TABS — radio-based navigation for programmatic switching
# ============================================================
if _app_mode == "🚨 Cảnh báo":
    _tab_labels = ["🏆 Xếp Hạng", "🚨 Cảnh báo", "🎯 Phân tích", "❓ Trợ giúp"]
else:
    _tab_labels = ["🔍 Quét coin", "🧪 Backtest", "⚡ Forward", "❓ Trợ giúp"]

if st.session_state.active_tab not in _tab_labels:
    st.session_state.active_tab = _tab_labels[0]

_active_tab = st.radio(
    "Tab",
    _tab_labels,
    index=_tab_labels.index(st.session_state.active_tab),
    horizontal=True,
    label_visibility="collapsed",
)
st.session_state.active_tab = _active_tab

# Containers for each tab (only active one renders content)
if _app_mode == "🚨 Cảnh báo":
    _ranking_container = st.container()
    _alerts_container = st.container()
    _detect_container = st.container()
    _help_container = st.container()
    # Hidden containers (collapsed expanders — not visible by default)
    _scan_container = st.expander("⠀", expanded=False)
    _backtest_container = st.expander("⠀", expanded=False)
    _market_container = _ranking_container  # market merged into ranking tab
    _glossary_container = st.expander("⠀", expanded=False)
    _guide_container = st.expander("⠀", expanded=False)
else:
    # 🔬 Nghiên cứu
    _scan_container = st.container()
    _backtest_container = st.container()
    _detect_container = st.container()
    _help_container = st.container()
    # Hidden containers (collapsed expanders)
    _ranking_container = st.expander("⠀", expanded=False)
    _alerts_container = st.expander("⠀", expanded=False)
    _market_container = st.expander("⠀", expanded=False)
    _glossary_container = st.expander("⠀", expanded=False)
    _guide_container = st.expander("⠀", expanded=False)


# ============================================================
# TAB: ALERT INBOX — 24/7 scanner alerts + deep-dive (ADR 0001)
# ============================================================
with _alerts_container:
    from dao_vang.alerts.store import AlertStore
    from dao_vang.config.settings import AppSettings as _AlertSettings

    _alert_settings = _AlertSettings()
    _alert_store = AlertStore(str(_alert_settings.scanner.db_path))

    st.markdown("#### 🚨 Cảnh báo — tín hiệu từ bộ quét 24/7")
    st.caption(
        "Bộ quét chạy 24/7, quét coin tăng mạnh + danh sách theo dõi, gửi Telegram khi phát hiện xả. "
        "Tab này để bạn xem lại + kiểm tra kỹ trước khi vào lệnh."
    )

    # --- Stats summary ---
    _alert_stats = _alert_store.stats(days=7)
    _as1, _as2, _as3 = st.columns(3)
    _as1.metric("Tín hiệu (7d)", _alert_stats["total"])
    _as2.metric("🚨 CAO", _alert_stats["by_risk"].get("CAO", 0))
    _as3.metric("⚠️ TB", _alert_stats["by_risk"].get("TRUNG BÌNH", 0))
    _as4, _as5 = st.columns(2)
    if _alert_stats["hit_rate"] is not None:
        _as4.metric("Tỷ lệ trúng", f"{_alert_stats['hit_rate']:.0%}")
    else:
        _as4.metric("Tỷ lệ trúng", "—")
    _as5.metric("Đã chấm", f"{_alert_stats['n_judged']}/{_alert_stats['total']}")

    # --- Filters ---
    _af1, _af2, _af3 = st.columns([2, 2, 1])
    with _af1:
        _alert_days = st.selectbox("Khoảng thời gian", [1, 3, 7, 30], index=2, key="alert_days")
    with _af2:
        _all_syms = sorted({r["symbol"] for r in _alert_store.query(days=30, limit=500)})
        _alert_sym_filter = st.selectbox(
            "Coin",
            ["Tất cả"] + _all_syms,
            index=0,
            key="alert_sym",
        )
    with _af3:
        _alert_show_dismissed = st.checkbox("Hiện đã ẩn", value=False, key="alert_dismissed")

    _alert_rows = _alert_store.query(
        symbol=_alert_sym_filter if _alert_sym_filter != "Tất cả" else None,
        days=_alert_days,
        include_dismissed=_alert_show_dismissed,
        limit=200,
    )

    if not _alert_rows:
        st.info(
            "Chưa có tín hiệu nào. Chạy `dao-vang scanner start` để bắt đầu quét 24/7. "
            "Xem `docs/TELEGRAM_SETUP.md` để cấu hình Telegram."
        )
    else:
        # --- Alert table ---
        _alert_df = pd.DataFrame(_alert_rows)
        _alert_df["probability"] = _alert_df["probability"].apply(lambda x: f"{x:.1%}")
        _alert_df["signal_time"] = pd.to_datetime(
            _alert_df["signal_time"], utc=True
        ).dt.tz_convert(SYSTEM_TIMEZONE).dt.strftime("%Y-%m-%d %H:%M UTC+7")
        _alert_df["close_price"] = _alert_df["close_price"].apply(
            lambda x: f"${x:,.4f}" if x else "—"
        )
        _alert_df["telegram_sent"] = _alert_df["telegram_sent"].map({True: "✅", False: "—"})
        _alert_df["hit"] = _alert_df["hit"].map(
            {True: "✅ Trúng", False: "❌ Trượt", None: "⏳ Chờ"}
        )
        _alert_df["dismissed"] = _alert_df["dismissed"].map({True: "🚫", False: ""})
        _alert_df = _alert_df[[
            "signal_time", "symbol", "risk_level", "probability", "close_price",
            "telegram_sent", "hit", "dismissed", "model_id",
        ]]
        _alert_df.columns = [
            "Thời gian", "Coin", "Nguy cơ", "Xác suất", "Giá",
            "Telegram", "Kết quả", "Ẩn", "AI",
        ]

        def _alert_risk_style(val):
            colors = {"CAO": "#ff4444", "TRUNG BÌNH": "#ffaa00",
                      "THẤP": "#44aa44", "RẤT THẤP": "#2266aa"}
            c = colors.get(val, "")
            return f"background-color: {c}; color: white" if c else ""

        st.dataframe(
            _alert_df.style.map(_alert_risk_style, subset=["Nguy cơ"]),
            use_container_width=True,
            hide_index=True,
        )

        # --- Deep-dive: select an alert to inspect ---
        st.markdown("##### 🔎 Phân tích sâu — chọn coin để kiểm tra")
        _dd_sym = st.selectbox(
            "Chọn coin để xem chi tiết",
            sorted({r["symbol"] for r in _alert_rows}),
            key="alert_dd_sym",
        )

        if _dd_sym:
            _dd_col1, _dd_col2 = st.columns([3, 2])
            with _dd_col1:
                st.markdown(f"###### 📊 Biểu đồ giá {_dd_sym}")
                _dd_chart_data = _fetch_recent_klines(_dd_sym, interval="1h", limit=72)
                if _dd_chart_data:
                    _dd_chart_df = pd.DataFrame(_dd_chart_data)
                    _dd_chart_df = _dd_chart_df.set_index("time")
                    st.line_chart(_dd_chart_df[["close"]], use_container_width=True)
                else:
                    st.caption("Không tải được chart.")

            with _dd_col2:
                st.markdown("###### 📋 Tín hiệu gần nhất")
                _dd_alerts = [r for r in _alert_rows if r["symbol"] == _dd_sym]
                if _dd_alerts:
                    _latest = _dd_alerts[0]
                    st.metric("Xác suất", f"{_latest['probability']:.1%}")
                    st.metric("Nguy cơ", _latest["risk_level"])
                    st.metric("Giá tại tín hiệu",
                              f"${_latest['close_price']:,.4f}" if _latest["close_price"] else "—")
                    st.metric("Hết hạn",
                              _display_datetime(_latest["invalidation_time"], "%H:%M UTC+7"))

                    # Dismiss button
                    if not _latest["dismissed"]:
                        if st.button("🚫 Ẩn tín hiệu này", key=f"dismiss_{_dd_sym}"):
                            _alert_store.dismiss(_latest["signal_time"], _dd_sym)
                            st.toast(f"Đã ẩn tín hiệu {_dd_sym}", icon="🚫")
                            st.rerun()

        # --- Scanner status ---
        st.markdown("##### ⚙️ Trạng thái bộ quét")
        _ss1, _ss2 = st.columns(2)
        _ss1.metric("Model", _alert_settings.scanner.frozen_model_id or "CHƯA CÀI")
        _ss2.metric("Chu kỳ", f"{_alert_settings.scanner.poll_interval_minutes} phút")
        _ss3, _ss4 = st.columns(2)
        _ss3.metric("Coin tối đa", _alert_settings.scanner.max_coins)
        _ss4.metric("Telegram", "✅" if _alert_settings.telegram.bot_token else "❌")

        st.caption(
            "Bật bộ quét: `dao-vang scanner start` | Test Telegram: `dao-vang scanner test-telegram` | "
            "Xem lịch sử: `dao-vang scanner history`"
        )


# ============================================================
# TAB: BẢNG XẾP HẠNG — composite score ranking + drill-down
# ============================================================
with _ranking_container:
    from dao_vang.config.settings import AppSettings as _RankSettings
    from dao_vang.scoring import classify_btc, compute_distribution_score

    _rank_settings = _RankSettings()

    st.markdown("#### 🏆 Bảng Xếp Hạng Ứng Viên Bán")
    st.caption(
        "Điểm 0-100 dựa trên 8 tín hiệu. ≥70 = ứng viên bán. "
        "Bấm vào coin để xem chi tiết."
    )

    # --- BTC context banner ---
    _has_fr = False
    _rank_db = None
    _btc_ctx = None
    try:
        _rank_db = DuckDBQueryLayer(str(_rank_settings.scanner.db_path))
        _has_fr = _rank_db.conn.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'feature_results'"
        ).fetchone()[0] > 0
        if not _has_fr:
            st.info(
                "Chưa có bảng `feature_results`. Chạy `dao-vang scanner start` "
                "hoặc quét tín hiệu trong tab **Quét tín hiệu** để tạo dữ liệu."
            )
        else:
            _btc_df = _rank_db.conn.execute(
                "SELECT * FROM feature_results WHERE symbol='BTCUSDT' "
                "ORDER BY feature_time DESC LIMIT 1"
            ).df()
            if not _btc_df.empty:
                _btc_row = _btc_df.iloc[-1]
                _btc_ctx = classify_btc(
                    btc_ret_24h=float(_btc_row.get("price_ret_24h", 0.0)),
                    btc_ret_4h=float(_btc_row.get("price_ret_4h", 0.0)),
                    btc_ret_1h=float(_btc_row.get("price_ret_5m", 0.0)),
                    config=_rank_settings.scoring,
                )
                _btc_color = {
                    "FOMO": "🔴", "NEUTRAL": "🟡", "WEAK": "🟢",
                }.get(_btc_ctx.regime, "⚪")
                _btc_regime_vi = {
                    "FOMO": "FOMO (BTC đang pump mạnh)",
                    "NEUTRAL": "Trung tính (BTC đi ngang)",
                    "WEAK": "Yếu (BTC đang giảm)",
                }.get(_btc_ctx.regime, _btc_ctx.regime)
                st.info(
                    f"{_btc_color} **Bối cảnh BTC:** {_btc_regime_vi} — "
                    f"{_btc_ctx.explanation}"
                )
            else:
                _btc_ctx = None
                st.warning("Chưa có dữ liệu BTCUSDT — chạy bộ quét trước.")
    except Exception as _rank_exc:
        _btc_ctx = None
        st.warning(f"Không tải được bối cảnh BTC: {_rank_exc}")

    # --- Score table ---
    if not _has_fr or _rank_db is None:
        st.stop()
    try:
        _all_df = _rank_db.conn.execute(
            "SELECT * FROM feature_results ORDER BY feature_time DESC"
        ).df()
        if _all_df.empty:
            st.info("Chưa có dữ liệu đặc trưng. Chạy `dao-vang scanner start` trước.")
        else:
            # Get latest row per symbol
            _latest = _all_df.drop_duplicates(subset=["symbol"], keep="first")

            # Compute scores for all symbols
            _scores = []
            for _idx, _row in _latest.iterrows():
                _feat_dict = {
                    k: v for k, v in _row.to_dict().items()
                    if pd.notna(v)
                }
                _sym = str(_row.get("symbol", ""))
                if not _sym:
                    continue
                _score = compute_distribution_score(
                    symbol=_sym,
                    features=_feat_dict,
                    btc=_btc_ctx,
                    config=_rank_settings.scoring,
                )
                _scores.append(_score)

            _scores.sort(key=lambda s: s.total_score, reverse=True)

            # Display ranking table
            _rec_vi = {
                "SHORT_CANDIDATE": "🚨 Ứng viên bán",
                "WATCH": "⚠️ Theo dõi",
                "WAIT": "⏸️ Chờ",
            }
            _btc_vi = {
                "FOMO": "🔴 FOMO",
                "NEUTRAL": "🟡 Trung tính",
                "WEAK": "🟢 Yếu",
            }
            # --- Clickable ranking list (single full-width button per coin) ---
            for _i, _s in enumerate(_scores, 1):
                _rec_label = _rec_vi.get(_s.recommendation, _s.recommendation)
                _score_color = "🔴" if _s.total_score >= 70 else "🟡" if _s.total_score >= 40 else "🟢"
                _rank_btn_label = f"{_score_color} #{_i}  {_s.symbol}  •  {_s.total_score:.0f}/100  •  {_rec_label}  →"

                if st.button(
                    _rank_btn_label,
                    key=f"rank_goto_{_s.symbol}",
                    help=f"Xem báo cáo {_s.symbol}",
                    use_container_width=True,
                ):
                    st.session_state.focus_coin = _s.symbol
                    st.session_state.focus_mode = True
                    st.session_state.active_tab = "🎯 Phân tích"
                    st.rerun()

            # --- Drill-down: quick preview in same tab (collapsed by default) ---
            with st.expander("🔬 Xem nhanh tín hiệu", expanded=False):
                _selected_sym = st.selectbox(
                    "Chọn coin:",
                    options=[s.symbol for s in _scores],
                    index=0,
                    key="rank_preview_select",
                )

                _selected = next(
                    (s for s in _scores if s.symbol == _selected_sym), None
                )
                if _selected:
                    _rec_label = _rec_vi.get(_selected.recommendation, _selected.recommendation)
                    st.markdown(
                        f"**{_selected.symbol}** — "
                        f"{_selected.total_score:.0f}/100 "
                        f"({_rec_label})"
                    )

                    # Display each component as a bar
                    _signal_vi = {
                        "PRICE_VOLUME_DIVERGENCE": "Phân kỳ giá-khối lượng",
                        "FUNDING_SPIKE": "Funding tăng vọt",
                        "MOMENTUM_EXHAUSTION": "Động lượng cạn kiệt",
                        "DISTANCE_FROM_HIGH": "Khoảng cách từ đỉnh",
                        "TAKER_SELL_PRESSURE": "Áp lực bán chủ động",
                        "OI_DIVERGENCE": "Phân kỳ OI",
                        "BTC_CONTEXT": "Bối cảnh BTC",
                        "FAKE_BREAKOUT": "Phá vỡ giả (bẫy FOMO)",
                    }
                    for _comp in _selected.components:
                        _label = _signal_vi.get(_comp.name, _comp.name.replace("_", " ").title())
                        _pct = _comp.score / 100.0
                        st.markdown(f"**{_label}** — {_comp.score:.0f}/100 "
                                    f"(trọng số {_comp.weight:.0%})")
                        st.progress(_pct, text=_comp.explanation)
                        st.caption(f"Giá trị thực: {_comp.raw_value}")

                    # BTC context detail
                    _btc_label = _btc_vi.get(_selected.btc_regime, _selected.btc_regime)
                    st.caption(f"**Bối cảnh BTC:** {_btc_label} — {_selected.btc_explanation}")
    except Exception as _rank_err:
        st.error(f"Lỗi tải bảng xếp hạng: {_rank_err}")


# ============================================================
# TAB: QUÉT MULTI-COIN — scan top volatile coins (Nghiên cứu mode)
# ============================================================
with _scan_container:
    st.markdown("#### 🔍 Quét nhiều coin — tìm coin nào AI phát hiện xả tốt nhất")
    st.caption(
        "Quét top coin biến động nhất → thu thập 90 ngày dữ liệu → đếm sự kiện xả → chạy AI → so sánh với 'đoán mò'. "
        "Coin biến động mạnh có nhiều sự kiện xả hơn BTC → đủ data để kiểm chứng AI. "
        "Tiêu chí 'xả': giá giảm ≥8% trong 24h, không tăng quá 4% trước khi giảm."
    )

    _scan_db_path = "./data/scan_volatile.duckdb"
    _scan_db_exists = Path(_scan_db_path).exists()

    # --- Controls ---
    _scan_col1, _scan_col2, _scan_col3 = st.columns([2, 1, 1])
    with _scan_col1:
        _n_coins = st.slider(
            "Số coin volatile nhất cần quét",
            min_value=5, max_value=30, value=15, step=5,
            help="Lấy top N coin theo |thay đổi giá 24h|, khối lượng tối thiểu 10 triệu USD",
        )
    with _scan_col2:
        _scan_days = st.selectbox("Số ngày lịch sử", [30, 60, 90], index=2)
    with _scan_col3:
        _min_events = st.selectbox("Số sự kiện tối thiểu để chạy thử nghiệm", [30, 50, 100], index=1)

    _scan_run = st.button(
        "🚀 Chạy quét multi-coin",
        help="Thu thập nến 90 ngày + lãi suất funding cho các coin biến động mạnh, chạy gán nhãn + thử nghiệm",
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
                    # --- Load all scan artifacts ---
                    _registry = ArtifactRegistry(Path("./artifacts"))
                    _all_artifacts = _registry.list_artifacts()
                    _scan_artifacts = [
                        a for a in _all_artifacts
                        if "volatile" in a.get("config", {}).get("hypothesis_id", "")
                    ]

                    # Group artifacts by scan run (same created_at date + hour)
                    _scan_runs = {}
                    for a in _scan_artifacts:
                        created = a.get("created_at", "")[:13]  # YYYY-MM-DDTHH
                        if created not in _scan_runs:
                            _scan_runs[created] = []
                        _scan_runs[created].append(a)

                    # --- Scan history summary ---
                    if _scan_runs:
                        st.markdown("##### 📅 Lịch sử các lần quét")
                        _history_data = []
                        for run_time, arts in sorted(_scan_runs.items(), reverse=True):
                            _best_p = 0
                            _best_sym = ""
                            _n_edge = 0
                            _n_total = len(arts)
                            _n_valid = 0
                            for a in arts:
                                res = a.get("results", {})
                                agg = res.get("aggregate", {})
                                baselines = res.get("baselines", {})
                                leak = res.get("leakage_report", {})
                                mp = agg.get("precision_mean", 0)
                                bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
                                nv = agg.get("n_valid_folds", 0)
                                ls = leak.get("status", "?")
                                sym = a.get("config", {}).get("hypothesis_id", "").replace("hyp_volatile_", "")
                                if nv > 0:
                                    _n_valid += 1
                                if ls == "passed" and mp > bp and mp > 0:
                                    _n_edge += 1
                                if mp > _best_p:
                                    _best_p = mp
                                    _best_sym = sym

                            _run_date = run_time.replace("T", " ")
                            _history_data.append({
                                "Lần quét": _run_date,
                                "Số coin": _n_total,
                                "Coin hợp lệ": _n_valid,
                                "AI tốt hơn mốc": _n_edge,
                                "Coin tốt nhất": f"{_best_sym} (P={_best_p:.1%})" if _best_sym else "—",
                            })
                        st.dataframe(pd.DataFrame(_history_data), use_container_width=True, hide_index=True)
                        st.caption(f"📊 Tổng cộng **{len(_scan_runs)} lần quét** | **{len(_scan_artifacts)} thử nghiệm** | "
                                   f"Coin hợp lệ = có đủ sự kiện xả để chạy AI")

                    # --- Coin list with latest results ---
                    st.markdown("---")
                    st.markdown("##### 🪙 Danh sách coin đã quét")
                    st.caption("Chọn coin bên dưới để xem chi tiết. Mỗi coin hiển thị kết quả từ lần quét gần nhất.")

                    # Build coin → latest artifact mapping
                    _coin_latest = {}
                    _coin_all_artifacts = {}
                    for a in _scan_artifacts:
                        sym = a.get("config", {}).get("hypothesis_id", "").replace("hyp_volatile_", "")
                        if not sym:
                            continue
                        created = a.get("created_at", "")
                        if sym not in _coin_latest or created > _coin_latest[sym].get("created_at", ""):
                            _coin_latest[sym] = a
                        if sym not in _coin_all_artifacts:
                            _coin_all_artifacts[sym] = []
                        _coin_all_artifacts[sym].append(a)

                    # Merge with coin_stats (coins in DB but maybe no artifact yet)
                    _coin_list = []
                    for sym, total, pos, neg, first_ts, last_ts in _coin_stats:
                        prev = pos / total if total > 0 else 0
                        days = (last_ts - first_ts).total_seconds() / 86400 if first_ts and last_ts else 0
                        latest = _coin_latest.get(sym)
                        if latest:
                            res = latest.get("results", {})
                            agg = res.get("aggregate", {})
                            baselines = res.get("baselines", {})
                            leak = res.get("leakage_report", {})
                            ci = agg.get("confidence_intervals", {}).get("precision", {})
                            mp = agg.get("precision_mean", 0)
                            bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
                            nv = agg.get("n_valid_folds", 0)
                            ls = leak.get("status", "?")
                            n_runs = len(_coin_all_artifacts.get(sym, []))

                            if ls != "passed":
                                status = "🔴 Rò rỉ"
                            elif nv == 0:
                                status = "⚪ Thiếu dữ liệu"
                            elif mp > bp and mp > 0:
                                status = "🟢 AI tốt hơn mốc"
                            else:
                                status = "🟡 AI chưa tốt hơn mốc"

                            _coin_list.append({
                                "coin": sym, "status": status, "pos": pos, "total": total,
                                "prev": prev, "days": days, "mp": mp, "bp": bp,
                                "ci_lower": ci.get("ci_lower", 0), "ci_upper": ci.get("ci_upper", 0),
                                "nv": nv, "leak": ls, "n_runs": n_runs,
                                "latest_time": latest.get("created_at", ""), "artifact_id": latest.get("artifact_id", ""),
                            })
                        else:
                            _coin_list.append({
                                "coin": sym, "status": "⬜ Chưa chạy thử nghiệm", "pos": pos, "total": total,
                                "prev": prev, "days": days, "mp": 0, "bp": 0,
                                "ci_lower": 0, "ci_upper": 0, "nv": 0, "leak": "?",
                                "n_runs": 0, "latest_time": "", "artifact_id": "",
                            })

                    # Display coin table
                    _display_data = []
                    for c in _coin_list:
                        _display_data.append({
                            "Coin": c["coin"],
                            "Kết quả": c["status"],
                            "Sự kiện xả": c["pos"],
                            "Tần suất xả": f"{c['prev']:.1%}",
                            "Số ngày": f"{c['days']:.1f}",
                            "AI chính xác": f"{c['mp']:.1%}" if c["mp"] > 0 else "—",
                            "Mốc tốt nhất": f"{c['bp']:.1%}" if c["bp"] > 0 else "—",
                            "Khoảng tin cậy 95%": f"[{c['ci_lower']:.1%}, {c['ci_upper']:.1%}]" if c["nv"] > 0 else "—",
                            "Số lần kiểm tra": c["nv"],
                            "Số lần quét": c["n_runs"],
                            "Quét gần nhất": c["latest_time"][:16] if c["latest_time"] else "—",
                        })
                    st.dataframe(pd.DataFrame(_display_data), use_container_width=True, hide_index=True)

                    # Highlight edge coins
                    _edge_coins = [c for c in _coin_list if "AI tốt hơn mốc" in c["status"]]
                    if _edge_coins:
                        st.success(
                            f"🟢 **{len(_edge_coins)} coin: AI tốt hơn mốc so sánh**: "
                            + ", ".join(c["coin"] for c in _edge_coins)
                        )
                    else:
                        st.info("Chưa có coin nào AI tốt hơn mốc. Thử quét thêm hoặc thu thập thêm dữ liệu.")

                    # --- Coin detail viewer ---
                    st.markdown("---")
                    st.markdown("##### 🔎 Xem chi tiết từng coin")
                    _detail_coins = [c["coin"] for c in _coin_list]
                    if _detail_coins:
                        _selected_coin = st.selectbox(
                            "Chọn coin để xem chi tiết",
                            _detail_coins,
                            help="Hiển thị kết quả đầy đủ: chỉ số, các lần kiểm tra, đặc trưng quan trọng, thời gian cảnh báo trước"
                        )

                        if _selected_coin:
                            _sel = next(c for c in _coin_list if c["coin"] == _selected_coin)
                            _sel_artifacts = _coin_all_artifacts.get(_selected_coin, [])

                            # --- Overview metrics ---
                            _dc1, _dc2, _dc3 = st.columns(3)
                            _dc1.metric("Sự kiện xả", _sel["pos"], help="Số nến giảm ≥8% trong 24h")
                            _dc2.metric("Tần suất", f"{_sel['prev']:.1%}")
                            _dc3.metric("Ngày data", f"{_sel['days']:.1f}")
                            _dc4, _dc5 = st.columns(2)
                            _dc4.metric("AI chính xác", f"{_sel['mp']:.1%}" if _sel["mp"] > 0 else "—", help=_glossary_tooltip("Precision"))
                            _dc5.metric("Số lần quét", _sel["n_runs"])

                            if _sel["nv"] > 0:
                                _dc6, _dc7, _dc8 = st.columns(3)
                                _dc6.metric("Mốc tốt nhất", f"{_sel['bp']:.1%}", help="Cách đơn giản nhất, AI phải giỏi hơn")
                                _dc7.metric("Khoảng tin cậy 95%", f"[{_sel['ci_lower']:.1%}, {_sel['ci_upper']:.1%}]")
                                _dc8.metric("Rò rỉ dữ liệu", "✅ Không" if _sel["leak"] == "passed" else f"❌ {_sel['leak']}")

                                # Conclusion
                                if _sel["leak"] == "passed" and _sel["mp"] > _sel["bp"] and _sel["mp"] > 0:
                                    if _sel["pos"] < 100:
                                        st.warning(f"🟡 **CÓ TRIỂN VỌNG** — AI chính xác {_sel['mp']:.1%} > mốc {_sel['bp']:.1%}, nhưng chỉ {_sel['pos']} sự kiện. Cần thêm dữ liệu.")
                                    else:
                                        st.success(f"🟢 **AI TỐT HƠN MỐC SO SÁNH** — chính xác {_sel['mp']:.1%} > {_sel['bp']:.1%}")
                                elif _sel["mp"] > 0:
                                    st.warning(f"🟡 **AI CHƯA TỐT HƠN MỐC** — chính xác {_sel['mp']:.1%} ≤ mốc {_sel['bp']:.1%}")
                                else:
                                    st.error("🔴 AI không hoạt động — quá ít sự kiện xả")

                            # --- History of this coin's experiments ---
                            if _sel_artifacts:
                                st.markdown("---")
                                st.markdown("###### 📊 Lịch sử thử nghiệm của coin này")
                                _hist_data = []
                                for a in reversed(_sel_artifacts):
                                    res = a.get("results", {})
                                    agg = res.get("aggregate", {})
                                    baselines = res.get("baselines", {})
                                    leak = res.get("leakage_report", {})
                                    ci = agg.get("confidence_intervals", {}).get("precision", {})
                                    mp = agg.get("precision_mean", 0)
                                    bp = max((m.get("precision_mean", 0) for m in baselines.values()), default=0)
                                    nv = agg.get("n_valid_folds", 0)
                                    ns = agg.get("n_skipped_folds", 0)
                                    ls = leak.get("status", "?")
                                    created = a.get("created_at", "")[:19]

                                    if ls != "passed":
                                        _st = "🔴 Rò rỉ"
                                    elif nv == 0:
                                        _st = "⚪ Thiếu dữ liệu"
                                    elif mp > bp and mp > 0:
                                        _st = "🟢 Giỏi hơn"
                                    else:
                                        _st = "🟡 Chưa giỏi hơn"

                                    _hist_data.append({
                                        "Lần chạy": created,
                                        "Kết quả": _st,
                                        "AI chính xác": f"{mp:.1%}",
                                        "Mốc": f"{bp:.1%}",
                                        "Khoảng tin cậy 95%": f"[{ci.get('ci_lower', 0):.1%}, {ci.get('ci_upper', 0):.1%}]" if nv > 0 else "—",
                                        "Hợp lệ": nv,
                                        "Bỏ qua": ns,
                                        "Rò rỉ": "✅" if ls == "passed" else "❌",
                                    })
                                st.dataframe(pd.DataFrame(_hist_data), use_container_width=True, hide_index=True)

                                # --- Latest experiment detail ---
                                _latest = _sel_artifacts[0]  # already sorted newest first
                                _latest_res = _latest.get("results", {})
                                _latest_agg = _latest_res.get("aggregate", {})
                                _latest_folds = _latest_res.get("per_fold", [])
                                _latest_baselines = _latest_res.get("baselines", {})
                                _latest_leak = _latest_res.get("leakage_report", {})
                                _latest_lt = _latest_res.get("lead_time_stats", {})
                                _latest_dq = _latest_res.get("data_quality", {})

                                with st.expander("📈 Chi tiết lần chạy gần nhất", expanded=False):
                                    # Per-fold details
                                    if _latest_folds:
                                        st.markdown("**Các lần kiểm tra (kiểm tra theo thời gian):**")
                                        st.caption("Mỗi lần: train trên quá khứ → test trên tương lai. Train/Test = số nến (số sự kiện xả).")
                                        _fold_rows = []
                                        for fold in _latest_folds:
                                            row = {"Lần": fold.get("fold_idx", "?")}
                                            if fold.get("skipped"):
                                                row["Trạng thái"] = f"⚪ Bỏ qua: {fold.get('reason', '')}"
                                            else:
                                                m = fold.get("metrics", {})
                                                row["Chính xác"] = f"{m.get('precision', 0):.1%}"
                                                row["Bắt được"] = f"{m.get('recall', 0):.1%}"
                                                row["Chuẩn xác"] = f"{m.get('brier', 0):.3f}"
                                                row["Ngưỡng"] = f"{m.get('threshold', 0.5):.2f}"
                                                row["Train"] = f"{fold.get('train_size', 0)} ({fold.get('train_positives', 0)} xả)"
                                                row["Test"] = f"{fold.get('test_size', 0)} ({fold.get('test_positives', 0)} xả)"
                                            _fold_rows.append(row)
                                        st.dataframe(pd.DataFrame(_fold_rows), use_container_width=True, hide_index=True)

                                    # Baselines comparison
                                    if _latest_baselines:
                                        st.markdown("**So sánh AI với các cách đơn giản:**")
                                        _bl_names = {
                                            "B0_random": "Ngẫu nhiên",
                                            "B1_price_ret_0.0": "Giá giảm bất kỳ",
                                            "B1_price_ret_0.02": "Giá giảm ≥2%",
                                            "B1_price_ret_0.05": "Giá giảm ≥5%",
                                            "B2_funding_0.5": "Funding ≥50%",
                                            "B2_funding_0.8": "Funding ≥80%",
                                            "B2_funding_0.9": "Funding ≥90%",
                                        }
                                        _bl_rows = [{"Phương pháp": f"AI ({_selected_coin})",
                                                     "Độ chính xác": _latest_agg.get("precision_mean", 0),
                                                     "Tỷ lệ bắt được": _latest_agg.get("recall_mean", 0),
                                                     "Độ chuẩn xác": _latest_agg.get("brier_mean", 0)}]
                                        for name, m in _latest_baselines.items():
                                            _bl_rows.append({
                                                "Phương pháp": _bl_names.get(name, name),
                                                "Độ chính xác": m.get("precision_mean", 0),
                                                "Tỷ lệ bắt được": m.get("recall_mean", 0),
                                                "Độ chuẩn xác": m.get("brier_mean", 0),
                                            })
                                        st.dataframe(
                                            pd.DataFrame(_bl_rows).style.format({
                                                "Độ chính xác": "{:.1%}", "Tỷ lệ bắt được": "{:.1%}", "Độ chuẩn xác": "{:.4f}"
                                            }),
                                            use_container_width=True, hide_index=True,
                                        )

                                    # Lead time
                                    if _latest_lt and _latest_lt.get("status") == "ok":
                                        st.markdown(f"**⏱️ Cảnh báo trước:** trung bình ~{_latest_lt.get('median_hours', 0):.1f}h "
                                                    f"(phạm vi {_latest_lt.get('min_minutes', 0):.0f}–{_latest_lt.get('max_minutes', 0):.0f} phút)")

                                    # Leakage
                                    st.markdown(f"**🔍 Rò rỉ dữ liệu:** {'✅ Không phát hiện' if _latest_leak.get('status') == 'passed' else '❌ ' + str(_latest_leak.get('forbidden_columns', []))}")

                                    # Data quality
                                    _ld = _latest_dq.get("label_distribution", {})
                                    st.caption(f"Tổng nến: {_latest_dq.get('total_rows', 0):,} | "
                                               f"Xả: {_ld.get('positive', 0)} | Bình thường: {_ld.get('negative', 0)} | "
                                               f"Tần suất xả: {_ld.get('prevalence', 0):.1%}")

                            _scan_conn.close()
                    else:
                        st.info("Chưa có coin nào trong database. Bấm 'Chạy quét' để bắt đầu.")
                else:
                    st.info("Cơ sở dữ liệu có nhưng chưa có nhãn. Bấm 'Chạy quét' để bắt đầu.")
            else:
                st.info("Cơ sở dữ liệu có nhưng chưa có bảng nhãn. Bấm 'Chạy quét' để bắt đầu.")

            _scan_conn.close()
        except Exception as e:
            st.warning(f"Không đọc được scan DB: {e}")

    # --- Run scan on button click ---
    if _scan_run:
        if not _tickers:
            st.error("Không lấy được ticker data từ Binance.")
        else:
            import logging as _logging
            import time as _time
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
            _now = system_now()
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
                            _st = "🔴 Rò rỉ"
                        elif _nv == 0:
                            _st = "⚪ Thiếu dữ liệu"
                        elif _mp > _bp and _mp > 0:
                            _st = "🟢 AI tốt hơn mốc"
                        else:
                            _st = "🟡 AI chưa tốt hơn mốc"

                        _n = _scan_db.conn.execute("SELECT count(*) FROM feature_results").fetchone()[0]
                        _np = _scan_db.conn.execute("SELECT count(*) FROM labels WHERE label_value = 1").fetchone()[0]
                        _results_summary.append({
                            "Coin": sym, "Kết quả": _st, "Số nến": _n, "Sự kiện xả": _np,
                            "AI chính xác": f"{_mp:.1%}", "Mốc tốt nhất": f"{_bp:.1%}",
                            "Khoảng tin cậy 95%": f"[{_ci.get('ci_lower', 0):.1%}, {_ci.get('ci_upper', 0):.1%}]",
                            "Số lần kiểm tra": _nv, "Rò rỉ": "✅" if _ls == "passed" else "❌",
                        })
                    except Exception as e:
                        _results_summary.append({"Coin": sym, "Kết quả": "❌ Lỗi", "Chi tiết": str(e)})
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

                _edge = [r for r in _results_summary if "AI tốt hơn mốc" in r.get("Kết quả", "")]
                if _edge:
                    st.success(
                        f"🟢 **{len(_edge)} coin: AI tốt hơn mốc so sánh**: "
                        + ", ".join(r["Coin"] for r in _edge)
                    )
                else:
                    st.info("Chưa có coin nào AI tốt hơn mốc. Thử tăng số ngày hoặc giảm số sự kiện tối thiểu.")

            except Exception as e:
                st.error(f"Lỗi chạy pipeline: {e}")
                import traceback
                st.code(traceback.format_exc())


# ============================================================
# MARKET OBSERVATION — merged into Ranking tab (Cảnh báo mode)
# ============================================================
with _market_container:
    st.markdown("#### 📊 Quan sát thị trường")
    # --- Binance listing overview (Spot vs Futures) ---
    st.markdown("##### 🏛️ Tổng quan niêm yết trên Binance")
    st.caption(
        "Số lượng coin/symbol đang giao dịch trên các sàn Binance (lấy trực tiếp từ exchangeInfo). "
        "Giao ngay (Spot) = api.binance.com · Futures USD-M = fapi.binance.com · Futures COIN-M = dapi.binance.com. "
        "Tự quét 1 lần/ngày (UTC+7) và lưu vào `data/binance_listing_history.json`."
    )

    _stats = _get_listing_stats()
    _stats_col_refresh = st.columns([10, 1])[1]
    with _stats_col_refresh:
        if st.button("🔄 Niêm yết", help="Quét lại danh sách niêm yết hôm nay từ Binance", key="refresh_listing"):
            st.session_state._listing_force = True
            st.rerun()

    if _stats:
        _is_today = _listing_is_today(_stats)
        _freshness = "✅ Đã quét hôm nay" if _is_today else f"⚠️ Data cũ ({_stats.get('date', '?')}) — bấm 🔄 để quét"
        st.caption(_freshness)

        _m1, _m2, _m3 = st.columns(3)
        _m1.metric("Spot", f"{_stats['spot_coins']:,}",
                   help=f"{_stats['spot_symbols']:,} symbol · {_stats['spot_usdt_pairs']:,} cặp USDT")
        _m2.metric("USD-M", f"{_stats['usdm_coins']:,}",
                   help=f"{_stats['usdm_symbols']:,} symbol · {_stats['usdm_usdt_pairs']:,} cặp USDT")
        _m3.metric("COIN-M", f"{_stats['coinm_coins']:,}",
                   help=f"{_stats['coinm_symbols']:,} symbol (margined bằng coin)")
        _m4, _m5 = st.columns(2)
        _m4.metric("Futures tổng", f"{_stats['futures_coins']:,}",
                   help="Số coin unique trên ít nhất 1 sàn futures")
        _m5.metric("Tổng Binance", f"{_stats['all_coins']:,}",
                   help=f"Spot ∪ Futures · Chỉ Spot: {_stats['spot_only']:,} · Cả hai: {_stats['both']:,}")

        with st.expander("📊 Chi tiết phân bổ coin + lịch sử quét", expanded=False):
            _ov1, _ov2, _ov3 = st.columns(3)
            _ov1.metric("Coin chỉ có trên Spot", f"{_stats['spot_only']:,}")
            _ov2.metric("Coin chỉ có trên Futures", f"{_stats['futures_only']:,}")
            _ov3.metric("Coin có trên cả Spot & Futures", f"{_stats['both']:,}")
            st.caption(
                f"Cập nhật lúc: {_stats.get('fetched_at', '?')} · Quét 1 lần/ngày (UTC+7). "
                f"Lưu ý: app Đảo Vàng dùng dữ liệu USD-M Futures (fapi.binance.com)."
            )

            # --- History chart ---
            _history = _load_listing_history(_LISTING_HISTORY_PATH)
            if len(_history) >= 2:
                st.markdown("###### 📈 Lịch sử số lượng coin theo ngày")
                _hist_df = pd.DataFrame(_history)
                _hist_df["date"] = pd.to_datetime(_hist_df["date"])
                _chart_df = _hist_df.set_index("date")[
                    ["spot_coins", "usdm_coins", "coinm_coins", "futures_coins", "all_coins"]
                ].rename(columns={
                    "spot_coins": "Giao ngay (Spot)",
                    "usdm_coins": "Futures USD-M",
                    "coinm_coins": "Futures COIN-M",
                    "futures_coins": "Futures tổng",
                    "all_coins": "Tổng Binance",
                })
                st.line_chart(_chart_df, use_container_width=True, height=250)

                st.markdown("###### 📋 Bảng lịch sử (mới nhất trên cùng)")
                _table_df = _hist_df.sort_values("date", ascending=False)[
                    ["date", "spot_coins", "usdm_coins", "coinm_coins", "futures_coins", "all_coins", "fetched_at"]
                ].copy()
                _table_df["date"] = _table_df["date"].dt.strftime("%Y-%m-%d")
                _table_df.columns = ["Ngày", "Giao ngay (Spot)", "Futures USD-M", "Futures COIN-M", "Futures tổng", "Tổng Binance", "Quét lúc"]
                st.dataframe(_table_df, use_container_width=True, hide_index=True)
                st.caption(f"Tổng cộng **{len(_history)} ngày** có dữ liệu · file: `{_LISTING_HISTORY_PATH}`")
            else:
                st.info(
                    "Chưa đủ dữ liệu lịch sử để vẽ chart (cần ≥ 2 ngày). "
                    "Chạy `dao-vang data listing-scan` mỗi ngày để tích lũy."
                )
    else:
        st.info("Không lấy được số liệu listing từ Binance. Bấm 🔄 Listing để thử lại.")

    st.markdown("---")

    if _tickers:
        _top_gainers = _tickers[:50]
        _top_losers = sorted(_tickers, key=lambda x: float(x.get("priceChangePercent", 0)))[:50]

        # --- Top gainers as clickable buttons ---
        st.markdown("##### 🟢 Top 50 tăng mạnh nhất — bấm để xem")
        _gainer_grid = st.columns(5)
        for i, d in enumerate(_top_gainers):
            sym = d["symbol"]
            pct = float(d["priceChangePercent"])
            price = float(d["lastPrice"])
            col = _gainer_grid[i % 5]
            label = f"{sym}\n{pct:+.2f}%"
            if col.button(label, key=f"gainer_{sym}", use_container_width=True, help=f"Giá: {price:.6f} | Khối lượng: {float(d['quoteVolume']):,.0f}"):
                st.session_state.selected_gainer = sym

        # --- Top losers ---
        st.markdown("##### 🔴 Top 50 giảm mạnh nhất")
        _loser_grid = st.columns(5)
        for i, d in enumerate(_top_losers):
            sym = d["symbol"]
            pct = float(d["priceChangePercent"])
            price = float(d["lastPrice"])
            col = _loser_grid[i % 5]
            label = f"{sym}\n{pct:+.2f}%"
            if col.button(label, key=f"loser_{sym}", use_container_width=True, help=f"Giá: {price:.6f} | Khối lượng: {float(d['quoteVolume']):,.0f}"):
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

                dc1, dc2 = st.columns(2)
                dc1.metric("Giá hiện tại", f"{float(_ticker_info.get('lastPrice', 0)):.6f}")
                dc2.metric("24h", f"{float(_ticker_info.get('priceChangePercent', 0)):+.2f}%")
                dc3, dc4 = st.columns(2)
                dc3.metric("Volume 24h", f"{float(_ticker_info.get('quoteVolume', 0)):,.0f}")
                dc4.metric("Cao/Thấp", f"{float(_ticker_info.get('highPrice', 0)):.6f} / {float(_ticker_info.get('lowPrice', 0)):.6f}")

                # --- Chart type selector ---
                _chart_type = st.radio(
                    "Chart",
                    ["🕯️ Nến", "📈 Đường", "📊 TradingView"],
                    horizontal=True,
                    key="chart_type_radio",
                )
                _tf_col, _tv_col = st.columns(2)
                with _tf_col:
                    _tf = st.selectbox(
                        "Khung",
                        ["15m", "1h", "4h", "1d"],
                        index=1,
                        key="chart_tf_select",
                    )
                with _tv_col:
                    _n_candles = st.selectbox(
                        "Nến",
                        [48, 96, 200, 500],
                        index=0,
                        key="chart_n_select",
                    )

                # Re-fetch with selected timeframe if not 1h/48
                if _tf != "1h" or _n_candles != 48:
                    _klines = _fetch_recent_klines(_show_symbol, _tf, _n_candles)
                    _kdf = pd.DataFrame(_klines) if _klines else _kdf

                if _chart_type == "🕯️ Nến":
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
                        height=320,
                        margin=dict(l=0, r=0, t=20, b=0),
                        xaxis_rangeslider_visible=False,
                        yaxis_title="Giá",
                    )
                    _fig.update_xaxes(showgrid=True, gridwidth=1, gridcolor='rgba(50,50,50,0.3)')
                    st.plotly_chart(_fig, use_container_width=True, config={"displayModeBar": False})

                elif _chart_type == "📈 Đường":
                    _chart_data = _kdf.set_index("time")[["close"]]
                    st.line_chart(_chart_data, use_container_width=True)

                elif _chart_type == "📊 TradingView":
                    import streamlit.components.v1 as components
                    _tv_embed = f"""
                    <iframe
                        src="https://s.tradingview.com/widgetembed/?frameElementId=tv_chart&symbol=BINANCE%3A{_show_symbol}&interval={_tf}&hidesidetoolbar=false&symboledit=true&saveimage=false&toolbarbg=%231a1a2e&theme=dark&style=1&hideideas=true&locale=vi_VN"
                        style="width:100%;height:400px;border:0;margin:0;padding:0;"
                        allowfullscreen
                        allow="autoplay; clipboard-read; clipboard-write"
                    ></iframe>
                    """
                    components.html(_tv_embed, height=420)
                    st.caption("ℹ️ Nếu trắng — coin chưa có trên TradingView.")

                # --- Action buttons ---
                _wl_r1c1, _wl_r1c2 = st.columns(2)
                with _wl_r1c1:
                    if _show_symbol in st.session_state.watchlist:
                        st.caption(f"✅ {_show_symbol} trong watchlist")
                    else:
                        if st.button("➕ Thêm watchlist", key="add_wl", use_container_width=True):
                            st.session_state.watchlist.append(_show_symbol)
                            _save_watchlist(st.session_state.watchlist)
                            st.toast(f"✅ Đã thêm {_show_symbol}!")
                            st.rerun()
                with _wl_r1c2:
                    if st.button("🔄 Làm mới", use_container_width=True):
                        st.rerun()
                _wl_r2c1, _wl_r2c2 = st.columns(2)
                with _wl_r2c1:
                    if st.button("🚀 Quét coin", key="scan_gainer", use_container_width=True):
                        st.session_state.scan_symbol = _show_symbol
                        st.rerun()
                with _wl_r2c2:
                    _binance_url = f"https://www.binance.com/en/futures/{_show_symbol}"
                    st.link_button("📈 Binance", _binance_url, use_container_width=True)

    # --- Watchlist panel ---
    if st.session_state.watchlist:
        st.markdown("---")
        st.markdown(f"##### 📋 Danh sách theo dõi ({len(st.session_state.watchlist)} coin)")
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
# SIDEBAR — context-aware config (symbol, date range, advanced)
# ============================================================
with st.sidebar:
    # --- BTC context (always visible) ---
    try:
        _btc_db = DuckDBQueryLayer(str(AppSettings().scanner.db_path))
        _btc_df = _btc_db.conn.execute(
            "SELECT * FROM feature_results WHERE symbol='BTCUSDT' "
            "ORDER BY feature_time DESC LIMIT 1"
        ).df()
        if not _btc_df.empty:
            from dao_vang.scoring import classify_btc
            _btc_row = _btc_df.iloc[-1]
            _btc_ctx = classify_btc(
                btc_ret_24h=float(_btc_row.get("price_ret_24h", 0.0)),
                btc_ret_4h=float(_btc_row.get("price_ret_4h", 0.0)),
                btc_ret_1h=float(_btc_row.get("price_ret_5m", 0.0)),
                config=AppSettings().scoring,
            )
            _btc_color = {"FOMO": "🔴", "NEUTRAL": "🟡", "WEAK": "🟢"}.get(
                _btc_ctx.regime, "⚪"
            )
            st.markdown(f"**{_btc_color} BTC: {_btc_ctx.regime}**")
            st.caption(f"24h: {_btc_ctx.btc_ret_24h:+.1%} | Score: {_btc_ctx.score_adjustment:.0f}/100")
    except Exception:
        st.caption("⬜ Bối cảnh BTC: chưa có dữ liệu")

    # --- Symbol selection (only for Deep-dive + Backtest modes) ---
    _show_symbol_picker = (
        _app_mode == "🚨 Cảnh báo"  # Deep-dive tab
        or _app_mode == "🔬 Nghiên cứu"  # Backtest tab
    )
    symbol = "BTCUSDT"  # default

    # --- Focused coin view: minimal config, back button already in first sidebar block ---
    _focus_mode = st.session_state.get("focus_mode", False)
    _focus_coin = st.session_state.get("focus_coin")
    if _focus_mode and _focus_coin and _show_symbol_picker:
        symbol = _focus_coin
        _data_dir_scan = Path("data")
        _downloaded = scan_downloaded_data(_data_dir_scan)
        run_bt = False

        now = system_now()
        default_start = now - timedelta(days=30)
        start_date = default_start
        end_date = now
        db_path = "./data/dev.duckdb"
        artifact_dir = "./artifacts"
        hypothesis_id = "hyp_dashboard_001"
        baseline_model = "logreg_walkforward"
        seed = 42

        # --- Switch coin without leaving focus mode ---
        _focus_available = sorted(_downloaded.keys())
        _new_focus = None
        if _focus_available:
            _default_idx = _focus_available.index(_focus_coin) if _focus_coin in _focus_available else 0
            _new_focus = st.selectbox(
                "Đổi coin",
                options=_focus_available,
                index=_default_idx,
                key="focus_coin_select",
            )
        else:
            _new_focus = st.text_input(
                "Nhập mã coin", value=_focus_coin, key="focus_coin_input"
            ).strip().upper()
        if _new_focus and _new_focus != _focus_coin:
            st.session_state.focus_coin = _new_focus
            st.session_state.focus_run_scan = False
            st.rerun()

        # --- Back to ranking ---
        if st.button("← Quay lại bảng xếp hạng", use_container_width=True, key="focus_back_btn"):
            st.session_state.focus_mode = False
            st.session_state.focus_coin = None
            st.session_state.focus_run_scan = False
            st.session_state.active_tab = "🏆 Xếp Hạng"
            st.rerun()

        # --- Run full AI ---
        run_scan = st.session_state.get("focus_run_scan", False)
        st.markdown("---")
        if run_scan:
            if st.button("🔄 Dừng & chọn lại", use_container_width=True, key="focus_stop_scan"):
                st.session_state.focus_run_scan = False
                st.rerun()
        else:
            if st.button("🚀 Chạy AI đầy đủ", type="primary", use_container_width=True, key="focus_run_scan"):
                st.session_state.focus_run_scan = True
                st.rerun()
    elif _show_symbol_picker:
        _data_dir_scan = Path("data")
        _downloaded = scan_downloaded_data(_data_dir_scan)
        _all_symbols = sorted(_downloaded.keys())
        run_scan = False
        run_bt = False

        # If user clicked coin from ranking → two-step: switch tab, then run analysis
        _rank_goto = st.session_state.get("rank_goto_coin")
        _rank_step = st.session_state.get("rank_step")
        # If user clicked "Quét coin này" from top gainers, prefill symbol
        _scan_from_gainer = st.session_state.get("scan_symbol")
        if _rank_step == "step1" and _rank_goto:
            symbol = _rank_goto
            st.info(f"🎯 Chuẩn bị phân tích **{_rank_goto}** — chuyển sang tab '🎯 Phân tích'")
            st.session_state.rank_step = "step2"
            st.rerun()
        elif _rank_step == "step2" and _rank_goto:
            symbol = _rank_goto
            st.info(f"🚀 Đang chạy phân tích **{_rank_goto}**")
            run_scan = True
            st.session_state.rank_goto_coin = None
            st.session_state.rank_step = None
        elif _scan_from_gainer:
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
        now = system_now()
        default_start = now - timedelta(days=30)

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            start_date = st.date_input("Từ", value=default_start)
        with col_d2:
            end_date = st.date_input("Đến", value=now)

        # --- Advanced config (collapsed) ---
        with st.expander("⚙️ Nâng cao", expanded=False):
            db_path = st.text_input("Cơ sở dữ liệu", value="./data/dev.duckdb")
            artifact_dir = st.text_input("Thư mục lưu trữ", value="./artifacts")
            hypothesis_id = st.text_input("Mã giả thuyết", value="hyp_dashboard_001")
            baseline_model = st.selectbox("Loại AI", ["logreg_walkforward", "dummy"])
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

        # --- Action buttons (context-aware) ---
        st.markdown("---")
        if _app_mode == "🚨 Cảnh báo":
            if _rank_step == "step2" and _rank_goto:
                st.warning(f"⏳ Đang phân tích {_rank_goto} tự động...")
                run_scan = True
            else:
                run_scan = st.button("🔍 Phát hiện xả", type="primary", use_container_width=True)
            run_bt = False
        else:
            run_bt = st.button("🚀 Chạy Backtest (kiểm tra lịch sử)", type="primary", use_container_width=True)
    else:
        # Defaults for non-symbol modes
        now = system_now()
        default_start = now - timedelta(days=30)
        start_date = default_start
        end_date = now
        db_path = "./data/dev.duckdb"
        artifact_dir = "./artifacts"
        hypothesis_id = "hyp_dashboard_001"
        baseline_model = "logreg_walkforward"
        seed = 42
        run_scan = False
        run_bt = False
        _downloaded = {}

    # --- Scanner status + watchlist (hidden in focused coin view) ---
    if not (_focus_mode and _focus_coin):
        st.markdown("---")
        st.markdown("**📡 Bộ quét tự động**")
        try:
            _scan_settings = AppSettings()
            # Detect scanner running via heartbeat file
            _heartbeat_path = Path(_scan_settings.paths.data_dir) / "scanner_heartbeat.json"
            _is_running = False
            _cycle_info = ""
            _hb_scan_mode = ""
            if _heartbeat_path.exists():
                try:
                    _hb = _json.loads(_heartbeat_path.read_text(encoding="utf-8"))
                    _hb_time = datetime.fromisoformat(_hb["timestamp"])
                    _max_age = timedelta(minutes=_hb.get("poll_minutes", 5) * 2 + 5)
                    if _hb_time.tzinfo is None:
                        _hb_time = _hb_time.replace(tzinfo=SYSTEM_TIMEZONE)
                    if _hb.get("status") == "running" and system_now() - _hb_time < _max_age:
                        _is_running = True
                        _cycle_info = f" (chu kỳ #{_hb.get('cycle', '?')})"
                        _hb_scan_mode = _hb.get("scan_mode", "")
                except Exception:
                    pass
            _scan_status = "🟢 Đang chạy" if _is_running else "⚪ Tắt"
            st.caption(f"Trạng thái: {_scan_status}{_cycle_info}")
            _sc1, _sc2 = st.columns(2)
            with _sc1:
                st.caption(f"Chu kỳ: {_scan_settings.scanner.poll_interval_minutes} phút")
                st.caption(f"Mode: {_scan_settings.scanner.scan_mode}")
            with _sc2:
                st.caption(f"Số coin: {_scan_settings.scanner.max_coins}")
                st.caption(f"Min change: {_scan_settings.scanner.min_price_change_pct}%")
            if _scan_settings.telegram.bot_token:
                st.caption("Telegram: ✅ đã cấu hình")

            # --- Watchlist management (compact) ---
            with st.expander("📋 Danh sách theo dõi", expanded=False):
                from dao_vang.scanner.watchlist import (
                    add_to_watchlist as _wl_add,
                )
                from dao_vang.scanner.watchlist import (
                    load_manual_watchlist as _wl_load,
                )
                from dao_vang.scanner.watchlist import (
                    remove_from_watchlist as _wl_remove,
                )

                _wl_path = _scan_settings.scanner.watchlist_path
                _wl_symbols = _wl_load(_wl_path)
                if _wl_symbols:
                    st.caption(f"{len(_wl_symbols)} coin đang theo dõi:")
                    # Show as removable list
                    for _wl_sym in _wl_symbols:
                        _wl_c1, _wl_c2 = st.columns([4, 1])
                        with _wl_c1:
                            st.caption(f"  • {_wl_sym}")
                        with _wl_c2:
                            if st.button("✕", key=f"rm_wl_{_wl_sym}", help=f"Xóa {_wl_sym}"):
                                _wl_remove(_wl_path, _wl_sym)
                                st.rerun()
                else:
                    st.caption("Chưa có coin nào trong danh sách theo dõi.")

                _wl_new = st.text_input(
                    "Thêm coin",
                    placeholder="VD: BTCUSDT, ETHUSDT...",
                    key="wl_add_input",
                ).strip().upper()
                if st.button("➕ Thêm", key="wl_add_btn", use_container_width=True) and _wl_new:
                    _wl_add(_wl_path, _wl_new)
                    st.success(f"Đã thêm {_wl_new}")
                    st.rerun()

            # --- Scan list preview ---
            with st.expander("🔍 Xem trước danh sách quét", expanded=False):
                from dao_vang.scanner.watchlist import (
                    preview_scan_list as _preview_scan,
                )

                _scan_mode_vi = {
                    "gainers": "📈 Top tăng mạnh",
                    "losers": "📉 Top giảm mạnh",
                    "volume": "📊 Top khối lượng",
                    "volatile": "⚡ Top biến động",
                    "all": "🌐 Kết hợp tất cả",
                }
                st.caption(f"Mode: {_scan_mode_vi.get(_scan_settings.scanner.scan_mode, _scan_settings.scanner.scan_mode)}")
                if st.button("🔄 Tải xem trước", key="preview_scan_btn"):
                    with st.spinner("Đang tải dữ liệu từ Binance..."):
                        try:
                            _preview = _preview_scan(_scan_settings.scanner)
                            st.success(f"Sẽ quét {_preview['total_count']} coin:")
                            # Show top 10 auto tickers
                            if _preview["auto_tickers_top10"]:
                                st.caption("**Top 10 coin tự động:**")
                                _preview_data = []
                                for d in _preview["auto_tickers_top10"]:
                                    _preview_data.append({
                                        "Coin": d["symbol"],
                                        "Thay đổi 24h": f"{d['change_pct']:+.2f}%",
                                        "Volume": f"${d['volume_usd']:,.0f}",
                                        "Giá": f"${d['last_price']:.6f}",
                                    })
                                st.dataframe(pd.DataFrame(_preview_data), use_container_width=True, hide_index=True)
                            # Show final list
                            st.caption(f"**Danh sách cuối cùng ({len(_preview['final_list'])} coin):**")
                            st.text(", ".join(_preview["final_list"][:20]) + ("..." if len(_preview["final_list"]) > 20 else ""))
                        except Exception as _preview_exc:
                            st.error(f"Lỗi: {_preview_exc}")
        except Exception:
            st.caption("⬜ Bộ quét: chưa cấu hình")


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
# Core: tính xác suất + mức nguy cơ + so sánh mốc cho BTCUSDT
# ============================================================
with _detect_container:
    _in_focus = st.session_state.get("focus_mode", False) and bool(st.session_state.get("focus_coin"))

    # --- Focused coin report header ---
    if _in_focus:
        _fc_col1, _fc_col2 = st.columns([5, 1])
        with _fc_col1:
            st.markdown(f"## 📊 {symbol}")
        with _fc_col2:
            if st.button("← Xếp hạng", use_container_width=True, key="focus_back_main"):
                st.session_state.focus_mode = False
                st.session_state.focus_coin = None
                st.session_state.focus_run_scan = False
                st.session_state.active_tab = "🏆 Xếp Hạng"
                st.rerun()
        st.caption("Báo cáo phân tích tập trung — chỉ hiển thị dữ liệu của coin này.")
    else:
        # --- Quy tắc gán nhãn (normal mode only) ---
        _ls_c1, _ls_c2 = st.columns(2)
        _ls_c1.metric("Coin", symbol, help="Coin đang chọn ở thanh bên")
        _ls_c2.metric("Dự báo", "24h", help=_glossary_tooltip("Horizon"))
        _ls_c3, _ls_c4 = st.columns(2)
        _ls_c3.metric("Giảm mục tiêu", "≥8%", help=_glossary_tooltip("Target Drawdown"))
        _ls_c4.metric("Biên tăng tối đa", "≤4%", help=_glossary_tooltip("MAE"))

    # ============================================================
    # DEFAULT ANALYSIS — tự động hiện khi có mã coin (không cần bấm nút)
    # ============================================================
    if not run_scan and symbol:
        from dao_vang.scoring import classify_btc as _db_classify_btc
        from dao_vang.scoring import compute_distribution_score as _db_compute_score

        _da_settings = AppSettings()
        _da_scoring_cfg = _da_settings.scoring
        _da_signal_vi = {
            "price_volume_divergence": "Phân kỳ giá-khối lượng",
            "funding_spike": "Funding tăng vọt",
            "momentum_exhaustion": "Động lượng cạn kiệt",
            "distance_from_high": "Khoảng cách từ đỉnh",
            "taker_sell_pressure": "Áp lực bán chủ động",
            "oi_divergence": "Phân kỳ OI",
            "btc_context": "Bối cảnh BTC",
            "fake_breakout": "Phá vỡ giả (bẫy FOMO)",
        }
        _da_rec_vi = {
            "SHORT_CANDIDATE": "🚨 Ứng viên bán",
            "WATCH": "⚠️ Theo dõi",
            "WAIT": "⏸️ Chờ",
        }
        _da_btc_vi = {
            "FOMO": "🔴 FOMO (BTC đang pump mạnh)",
            "NEUTRAL": "🟡 Trung tính (BTC đi ngang)",
            "WEAK": "🟢 Yếu (BTC đang giảm)",
        }

        if not _in_focus:
            st.markdown(f"#### 📊 Phân tích nhanh: {symbol}")
            st.caption(
                "Tự động phân tích từ dữ liệu đã có. Bấm **🔍 Phát hiện xả** ở thanh bên "
                "để chạy AI đầy đủ (thu thập + huấn luyện + dự đoán)."
            )

        # --- 1. Distribution Score từ DB scanner ---
        _da_has_score = False
        _da_score = None
        _da_btc_ctx = None
        try:
            _da_db = DuckDBQueryLayer(str(_da_settings.scanner.db_path))

            # BTC context
            _da_btc_df = _da_db.conn.execute(
                "SELECT * FROM feature_results WHERE symbol='BTCUSDT' "
                "ORDER BY feature_time DESC LIMIT 1"
            ).df()
            if not _da_btc_df.empty:
                _da_btc_row = _da_btc_df.iloc[-1]
                _da_btc_ctx = _db_classify_btc(
                    btc_ret_24h=float(_da_btc_row.get("price_ret_24h", 0.0)),
                    btc_ret_4h=float(_da_btc_row.get("price_ret_4h", 0.0)),
                    btc_ret_1h=float(_da_btc_row.get("price_ret_5m", 0.0)),
                    config=_da_scoring_cfg,
                )

            # Coin features
            _da_coin_df = _da_db.conn.execute(
                "SELECT * FROM feature_results WHERE symbol = ? "
                "ORDER BY feature_time DESC LIMIT 1",
                [symbol],
            ).df()
            if not _da_coin_df.empty:
                _da_row = _da_coin_df.iloc[-1]
                _da_feat_dict = {
                    k: v for k, v in _da_row.to_dict().items() if pd.notna(v)
                }
                _da_score = _db_compute_score(
                    symbol=symbol,
                    features=_da_feat_dict,
                    btc=_da_btc_ctx or _db_classify_btc(0.0, 0.0, 0.0, _da_scoring_cfg),
                    config=_da_scoring_cfg,
                )
                _da_has_score = True
        except Exception as _da_exc:
            st.caption(f"⬜ Chưa có dữ liệu phân tích cho {symbol}: {_da_exc}")
        finally:
            try:
                _da_db.conn.close()
            except Exception:
                pass

        if _da_has_score and _da_score:
            # --- Score header ---
            _da_rec = _da_rec_vi.get(_da_score.recommendation, _da_score.recommendation)
            _da_btc_label = _da_btc_vi.get(_da_score.btc_regime, _da_score.btc_regime)

            _da_score_color = (
                "#ff4444" if _da_score.total_score >= 70
                else "#ffaa00" if _da_score.total_score >= 50
                else "#44aa44"
            )
            if _in_focus:
                # Focused layout: full-width score card, compact metrics below
                st.markdown(
                    f"<div style='text-align:center;padding:14px;border-radius:10px;"
                    f"background:{_da_score_color};color:white;margin-bottom:10px;'>"
                    f"<h1 style='margin:0;font-size:2.2rem;'>{_da_score.total_score:.0f}/100</h1>"
                    f"<p style='margin:4px 0 0 0;font-size:1.1rem;'>{_da_rec}</p></div>",
                    unsafe_allow_html=True,
                )
                _da_m1, _da_m2, _da_m3 = st.columns(3)
                _da_m1.metric("Bối cảnh BTC", _da_btc_label.split(" ")[0] if _da_btc_label else "—")
                if _da_btc_ctx:
                    _da_m2.metric("BTC 24h", f"{_da_btc_ctx.btc_ret_24h:+.1%}")
                if _da_score.pump_pct > 0:
                    _da_m3.metric("Pump", f"+{_da_score.pump_pct:.0%}", f"{_da_score.pump_days} ngày")
                else:
                    _da_m3.metric("Pump", "—", "không có")
            else:
                _da_h1, _da_h2, _da_h3 = st.columns([2, 2, 2])
                with _da_h1:
                    st.markdown(
                        f"<div style='text-align:center;padding:10px;border-radius:8px;"
                        f"background:{_da_score_color};color:white;'>"
                        f"<h2 style='margin:0;'>{_da_score.total_score:.0f}/100</h2>"
                        f"<p style='margin:0;'>{_da_rec}</p></div>",
                        unsafe_allow_html=True,
                    )
                with _da_h2:
                    st.metric("Bối cảnh BTC", _da_btc_label.split(" ")[0] if _da_btc_label else "—")
                    if _da_btc_ctx:
                        st.caption(f"24h: {_da_btc_ctx.btc_ret_24h:+.1%}")
                with _da_h3:
                    if _da_score.pump_pct > 0:
                        st.metric("Pump", f"+{_da_score.pump_pct:.0%}", f"{_da_score.pump_days} ngày")
                    else:
                        st.metric("Pump", "—", "không có")

            st.markdown("---")

            # --- 8 signal breakdown ---
            st.markdown("##### 🔬 Chi tiết 8 tín hiệu")
            for _da_comp in _da_score.components:
                _da_label = _da_signal_vi.get(_da_comp.name, _da_comp.name.replace("_", " ").title())
                _da_pct = _da_comp.score / 100.0
                _da_col1, _da_col2 = st.columns([3, 1])
                with _da_col1:
                    st.markdown(f"**{_da_label}** — {_da_comp.score:.0f}/100 "
                                f"(trọng số {_da_comp.weight:.0%})")
                    st.progress(_da_pct, text=_da_comp.explanation)
                with _da_col2:
                    st.caption(f"Giá trị thực:\n`{_da_comp.raw_value}`")

            # --- BTC context detail ---
            if _da_btc_ctx:
                st.markdown("---")
                st.markdown(f"**Bối cảnh BTC:** {_da_btc_label}")
                st.caption(_da_btc_ctx.explanation)

            # --- Latest price ---
            try:
                _da_price_df = _da_db.conn.execute(
                    "SELECT feature_time, close, volume_base FROM feature_results "
                    "WHERE symbol = ? ORDER BY feature_time DESC LIMIT 1",
                    [symbol],
                ).df()
                if not _da_price_df.empty:
                    _da_prow = _da_price_df.iloc[-1]
                    st.markdown("---")
                    _da_pc1, _da_pc2 = st.columns(2)
                    with _da_pc1:
                        st.metric("Giá đóng gần nhất", f"${float(_da_prow['close']):,.6f}")
                    with _da_pc2:
                        st.metric("Thời gian", str(_da_prow["feature_time"])[:19])

                    # --- Focused mini price chart ---
                    if _in_focus:
                        _focus_klines = _fetch_recent_klines(symbol, "1h", 72)
                        if _focus_klines:
                            _focus_kdf = pd.DataFrame(_focus_klines)
                            st.markdown("##### 📈 Biểu đồ giá 72h")
                            st.line_chart(_focus_kdf.set_index("time")[["close"]], use_container_width=True, height=220)
            except Exception:
                pass

        else:
            st.info(
                f"⬜ Chưa có dữ liệu đặc trưng cho **{symbol}** trong database. "
                "Bấm **🔍 Phát hiện xả** ở thanh bên để thu thập dữ liệu + chạy AI. "
                "Hoặc chạy `dao-vang scanner start` để bộ quét 24/7 thu thập tự động."
            )

        # --- Pump filter check ---
        if _in_focus:
            with st.expander("🚀 Kiểm tra pump", expanded=False):
                st.caption("Quét nhanh: coin có tăng 50-500% trong 1-5 ngày không?")
                try:
                    from dao_vang.scanner.pump_filter import (
                        scan_pumps as _da_scan_pumps,
                    )

                    _da_pump_cfg = _da_settings.pump_filter
                    _da_pumps = _da_scan_pumps(_da_pump_cfg, [symbol])
                    if _da_pumps:
                        _da_p = _da_pumps[0]
                        _da_pc1, _da_pc2 = st.columns(2)
                        _da_pc1.metric("Pump", f"+{_da_p.pump_pct:.0%}")
                        _da_pc2.metric("Thời gian", f"{_da_p.pump_days} ngày")
                        _da_pc3, _da_pc4 = st.columns(2)
                        _da_pc3.metric("Vs đỉnh", f"{_da_p.current_vs_peak:.0%}")
                        _da_pc4.metric("Volume 24h", f"${_da_p.quote_volume:,.0f}")
                        if _da_p.current_vs_peak < 0.7:
                            st.warning("⚠️ Coin đã xả (>30% từ đỉnh) — có thể đã qua cơ hội short.")
                        else:
                            st.success(f"✅ Coin vẫn gần đỉnh ({_da_p.current_vs_peak:.0%}) — chưa xả, đang là ứng viên short.")
                    else:
                        st.caption(f"⬜ {symbol} không đạt ngưỡng pump (≥{_da_pump_cfg.min_pump_pct:.0%} trong 1-5 ngày).")
                except Exception as _da_pump_exc:
                    st.caption(f"⬜ Không kiểm tra được pump: {_da_pump_exc}")
        else:
            st.markdown("---")
            st.markdown("##### 🚀 Kiểm tra pump")
            st.caption("Quét nhanh: coin có tăng 50-500% trong 1-5 ngày không? (Nguyên lý: tăng đột biến → sụt đột biến)")
            try:
                from dao_vang.scanner.pump_filter import scan_pumps as _da_scan_pumps

                _da_pump_cfg = _da_settings.pump_filter
                _da_pumps = _da_scan_pumps(_da_pump_cfg, [symbol])
                if _da_pumps:
                    _da_p = _da_pumps[0]
                    _da_pc1, _da_pc2 = st.columns(2)
                    _da_pc1.metric("Pump", f"+{_da_p.pump_pct:.0%}")
                    _da_pc2.metric("Thời gian", f"{_da_p.pump_days} ngày")
                    _da_pc3, _da_pc4 = st.columns(2)
                    _da_pc3.metric("Vs đỉnh", f"{_da_p.current_vs_peak:.0%}")
                    _da_pc4.metric("Volume 24h", f"${_da_p.quote_volume:,.0f}")
                    if _da_p.current_vs_peak < 0.7:
                        st.warning("⚠️ Coin đã xả (>30% từ đỉnh) — có thể đã qua cơ hội short.")
                    else:
                        st.success(f"✅ Coin vẫn gần đỉnh ({_da_p.current_vs_peak:.0%}) — chưa xả, đang là ứng viên short.")
                else:
                    st.caption(f"⬜ {symbol} không đạt ngưỡng pump (≥{_da_pump_cfg.min_pump_pct:.0%} trong 1-5 ngày). Không phải ứng viên short theo nguyên lý 'tăng đột biến → sụt đột biến'.")
            except Exception as _da_pump_exc:
                st.caption(f"⬜ Không kiểm tra được pump: {_da_pump_exc}")

        # --- Data availability ---
        if _in_focus:
            with st.expander("📦 Dữ liệu đã tải", expanded=False):
                if symbol in _downloaded:
                    _da_sym_data = _downloaded[symbol]
                    _da_dtype_names = {
                        "klines": "Nến 5m", "funding": "Funding Rate",
                        "open_interest": "Open Interest", "taker_ratio": "Taker Volume",
                        "global_ratio": "Global L/S", "top_ratio": "Top L/S",
                    }
                    for _da_dt in ["klines", "funding", "open_interest", "taker_ratio", "global_ratio", "top_ratio"]:
                        if _da_dt in _da_sym_data:
                            _da_d = _da_sym_data[_da_dt]
                            st.caption(f"✅ {_da_dtype_names.get(_da_dt, _da_dt)}: {_da_d['rows']:,} dòng")
                        else:
                            st.caption(f"⬜ {_da_dtype_names.get(_da_dt, _da_dt)}: chưa có")
                else:
                    st.caption(f"⬜ Chưa có dữ liệu tải cho {symbol}.")
        else:
            st.markdown("##### 📦 Dữ liệu đã tải")
            if symbol in _downloaded:
                _da_sym_data = _downloaded[symbol]
                _da_dtype_names = {
                    "klines": "Nến 5m",
                    "funding": "Funding Rate",
                    "open_interest": "Open Interest",
                    "taker_ratio": "Taker Volume",
                    "global_ratio": "Global L/S",
                    "top_ratio": "Top L/S",
                }
                _da_dc1, _da_dc2 = st.columns(2)
                with _da_dc1:
                    for _da_dt in ["klines", "funding", "open_interest"]:
                        if _da_dt in _da_sym_data:
                            _da_d = _da_sym_data[_da_dt]
                            st.caption(f"✅ {_da_dtype_names.get(_da_dt, _da_dt)}: {_da_d['rows']:,} dòng")
                        else:
                            st.caption(f"⬜ {_da_dtype_names.get(_da_dt, _da_dt)}: chưa có")
                with _da_dc2:
                    for _da_dt in ["taker_ratio", "global_ratio", "top_ratio"]:
                        if _da_dt in _da_sym_data:
                            _da_d = _da_sym_data[_da_dt]
                            st.caption(f"✅ {_da_dtype_names.get(_da_dt, _da_dt)}: {_da_d['rows']:,} dòng")
                        else:
                            st.caption(f"⬜ {_da_dtype_names.get(_da_dt, _da_dt)}: chưa có")
            else:
                st.caption(f"⬜ Chưa có dữ liệu tải cho {symbol}. Bấm **🔍 Phát hiện xả** để thu thập.")

        # --- Hint to run full AI (normal mode only) ---
        if not _in_focus:
            st.info(
                "👉 Muốn chạy AI đầy đủ (thu thập + huấn luyện + dự đoán 12 nến + so sánh với mốc)? "
                "Bấm **🔍 Phát hiện xả** ở thanh bên trái."
            )

    if run_scan:
        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=SYSTEM_TIMEZONE)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=SYSTEM_TIMEZONE)
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
                    f"⚠️ Không có sự kiện phân phối nào trong dữ liệu {symbol}. "
                    "Thử coin biến động hơn hoặc khoảng thời gian dài hơn."
                )
                progress.empty()
            else:
                status.info("🧠 Đang huấn luyện AI + dự đoán...")
                progress.progress(90, text="Huấn luyện + Dự đoán")

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
                status.success(f"✅ Quét xong trong {t_pipe:.1f}s — {n_pos} sự kiện phân phối trong lịch sử")

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

                    c1, c2, c3 = st.columns(3)
                    c1.metric("Xác suất max", f"{max_prob:.1%}", help=_glossary_tooltip("Probability"))
                    c2.metric("🚨 CAO", len(high_risk), help=_glossary_tooltip("Risk Level"))
                    c3.metric("⚠️ TB", len(med_risk), help=_glossary_tooltip("Risk Level"))
                    c4, c5 = st.columns(2)
                    c4.metric("Chính xác", f"{model_metrics.get('precision', 0):.1%}", help=_glossary_tooltip("Precision"))
                    if _median_lead is not None:
                        c5.metric("Báo trước", f"~{_median_lead/60:.1f}h", f"{_median_lead:.0f} phút", help="Tín hiệu xuất hiện trước khi coin xả bao lâu")
                    else:
                        c5.metric("Báo trước", "—", help="Chưa đủ sự kiện xả để tính")

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
                        st.caption("Xác suất = % cơ hội coin xả trong 24h tới. Nguy cơ = phân loại dựa trên ngưỡng. Hết hạn = sau 24h cảnh báo mất giá trị.")
                        pred_df = pd.DataFrame(predictions)
                        pred_df["probability"] = pred_df["probability"].apply(lambda x: f"{x:.1%}")
                        pred_df["close"] = pred_df["close"].apply(lambda x: f"{x:.6f}" if x else "—")
                        pred_df["feature_time"] = pred_df["feature_time"].str[:19]
                        if "invalidation_time" in pred_df.columns:
                            pred_df["invalidation_time"] = pred_df["invalidation_time"].str[:19]
                            pred_df = pred_df[["feature_time", "symbol", "close", "probability", "risk_level", "invalidation_time"]]
                            pred_df.columns = ["Thời gian", "Coin", "Giá đóng", "Xác suất xả", "Nguy cơ", "Hết hạn"]
                        else:
                            pred_df = pred_df[["feature_time", "symbol", "close", "probability", "risk_level"]]
                            pred_df.columns = ["Thời gian", "Coin", "Giá đóng", "Xác suất xả", "Nguy cơ"]

                        def _risk_style(val):
                            colors = {"CAO": "#ff4444", "TRUNG BÌNH": "#ffaa00", "THẤP": "#44aa44", "RẤT THẤP": "#2266aa"}
                            c = colors.get(val, "")
                            return f"background-color: {c}; color: white" if c else ""

                        st.dataframe(
                            pred_df.style.map(_risk_style, subset=["Nguy cơ"]),
                            use_container_width=True,
                            hide_index=True,
                        )

                    with col_chart:
                        st.markdown("#### Xác suất xả theo thời gian")
                        chart_df = pd.DataFrame(predictions)
                        chart_df["feature_time"] = pd.to_datetime(chart_df["feature_time"])
                        chart_df = chart_df.set_index("feature_time")[["probability"]]
                        thresh = model_metrics.get("threshold", 0.5)
                        st.line_chart(chart_df)
                        st.caption(f"🔴 Ngưỡng cảnh báo = {thresh:.2f} — vượt đường này = AI báo sắp xả")

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
                        st.caption("ℹ️ Nếu biểu đồ trắng — coin chưa có trên TradingView. Bấm ô mã coin trên biểu đồ để đổi.")
                    else:
                        _scan_klines = _fetch_recent_klines(symbol, _scan_tf, 200)
                        if _scan_klines:
                            _skdf = pd.DataFrame(_scan_klines)
                            if _scan_chart_type == "🕯️ Nến":
                                import plotly.graph_objects as go
                                from plotly.subplots import make_subplots
                                _sfig = make_subplots(specs=[[{"secondary_y": True}]])
                                _sfig.add_trace(go.Candlestick(
                                    x=_skdf["time"],
                                    open=_skdf["open"],
                                    high=_skdf["high"],
                                    low=_skdf["low"],
                                    close=_skdf["close"],
                                    name=symbol,
                                ), secondary_y=False)

                                # Overlay probability on secondary y-axis
                                if predictions:
                                    _pred_df = pd.DataFrame(predictions)
                                    _pred_df["feature_time"] = pd.to_datetime(_pred_df["feature_time"])
                                    _sfig.add_trace(go.Scatter(
                                        x=_pred_df["feature_time"],
                                        y=_pred_df["probability"],
                                        mode="lines+markers",
                                        name="Xác suất xả",
                                        line=dict(color="#00ffcc", width=2, dash="dot"),
                                        marker=dict(size=6),
                                        hovertemplate="Xác suất: %{y:.1%}<br>Thời gian: %{x}<extra></extra>"
                                    ), secondary_y=True)

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
                                    ), secondary_y=False)
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
                                    ), secondary_y=False)
                                _sfig.update_layout(
                                    template="plotly_dark",
                                    height=450,
                                    margin=dict(l=0, r=0, t=30, b=0),
                                    xaxis_rangeslider_visible=False,
                                )
                                _sfig.update_yaxes(title_text="Giá", secondary_y=False)
                                _sfig.update_yaxes(title_text="Xác suất xả", tickformat=".0%", range=[0, 1.05], secondary_y=True)
                                st.plotly_chart(_sfig, use_container_width=True, config={"displayModeBar": False})
                                st.caption("🔻 Tam giác đỏ = dự đoán CAO | ◆ Cam = phân phối lịch sử | 🟢 Đứt nét = Xác suất xả")
                            else:  # Line
                                _sline_data = _skdf.set_index("time")[["close"]]
                                st.line_chart(_sline_data, use_container_width=True)
                        else:
                            st.warning(f"Không lấy được klines cho {symbol} ở khung {_scan_tf}")

                    # === Feature importance ===
                    top_feats = model_info.get("top_features", [])
                    if top_feats:
                        with st.expander("🔍 AI dựa vào yếu tố nào để quyết định?", expanded=False):
                            st.caption("Hệ số dương = yếu tố này tăng → xác suất xả tăng. Hệ số âm = ngược lại. Số lớn = ảnh hưởng mạnh.")
                            feat_df = pd.DataFrame(top_feats)
                            feat_df["coefficient"] = feat_df["coefficient"].apply(lambda x: f"{x:+.4f}")
                            feat_df.columns = ["Yếu tố", "Hệ số ảnh hưởng"]
                            st.dataframe(feat_df, use_container_width=True, hide_index=True)

                    # === Baseline comparison (core: có lợi thế thống kê?) ===
                    st.markdown("---")
                    st.markdown("#### ⚖️ AI tốt hơn 'mốc so sánh' không?")
                    st.caption("So sánh AI với cách đơn giản nhất (luôn báo sắp xả). AI phải GIỎI HƠN mới đáng dùng.")

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
                        st.metric("Độ chính xác", f"{_model_prec:.1%}", f"{_model_prec - _base_prec:+.1%} vs mốc so sánh", help=_glossary_tooltip("Precision"))
                    with _cmp_c2:
                        st.metric("Tỷ lệ bắt được", f"{_model_recall:.1%}", f"{_model_recall - _base_recall:+.1%} vs mốc so sánh", help=_glossary_tooltip("Recall"))
                    with _cmp_c3:
                        st.metric("Độ chuẩn xác", f"{_model_brier:.4f}", f"{_model_brier - _base_brier:+.4f} vs mốc (thấp hơn tốt hơn)", help=_glossary_tooltip("Brier Score"))

                    _cmp_df = pd.DataFrame([
                        {"Phương pháp": "AI (LogReg kiểm tra theo thời gian)", "Độ chính xác": _model_prec, "Tỷ lệ bắt được": _model_recall, "Độ chuẩn xác": _model_brier},
                        {"Phương pháp": "Luôn báo sắp xả (mốc)", "Độ chính xác": _base_prec, "Tỷ lệ bắt được": _base_recall, "Độ chuẩn xác": _base_brier},
                    ])
                    st.dataframe(
                        _cmp_df.style.format({"Độ chính xác": "{:.1%}", "Tỷ lệ bắt được": "{:.1%}", "Độ chuẩn xác": "{:.4f}"}),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.bar_chart(_cmp_df.set_index("Phương pháp")[["Độ chính xác", "Tỷ lệ bắt được"]])

                    if _model_prec > _base_prec and _model_prec > 0:
                        if _train_pos < 100:
                            st.warning(f"🟡 **CÓ TRIỂN VỌNG (thận trọng)** — AI chính xác {_model_prec:.1%} > đoán mò {_base_prec:.1%}, nhưng chỉ có {_train_pos} sự kiện xả trong data. Cần thêm dữ liệu để chắc chắn.")
                        else:
                            st.success(f"🟢 **AI TỐT HƠN MỐC SO SÁNH** — chính xác {_model_prec:.1%} > {_base_prec:.1%}. Tiếp tục kiểm chứng bằng Backtest + Forward Test.")
                    elif _model_prec > 0:
                        st.warning(f"🟡 **AI CHƯA TỐT HƠN MỐC SO SÁNH** — chính xác {_model_prec:.1%} ≤ {_base_prec:.1%}. Cần thêm đặc trưng hoặc sửa giả thuyết.")
                    else:
                        st.error("🔴 **AI KHÔNG HOẠT ĐỘNG** — chính xác = 0. Kiểm tra dữ liệu hoặc số sự kiện quá ít.")

                    st.caption(f"📌 Tần suất xả thật = {_prevalence:.1%} ({_train_pos}/{_train_size} nến có xả thật) | Ngưỡng cảnh báo = {_thresh:.2f}")

            db.conn.close()
        except Exception as e:
            status.error(f"❌ Lỗi: {str(e)}")
            progress.empty()


# ============================================================
# TAB 2: BACKTEST — đánh giá AI trên lịch sử (kiểm tra theo thời gian)
# ============================================================
with _backtest_container:
    st.caption("Chạy toàn bộ quy trình: thu thập dữ liệu → gán nhãn → tính đặc trưng → huấn luyện AI → so sánh với mốc → kiểm tra rò rỉ. Kết luận: AI có đáng dùng không?")

    if run_bt:
        start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=SYSTEM_TIMEZONE)
        end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=SYSTEM_TIMEZONE)
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
                    st.warning(f"🟡 **CÓ TRIỂN VỌNG (thận trọng)** — AI chính xác {model_p:.1%} > mốc {best_bp:.1%}, nhưng chỉ {n_pos} sự kiện xả. Cần thêm dữ liệu.")
                else:
                    _leak_vi = "✅ không rò rỉ" if leak_status == "passed" else f"⚠️ {leak_status}"
                    st.success(f"🟢 **AI ĐANG GIỎI HƠN** — chính xác {model_p:.1%} > mốc {best_bp:.1%}, {_leak_vi}")
            elif model_p > 0:
                st.warning(f"🟡 **AI CHƯA TỐT HƠN MỐC** — chính xác {model_p:.1%} ≤ mốc {best_bp:.1%}. Cần thêm đặc trưng hoặc sửa giả thuyết.")
            else:
                st.error("🔴 **AI KHÔNG HOẠT ĐỘNG** — tất cả chỉ số = 0. Có thể do quá ít sự kiện xả.")

            # === Results tabs ===
            tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
                "📈 Kết quả", "📊 So sánh", "🏷️ Nhãn", "🔍 Chất lượng", "📄 Báo cáo", "📖 Thuật ngữ"
            ])

            # --- Tab: Metrics ---
            with tab1:
                agg = results_data.get("aggregate", {})
                per_fold = results_data.get("per_fold", [])

                if agg:
                    # Compact metric row with tooltips (3 cols for mobile)
                    mc1, mc2, mc3 = st.columns(3)
                    mc1.metric("Chính xác", f"{agg.get('precision_mean', 0):.1%}",
                               f"±{agg.get('precision_std', 0):.4f}", help=_glossary_tooltip("Precision"))
                    mc2.metric("Bắt được", f"{agg.get('recall_mean', 0):.1%}",
                               f"±{agg.get('recall_std', 0):.4f}", help=_glossary_tooltip("Recall"))
                    mc3.metric("Chuẩn xác", f"{agg.get('brier_mean', 0):.4f}",
                               f"±{agg.get('brier_std', 0):.4f}", help=_glossary_tooltip("Brier Score"))

                    # Valid/skipped fold info
                    _nv = agg.get("n_valid_folds", 0)
                    _ns = agg.get("n_skipped_folds", 0)
                    if _nv > 0 or _ns > 0:
                        st.caption(f"✅ {_nv} lần kiểm tra hợp lệ | ⚪ {_ns} lần bỏ qua (thiếu sự kiện xả trong khoảng thời gian đó)")

                    # Confidence intervals
                    ci = agg.get("confidence_intervals", {})
                    if ci:
                        with st.expander("📊 Khoảng tin cậy 95% (bootstrap)", expanded=False):
                            st.caption("Khoảng này cho biết: nếu chạy lại nhiều lần, kết quả sẽ nằm trong phạm vi này 95% thời gian.")
                            ci_rows = []
                            for metric, vals in ci.items():
                                _metric_vi = {"precision": "Độ chính xác", "recall": "Tỷ lệ bắt được", "brier": "Độ chuẩn xác"}.get(metric, metric)
                                ci_rows.append({
                                    "Chỉ số": _metric_vi,
                                    "Giá trị": f"{vals.get('mean', 0):.4f}",
                                    "Tối thiểu (95%)": f"{vals.get('ci_lower', 0):.4f}",
                                    "Tối đa (95%)": f"{vals.get('ci_upper', 0):.4f}",
                                })
                            st.dataframe(pd.DataFrame(ci_rows), use_container_width=True, hide_index=True)

                    if per_fold:
                        st.markdown("#### Các lần kiểm tra (kiểm tra theo thời gian — huấn luyện quá khứ, kiểm tra tương lai)")
                        st.caption("Mỗi lần: train trên quá khứ → test trên tương lai. Train/Test = số nến (số sự kiện xả thật).")
                        fold_rows = []
                        for fold in per_fold:
                            row = {"Lần": fold.get("fold_idx", "?")}
                            if fold.get("skipped"):
                                row["Trạng thái"] = f"⚪ Bỏ qua: {fold.get('reason', '')}"
                            else:
                                m = fold.get("metrics", {})
                                row["Chính xác"] = f"{m.get('precision', 0):.1%}"
                                row["Bắt được"] = f"{m.get('recall', 0):.1%}"
                                row["Chuẩn xác"] = f"{m.get('brier', 0):.3f}"
                                row["Ngưỡng"] = f"{m.get('threshold', 0.5):.2f}"
                                row["Train"] = f"{fold.get('train_size', 0)} ({fold.get('train_positives', 0)} xả)"
                                row["Test"] = f"{fold.get('test_size', 0)} ({fold.get('test_positives', 0)} xả)"
                            fold_rows.append(row)
                        st.dataframe(pd.DataFrame(fold_rows), use_container_width=True, hide_index=True)

                    all_zero = all(v == 0 for v in agg.values() if isinstance(v, (int, float)))
                    if all_zero:
                        st.error("❌ Tất cả chỉ số = 0 — AI không học được. Có thể do quá ít sự kiện xả trong data.")
                else:
                    st.info("Không có kết quả.")

            # --- Tab: Baselines ---
            with tab2:
                baselines = results_data.get("baselines", {})
                if baselines:
                    st.caption("So sánh AI với các cách đơn giản. AI phải GIỎI HƠN cách tốt nhất mới đáng dùng.")
                    rows = [{"Phương pháp": "AI (LogReg)", "Độ chính xác": model_p, "Tỷ lệ bắt được": agg.get("recall_mean", 0), "Độ chuẩn xác": agg.get("brier_mean", 0)}]
                    _baseline_names_vi = {
                        "B0_random": "Ngẫu nhiên",
                        "B1_price_ret_0.0": "Giá giảm bất kỳ",
                        "B1_price_ret_0.02": "Giá giảm ≥2%",
                        "B1_price_ret_0.05": "Giá giảm ≥5%",
                        "B2_funding_0.5": "Funding ≥50%",
                        "B2_funding_0.8": "Funding ≥80%",
                        "B2_funding_0.9": "Funding ≥90%",
                    }
                    for name, m in baselines.items():
                        _vn = _baseline_names_vi.get(name, name)
                        rows.append({"Phương pháp": _vn, "Độ chính xác": m.get("precision_mean", 0), "Tỷ lệ bắt được": m.get("recall_mean", 0), "Độ chuẩn xác": m.get("brier_mean", 0)})
                    df_comp = pd.DataFrame(rows)
                    st.dataframe(
                        df_comp.style.format({"Độ chính xác": "{:.1%}", "Tỷ lệ bắt được": "{:.1%}", "Độ chuẩn xác": "{:.4f}"}),
                        use_container_width=True, hide_index=True,
                    )
                    st.bar_chart(df_comp.set_index("Phương pháp")[["Độ chính xác", "Tỷ lệ bắt được"]])

                    if model_p > best_bp:
                        st.success(f"✅ AI tốt hơn mốc tốt nhất (chính xác {model_p:.1%} > {best_bp:.1%})")
                    else:
                        st.warning(f"⚠️ AI chưa tốt hơn mốc tốt nhất (chính xác {model_p:.1%} ≤ {best_bp:.1%})")
                else:
                    st.info("Không có mốc so sánh.")

            # --- Tab: Labels ---
            with tab3:
                st.caption("Xả (1) = giảm ≥8%/24h, tăng ≤4% trước khi giảm. (0) = không xả.")
                c1, c2 = st.columns(2)
                c1.metric("Tổng nến", f"{n_total:,}")
                c2.metric("Xả (1)", n_positive, help=_glossary_tooltip("Phân phối"))
                c3, c4 = st.columns(2)
                c3.metric("Bình thường (0)", f"{n_negative:,}")
                c4.metric("Loại trừ", n_excluded, help="Nến không đủ data 24h tới.")

                chart_data = pd.DataFrame({
                    "Nhãn": ["Coin xả", "Bình thường", "Loại trừ"],
                    "Số lượng": [n_positive, n_negative, n_excluded],
                })
                st.bar_chart(chart_data.set_index("Nhãn"))

                if n_positive == 0:
                    st.warning("⚠️ Không có sự kiện xả nào. Thử coin biến động hơn hoặc khoảng thời gian dài hơn.")
                elif n_positive < 50:
                    st.warning(f"⚠️ Chỉ {n_positive} sự kiện xả — quá ít để AI học tốt. Cần thêm dữ liệu.")

            # --- Tab: Quality ---
            with tab4:
                dq = results_data.get("data_quality", {})
                leak = results_data.get("leakage_report", {})
                lt = results_data.get("lead_time_stats", {})

                st.caption("Rò rỉ dữ liệu = AI vô tình 'nhìn trộm' tương lai (như coi trước đáp án). Phải PASS mới dùng được.")
                leak_status = leak.get("status", "unknown")
                if leak_status == "passed":
                    st.success("✅ Không phát hiện rò rỉ dữ liệu — AI không gian lận")
                else:
                    st.error(f"❌ Phát hiện rò rỉ: {leak.get('forbidden_columns', [])} — kết quả không đáng tin!")

                if dq:
                    qc1, qc2 = st.columns(2)
                    qc1.metric("Tổng nến", f"{dq.get('total_rows', 0):,}")
                    qc2.metric("Trùng lặp", dq.get("duplicate_count", 0))
                    qc3, qc4 = st.columns(2)
                    qc3.metric("Tần suất xả", f"{dq.get('label_distribution', {}).get('prevalence', 0):.1%}", help=_glossary_tooltip("Prevalence"))
                    qc4.metric("Số ngày", f"{dq.get('time_range', {}).get('duration_days', 0):.1f}")

                    nc = dq.get("null_counts", {})
                    if nc:
                        with st.expander("Dữ liệu thiếu (top cột bị null)", expanded=False):
                            st.caption("Null = không có dữ liệu cho cột này. Nhiều null = feature không dùng được (VD: Binance API không cho lịch sử).")
                            st.dataframe(
                                pd.DataFrame(list(nc.items()), columns=["Dữ liệu", "Số nến thiếu"]),
                                use_container_width=True, hide_index=True,
                            )

                # --- Lead time + invalidation ---
                if lt and lt.get("status") == "ok":
                    st.markdown("##### ⏱️ Cảnh báo trước bao lâu?")
                    st.caption("Từ tín hiệu đến khi coin xả. Số càng lớn = báo càng sớm. Hết hạn sau 24h.")
                    lc1, lc2 = st.columns(2)
                    lc1.metric("Trung bình", f"~{lt.get('median_hours', 0):.1f}h", f"{lt.get('median_minutes', 0):.0f} phút")
                    lc2.metric("P25–P75", f"{lt.get('p25_minutes', 0):.0f}–{lt.get('p75_minutes', 0):.0f} phút")
                    lc3, lc4 = st.columns(2)
                    lc3.metric("Min–Max", f"{lt.get('min_minutes', 0):.0f}–{lt.get('max_minutes', 0):.0f} phút")
                    lc4.metric("Hết hạn", f"{lt.get('horizon_minutes', 1440)} phút", "24h")
                    st.info(f"📊 {lt.get('summary', '')}")
                elif lt and lt.get("status") == "no_positive_labels":
                    st.markdown("---")
                    st.markdown("##### ⏱️ Cảnh báo trước bao lâu?")
                    st.warning("Không có sự kiện xả trong data — không tính được thời gian cảnh báo trước.")

            # --- Tab: Report ---
            with tab5:
                with st.expander("📄 Markdown Report", expanded=True):
                    st.markdown(md_content)
                with st.expander("📋 Log", expanded=False):
                    st.code("\n".join(log_lines), language="text")

            # --- Tab: Glossary ---
            with tab6:
                _render_glossary_tab(key_prefix="glossary_bt")

            db.conn.close()
        except Exception as e:
            status.error(f"❌ Lỗi: {str(e)}")
            progress.empty()

    # Idle state for detect tab
    if not run_scan:
        st.markdown("""
        ### 🎯 Phát hiện xả phân phối

        **Mục tiêu:** Phát hiện sớm coin có nguy cơ cao sắp xả (giảm mạnh).

        **Cách dùng:**
        1. Chọn mã coin ở thanh bên (mặc định **BTCUSDT**)
        2. Chọn khoảng thời gian (mặc định 30 ngày)
        3. Bấm **"🔍 Phát hiện xả"** ở thanh bên

        App sẽ: thu thập dữ liệu → tính toán → huấn luyện AI → dự đoán xác suất xả trên 12 nến mới nhất → so sánh AI với 'đoán mò'.
        """)


# ============================================================
# IDLE STATE — Backtest tab instructions
# ============================================================
with _backtest_container:
    if not run_bt:
        st.markdown("""
        ### 🧪 Backtest — Đánh giá AI trên lịch sử

        **Cách dùng:**
        1. Chọn mã coin + khoảng thời gian ở thanh bên
        2. Bấm **"🚀 Chạy Backtest"** ở thanh bên

        App sẽ chạy 5 bước: thu thập → chuẩn hóa → gán nhãn → tính đặc trưng → huấn luyện AI.
        Kết quả: AI có chính xác không? Có giỏi hơn 'đoán mò' không? Có 'gian lận' (rò rỉ dữ liệu) không?
        """)


# ============================================================
# TAB: FORWARD TEST — đóng băng model → chấm điểm trên dữ liệu mới
# ============================================================
with _detect_container:
    st.markdown("### 🔒 Forward Test — kiểm tra tiến lên")
    st.caption(
        "Đóng băng model (khóa code + cấu hình + ngưỡng) → chấm điểm trên dữ liệu MỚI sinh ra SAU khi đóng băng. "
        "Kiểm tra độ ổn định thực tế trước khi dùng thật. Model không vượt mốc so sánh trong forward test → không triển khai."
    )

    from dao_vang.experiments.forward_test import (
        evaluate_frozen,
    )
    from dao_vang.experiments.forward_test import (
        freeze_model as _freeze_model,
    )
    from dao_vang.experiments.forward_test import (
        list_frozen_models as _list_frozen,
    )

    _ft_c1, _ft_c2 = st.columns(2)
    with _ft_c1:
        if st.button("🔒 Đóng băng model hiện tại", help="Huấn luyện AI trên tất cả dữ liệu đã có nhãn, khóa ngưỡng, lưu model + metadata. Data sau mốc cắt = dữ liệu forward test."):
            try:
                import numpy as _np
                from sklearn.linear_model import LogisticRegression as _LR

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
                    st.warning("Cần ít nhất 200 dòng dữ liệu đã có nhãn. Chạy Backtest trước để tạo đặc trưng + nhãn.")
                elif _ft_df["is_distribution"].nunique() < 2:
                    st.warning("Cần cả 2 loại nhãn (có xả + không xả) trong dữ liệu.")
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
                    st.info(f"Mốc cắt: {_info.train_cutoff[:19]} | Ngưỡng: {_info.threshold:.4f} | Số đặc trưng: {len(_info.feature_cols)} | Dòng train: {len(_ft_df)} ({int(_ft_df['is_distribution'].sum())} xả)")
            except Exception as _e:
                st.error(f"❌ Lỗi đóng băng: {_e}")

    with _ft_c2:
        _frozen_models = _list_frozen(Path(artifact_dir))
        if not _frozen_models:
            st.info("Chưa có model nào đóng băng. Bấm **🔒 Đóng băng** để tạo.")
        else:
            st.markdown(f"**{len(_frozen_models)} model đã đóng băng (frozen):**")
            _fm_options = {f"{m.model_id}  (mốc cắt: {m.train_cutoff[:10]}, ngưỡng: {m.threshold:.3f})": m.model_id for m in _frozen_models}
            _sel_fm = st.selectbox("Chọn model để đánh giá forward test", options=list(_fm_options.keys()))
            _sel_id = _fm_options[_sel_fm]

            if st.button("📊 Chấm điểm forward test (kiểm tra tiến lên)", type="primary"):
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

                        st.markdown("#### Kết quả kiểm tra tiến lên")
                        _ftc1, _ftc2, _ftc3 = st.columns(3)
                        _ftc1.metric("Độ chính xác", f"{_ft_m['precision']:.4f}", f"{_ft_m['precision'] - _ft_tm['precision']:+.4f} vs lúc train", help=_glossary_tooltip("Precision"))
                        _ftc2.metric("Tỷ lệ bắt được", f"{_ft_m['recall']:.4f}", f"{_ft_m['recall'] - _ft_tm['recall']:+.4f} vs lúc train", help=_glossary_tooltip("Recall"))
                        _ftc3.metric("Độ chuẩn xác", f"{_ft_m['brier']:.4f}", help=_glossary_tooltip("Brier Score"))

                        st.info(f"📊 {_ft_result['summary']}")

                        # Drift alert
                        if _ft_drift["precision_drift"]:
                            st.error("🔴 **Phát hiện trôi dịch** — độ chính xác thay đổi >0.1 so với lúc train. Model có thể không còn ổn định.")
                        else:
                            st.success("✅ Không có trôi dịch đáng kể — model ổn định trong forward test.")

                        # Risk breakdown
                        _rb = _ft_result["risk_breakdown"]
                        if _rb:
                            st.markdown("##### Phân tích theo mức nguy cơ")
                            _rb_rows = []
                            for _lvl in ["CAO", "TRUNG BÌNH", "THẤP", "RẤT THẤP"]:
                                _d = _rb.get(_lvl, {})
                                _rb_rows.append({
                                    "Mức nguy cơ": _lvl,
                                    "Số tín hiệu": _d.get("n_signals", 0),
                                    "Thực xả": _d.get("n_actual_distribution", 0),
                                    "Độ chính xác": f"{_d.get('precision', 0):.4f}",
                                })
                            st.dataframe(pd.DataFrame(_rb_rows), use_container_width=True, hide_index=True)

                        st.caption(f"Dòng forward: {_ft_result['n_forward_rows']} | Xả thật: {_ft_result['n_positive_labels']} | AI báo xả: {_ft_result['n_predicted_positive']}")
                except Exception as _e:
                    st.error(f"❌ Lỗi kiểm tra tiến lên: {_e}")

# ============================================================
# TAB: TRỢ GIÚP — glossary + guide merged
# ============================================================
with _help_container:
    st.markdown("#### ❓ Trợ giúp")
    _help_tab1, _help_tab2 = st.tabs(["📖 Thuật ngữ", "🧭 Hướng dẫn"])
    with _help_tab1:
        _render_glossary_tab(key_prefix="glossary_help")
    with _help_tab2:
        _render_guide_tab(key_prefix="guide_help")
