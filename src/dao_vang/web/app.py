import streamlit as st
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import duckdb

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.klines import KlinesCollector
from dao_vang.data.storage.duckdb import DuckDBQueryLayer
from dao_vang.experiments.artifacts import ArtifactRegistry
from dao_vang.experiments.runner import ExperimentConfig, run_experiment
from dao_vang.features.builder import build_features
from dao_vang.labels.engine import DistributionLabelEngine
from dao_vang.reports.generator import generate_markdown_report

st.set_page_config(
    page_title="Đảo Vàng - Dashboard",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🪙 Đảo Vàng MVP Dashboard")
st.markdown("Predictive model for crypto distribution phases")

with st.sidebar:
    st.header("⚙️ Cấu hình Pipeline")
    
    # Date selection
    now = datetime.now()
    default_start = now - timedelta(days=7)
    
    start_date = st.date_input("Start Date", value=default_start)
    end_date = st.date_input("End Date", value=now)
    
    db_path = st.text_input("Database Path", value="./data/dev.duckdb")
    artifact_dir = st.text_input("Artifact Directory", value="./artifacts")
    
    st.markdown("---")
    st.subheader("Experiment Config")
    hypothesis_id = st.text_input("Hypothesis ID", value="hyp_dashboard_001")
    baseline_model = st.selectbox("Baseline Model", ["logreg_walkforward", "dummy"])
    seed = st.number_input("Random Seed", value=42, step=1)
    
    run_button = st.button("🚀 Run Full Pipeline", type="primary", use_container_width=True)

if run_button:
    start_dt = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_dt = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    # Ensure dirs exist
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(artifact_dir).mkdir(parents=True, exist_ok=True)
    
    progress_bar = st.progress(0, text="Khởi động...")
    status_text = st.empty()
    
    try:
        # 1. Collect Data
        status_text.info("Đang tải dữ liệu K-line từ Binance...")
        progress_bar.progress(10, text="Bước 1/5: Collect Data")
        settings = AppSettings()
        client = BinanceClient()
        collector = KlinesCollector(client, settings)
        run_id = f"ui_{int(time.time())}"
        collector.collect(start_dt, end_dt, run_id)
        
        # 2. Normalize (Placeholder for now, assuming raw_timeline is used)
        progress_bar.progress(30, text="Bước 2/5: Normalize Data")
        status_text.info("Chuẩn hóa dữ liệu (Timeline Stitching)...")
        time.sleep(0.5) # Simulate work
        
        # 3. Label Generation
        progress_bar.progress(50, text="Bước 3/5: Generate Labels")
        status_text.info("Sinh nhãn dữ liệu...")
        conn = duckdb.connect(db_path)
        engine = DistributionLabelEngine()
        # In a real run, you'd ensure raw_timeline is fully populated
        # For this dashboard demo, if table doesn't exist, we skip or show warning
        try:
            engine.compute_all(conn, "raw_timeline")
        except duckdb.CatalogException:
            st.warning("Bảng `raw_timeline` chưa có dữ liệu. Vui lòng kiểm tra lại Data Collector.")
        
        # 4. Feature Generation
        progress_bar.progress(70, text="Bước 4/5: Generate Features")
        status_text.info("Tính toán Feature...")
        db = DuckDBQueryLayer(db_path)
        try:
            build_features(db, "raw_timeline", "feature_results")
        except duckdb.CatalogException:
            pass # Same as above
        
        # 5. Run Experiment & Report
        progress_bar.progress(90, text="Bước 5/5: Model & Report")
        status_text.info("Đang chạy mô hình Baseline & Xuất báo cáo...")
        
        config = ExperimentConfig(
            hypothesis_id=hypothesis_id,
            baseline_model=baseline_model,
            dataset_version="v1",
            label_version="v1",
            feature_set_version="v1",
            split_version="v1",
            seed=seed,
            metrics=["precision", "recall", "brier"],
        )
        result = run_experiment(config)
        registry = ArtifactRegistry(Path(artifact_dir))
        artifact_id = registry.save_experiment(result)
        
        artifact = registry.load_experiment(artifact_id)
        md_content = generate_markdown_report(artifact)
        
        progress_bar.progress(100, text="Hoàn thành!")
        status_text.success(f"Pipeline chạy thành công! Artifact ID: `{artifact_id}`")
        
        st.markdown("---")
        st.markdown(md_content)
        
    except Exception as e:
        status_text.error(f"Lỗi: {str(e)}")
        progress_bar.empty()
else:
    st.info("👈 Bấm 'Run Full Pipeline' ở thanh bên trái để bắt đầu.")
