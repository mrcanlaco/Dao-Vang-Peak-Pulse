import streamlit as st
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import duckdb

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
from dao_vang.data.pipeline import process_raw_to_parquet, build_raw_timeline

st.set_page_config(
    page_title="Đảo Vàng - Dashboard",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🪙 Đảo Vàng MVP Dashboard")
st.markdown("Mô hình dự đoán các giai đoạn phân phối crypto")

with st.sidebar:
    st.header("⚙️ Cấu hình Pipeline")
    
    # Date selection
    now = datetime.now()
    default_start = now - timedelta(days=7)
    
    start_date = st.date_input("Ngày bắt đầu", value=default_start)
    end_date = st.date_input("Ngày kết thúc", value=now)
    
    db_path = st.text_input("Đường dẫn Database", value="./data/dev.duckdb")
    artifact_dir = st.text_input("Thư mục Artifact", value="./artifacts")
    symbol = st.text_input("Coin / Symbol", value="ETHUSDT").strip().upper()
    
    st.markdown("---")
    st.subheader("Cấu hình Thử nghiệm")
    hypothesis_id = st.text_input("ID Giả thuyết", value="hyp_dashboard_001")
    baseline_model = st.selectbox("Mô hình Cơ sở", ["logreg_walkforward", "dummy"])
    seed = st.number_input("Giá trị ngẫu nhiên (Seed)", value=42, step=1)
    
    run_button = st.button("🚀 Chạy toàn bộ quy trình", type="primary", use_container_width=True)

if run_button:
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Ensure dirs exist
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(artifact_dir).mkdir(parents=True, exist_ok=True)
    
    progress_bar = st.progress(0, text="Khởi động...")
    status_text = st.empty()
    
    t_start = time.perf_counter()
    
    try:
        # 1. Collect Data
        status_text.info("Đang tải dữ liệu K-line và các metrics từ Binance...")
        progress_bar.progress(10, text="Bước 1/5: Thu thập Dữ liệu")
        t0 = time.perf_counter()
        settings = AppSettings()
        settings.binance.symbol = symbol
        client = BinanceClient()
        run_id = f"ui_{int(time.time())}"
        
        KlinesCollector(client, settings).collect(start_dt, end_dt, run_id)
        FundingCollector(client, settings).collect(start_dt, end_dt, run_id)
        OpenInterestCollector(client, settings).collect(start_dt, end_dt, run_id)
        TakerRatioCollector(client, settings).collect(start_dt, end_dt, run_id)
        GlobalRatioCollector(client, settings).collect(start_dt, end_dt, run_id)
        TopRatioCollector(client, settings).collect(start_dt, end_dt, run_id)
        t1 = time.perf_counter()
        st.info(f"Bước 1/5: Thu thập dữ liệu từ Binance hoàn tất trong {t1 - t0:.2f}s")
        
        # 2. Normalize 
        progress_bar.progress(30, text="Bước 2/5: Chuẩn hóa Dữ liệu")
        status_text.info("Chuẩn hóa dữ liệu (Timeline Stitching)...")
        t0 = time.perf_counter()
        db = DuckDBQueryLayer(db_path)
        process_raw_to_parquet(settings)
        build_raw_timeline(db, settings)
        t1 = time.perf_counter()
        st.info(f"Bước 2/5: Chuẩn hóa dữ liệu vào DuckDB hoàn tất trong {t1 - t0:.2f}s")
        
        # 3. Label Generation
        progress_bar.progress(50, text="Bước 3/5: Sinh Nhãn")
        status_text.info("Đang tính nhãn phân phối...")
        t0 = time.perf_counter()
        engine = DistributionLabelEngine()
        label_results = engine.compute_all(db.conn, "raw_timeline")
        t1 = time.perf_counter()

        n_total = len(label_results)
        n_positive = sum(1 for r in label_results if r.label_value == 1)
        n_negative = sum(1 for r in label_results if r.label_value == 0)
        n_excluded = n_total - n_positive - n_negative
        status_text.info(
            f"Nhãn: {n_total} điểm, {n_positive} phân phối, {n_negative} bình thường, {n_excluded} loại trừ"
        )

        db.conn.execute("DROP TABLE IF EXISTS labels")
        db.conn.execute("CREATE TABLE labels (signal_time TIMESTAMP, symbol VARCHAR, label_value INTEGER)")
        db.conn.executemany(
            "INSERT INTO labels VALUES (?, ?, ?)",
            [(r.signal_time, r.symbol, r.label_value) for r in label_results],
        )

        st.info(
            f"**Bước 3/5 hoàn tất: Sinh nhãn ({t1 - t0:.2f}s).**\n\n"
            f"- **{n_total} điểm**: tổng số cây nến 5 phút trong khoảng thời gian đã chọn.\n"
            f"- **{n_positive} phân phối** (nhãn = 1): trong 24 giờ sau, giá sập từ 8% trở lên trước khi vượt mức tăng 4%.\n"
            f"- **{n_negative} bình thường** (nhãn = 0): giá không sập đủ 8% trong 24 giờ.\n"
            f"- **{n_excluded} loại trừ**: thiếu dữ liệu tương lai (gần cuối chuỗi) hoặc mẫu mơ hồ.\n\n"
            "Nếu **phân phối = 0**, dữ liệu bạn chọn không có đợt bán tháo đủ mạnh để mô hình học. "
            "Hãy thử coin biến động hơn hoặc khoảng thời gian dài hơn."
        )
        
        # 4. Feature Generation
        progress_bar.progress(70, text="Bước 4/5: Tính toán Đặc trưng")
        status_text.info("Đang tính toán feature (có thể mất vài phút với dữ liệu dài)...")
        t0 = time.perf_counter()
        build_features(db, "raw_timeline", "feature_results")
        t1 = time.perf_counter()

        row_count = db.conn.execute("SELECT count(*) FROM feature_results").fetchone()[0]
        col_count = db.conn.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = 'feature_results'"
        ).fetchone()[0]
        status_text.info(f"Feature: {row_count} dòng, {col_count} cột ({t1 - t0:.2f}s)")

        st.info(
            f"**Bước 4/5 hoàn tất: Tính feature ({t1 - t0:.2f}s).**\n\n"
            f"- **{row_count} dòng**: mỗi dòng là một cây nến 5 phút với các chỉ số kỹ thuật.\n"
            f"- **{col_count} cột**: tập hợp các đặc trưng từ giá, khối lượng, funding, open interest, "
            "taker volume và tỷ lệ long/short.\n\n"
            "Các cột này sẽ làm đầu vào cho mô hình logistic regression ở bước 5."
        )
        
        # 5. Run Experiment & Report
        progress_bar.progress(90, text="Bước 5/5: Mô hình & Báo cáo")
        status_text.info("Đang chạy mô hình Baseline & Xuất báo cáo...")
        t0 = time.perf_counter()
        
        config = ExperimentConfig(
            hypothesis_id=hypothesis_id,
            baseline_model=baseline_model,
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=seed,
            metrics=["precision", "recall", "brier"],
            db_path=db_path,
        )
        result = run_experiment(config)
        registry = ArtifactRegistry(Path(artifact_dir))
        artifact_id = registry.save_experiment(result)
        t1 = time.perf_counter()
        
        artifact = registry.load_experiment(artifact_id)
        md_content = generate_markdown_report(artifact)
        
        progress_bar.progress(100, text="Hoàn thành!")
        status_text.success(f"Pipeline chạy thành công! Artifact ID: `{artifact_id}`")
        st.info(f"Bước 5/5: Mô hình và báo cáo hoàn tất trong {t1 - t0:.2f}s")
        st.info(f"Tổng thời gian pipeline: {time.perf_counter() - t_start:.2f}s")
        
        st.markdown("---")
        st.markdown(md_content)
        
    except Exception as e:
        status_text.error(f"Lỗi: {str(e)}")
        progress_bar.empty()
else:
    st.info("👈 Bấm 'Chạy toàn bộ quy trình' ở thanh bên trái để bắt đầu.")
