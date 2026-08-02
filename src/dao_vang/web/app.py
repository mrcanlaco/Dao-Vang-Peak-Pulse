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
from dao_vang.data.pipeline import (
    process_raw_to_parquet,
    build_raw_timeline,
    get_incremental_start,
    scan_downloaded_data,
)

st.set_page_config(
    page_title="Đảo Vàng - Dashboard",
    page_icon="🪙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🪙 Đảo Vàng MVP Dashboard")
st.markdown("Mô hình dự đoán các giai đoạn phân phối crypto")

# --- Scan existing downloaded data ---
_data_dir_scan = Path("data")
_downloaded = scan_downloaded_data(_data_dir_scan)
_all_symbols = sorted(_downloaded.keys())

with st.sidebar:
    st.header("⚙️ Cấu hình Pipeline")

    # --- Symbol selection with data info ---
    st.subheader("📊 Chọn Mã Coin")

    if _all_symbols:
        # Build display labels with data summary
        _symbol_labels = {}
        for sym in _all_symbols:
            info = _downloaded.get(sym, {})
            dtypes = sorted(info.keys())
            klines_info = info.get("klines", {})
            date_range = ""
            if klines_info:
                date_range = f" ({klines_info['first_date']} → {klines_info['last_date']})"
            _symbol_labels[sym] = f"{sym}{date_range}"

        selected_label = st.selectbox(
            "Mã coin đã có dữ liệu",
            options=list(_symbol_labels.keys()),
            format_func=lambda s: _symbol_labels[s],
            help="Chọn mã coin từ dữ liệu đã tải. Chọn 'Nhập mã khác' để tải mã mới.",
        )
        symbol = selected_label

        # Allow entering a new symbol not yet downloaded
        use_custom = st.checkbox("Nhập mã khác (tải mới)")
        if use_custom:
            custom_symbol = st.text_input(
                "Mã coin mới", value="", placeholder="VD: SOLUSDT, DOGEUSDT..."
            ).strip().upper()
            if custom_symbol:
                symbol = custom_symbol
    else:
        st.info("Chưa có dữ liệu nào. Nhập mã coin để bắt đầu tải.")
        symbol = st.text_input(
            "Mã coin", value="BTCUSDT", placeholder="VD: BTCUSDT, ETHUSDT..."
        ).strip().upper()

    # --- Show downloaded data details for selected symbol ---
    if symbol and symbol in _downloaded:
        st.markdown("---")
        st.markdown(f"**📦 Dữ liệu đã tải: `{symbol}`**")
        sym_data = _downloaded[symbol]
        _dtype_names = {
            "klines": "Nến (K-lines 5m)",
            "funding": "Funding Rate",
            "open_interest": "Open Interest",
            "taker_ratio": "Taker Volume",
            "global_ratio": "Global Long/Short",
            "top_ratio": "Top Trader L/Short",
        }
        for dt in ["klines", "funding", "open_interest", "taker_ratio", "global_ratio", "top_ratio"]:
            if dt in sym_data:
                d = sym_data[dt]
                st.markdown(
                    f"- **{_dtype_names.get(dt, dt)}**: {d['rows']:,} dòng, "
                    f"{d['files']} file, {d['first_date']} → {d['last_date']}"
                )
            else:
                st.markdown(f"- ~~{_dtype_names.get(dt, dt)}~~: chưa có")
    elif symbol:
        st.markdown("---")
        st.warning(f"⚠️ Chưa có dữ liệu cho `{symbol}`. Sẽ tải mới khi bấm chạy.")

    st.markdown("---")

    # --- Date selection ---
    now = datetime.now()
    default_start = now - timedelta(days=7)

    start_date = st.date_input("Ngày bắt đầu", value=default_start)
    end_date = st.date_input("Ngày kết thúc", value=now)

    db_path = st.text_input("Đường dẫn Database", value="./data/dev.duckdb")
    artifact_dir = st.text_input("Thư mục Artifact", value="./artifacts")

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
    log_lines: list[str] = []
    
    def log(msg: str):
        log_lines.append(msg)
        
    t_start = time.perf_counter()
    
    try:
        # 1. Collect Data (incremental — skip already-downloaded data)
        status_text.info("📡 Bước 1/5: Đang tải dữ liệu từ Binance...")
        progress_bar.progress(10, text="Bước 1/5: Thu thập")
        t0 = time.perf_counter()
        settings = AppSettings()
        settings.binance.symbol = symbol
        client = BinanceClient()
        run_id = f"ui_{int(time.time())}"

        data_dir = Path(settings.paths.data_dir)
        collectors_info = [
            ("klines", "K-line", KlinesCollector(client, settings)),
            ("funding", "Funding Rate", FundingCollector(client, settings)),
            ("open_interest", "Open Interest", OpenInterestCollector(client, settings)),
            ("taker_ratio", "Taker Volume", TakerRatioCollector(client, settings)),
            ("global_ratio", "Global Long/Short", GlobalRatioCollector(client, settings)),
            ("top_ratio", "Top Trader Long/Short", TopRatioCollector(client, settings)),
        ]

        skipped_all = True
        for data_type, label, collector in collectors_info:
            inc_start = get_incremental_start(data_dir, data_type, symbol, start_dt)
            if inc_start > end_dt:
                log(f"  ✓ {label}: đã có → bỏ qua")
                continue
            skipped_all = False
            collector.collect(inc_start, end_dt, run_id)
            log(f"  ↓ {label}: tải bổ sung từ {inc_start.strftime('%H:%M UTC')}")

        t1 = time.perf_counter()
        log(f"Bước 1: {'tất cả đã có' if skipped_all else 'tải xong'} ({t1 - t0:.1f}s)")
        
        # 2. Normalize 
        status_text.info("🔄 Bước 2/5: Đang chuẩn hóa dữ liệu...")
        progress_bar.progress(30, text="Bước 2/5: Chuẩn hóa")
        t0 = time.perf_counter()
        db = DuckDBQueryLayer(db_path)
        process_raw_to_parquet(settings)
        build_raw_timeline(db, settings)
        t1 = time.perf_counter()
        log(f"Bước 2: chuẩn hóa xong ({t1 - t0:.1f}s)")
        
        # 3. Label Generation
        status_text.info("🏷️ Bước 3/5: Đang tính nhãn phân phối...")
        progress_bar.progress(50, text="Bước 3/5: Sinh nhãn")
        t0 = time.perf_counter()
        engine = DistributionLabelEngine()
        n_total, n_positive, n_negative = engine.compute_all_to_table(db.conn, "raw_timeline", "labels")
        t1 = time.perf_counter()
        n_excluded = n_total - n_positive - n_negative
        log(f"Bước 3: {n_total} nhãn ({n_positive} phân phối, {n_negative} thường, {n_excluded} loại) ({t1 - t0:.1f}s)")
        
        # 4. Feature Generation
        status_text.info("⚙️ Bước 4/5: Đang tính toán đặc trưng...")
        progress_bar.progress(70, text="Bước 4/5: Đặc trưng")
        t0 = time.perf_counter()
        build_features(db, "raw_timeline", "feature_results")
        t1 = time.perf_counter()

        row_count = db.conn.execute("SELECT count(*) FROM feature_results").fetchone()[0]
        col_count = db.conn.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_name = 'feature_results'"
        ).fetchone()[0]
        log(f"Bước 4: {row_count} dòng × {col_count} cột ({t1 - t0:.1f}s)")
        
        # 5. Run Experiment & Report
        status_text.info("🧪 Bước 5/5: Đang chạy mô hình & xuất báo cáo...")
        progress_bar.progress(90, text="Bước 5/5: Mô hình")
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
        result = run_experiment(config, conn=db.conn)
        registry = ArtifactRegistry(Path(artifact_dir))
        artifact_id = registry.save_experiment(result)
        t1 = time.perf_counter()

        artifact = registry.load_experiment(artifact_id)
        md_content = generate_markdown_report(artifact)

        total_time = time.perf_counter() - t_start
        progress_bar.progress(100, text="Hoàn thành!")
        status_text.success(f"✅ Pipeline hoàn tất trong {total_time:.1f}s — Artifact: `{artifact_id}`")
        log(f"Bước 5: mô hình xong ({t1 - t0:.1f}s)")
        log(f"Tổng: {total_time:.1f}s")

        # ===== RESULTS SECTION =====
        st.markdown("---")

        # Tab layout for clean results
        tab_labels, tab_metrics, tab_baselines, tab_quality, tab_report, tab_log = st.tabs([
            "🏷️ Nhãn", "📈 Metrics", "� Baselines", "🔍 Chất lượng", "�📄 Báo cáo", "📋 Log"
        ])

        # --- Tab: Labels ---
        with tab_labels:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Tổng số điểm", f"{n_total:,}")
            c2.metric("Phân phối (1)", n_positive)
            c3.metric("Bình thường (0)", f"{n_negative:,}")
            c4.metric("Loại trừ", n_excluded)

            # Bar chart for label distribution
            import pandas as pd
            chart_data = pd.DataFrame({
                "Nhãn": ["Phân phối (1)", "Bình thường (0)", "Loại trừ"],
                "Số lượng": [n_positive, n_negative, n_excluded],
            })
            st.bar_chart(chart_data.set_index("Nhãn"))

            if n_positive == 0:
                st.warning(
                    "⚠️ Không có event phân phối nào (label=1). Mô hình không thể học. "
                    "Hãy thử coin biến động hơn hoặc khoảng thời gian dài hơn."
                )
            elif n_positive < 50:
                st.warning(f"⚠️ Chỉ có {n_positive} event phân phối — quá ít để mô hình học tốt. Cần thêm dữ liệu.")

        # --- Tab: Metrics ---
        with tab_metrics:
            agg = result.get("results", {}).get("aggregate", {})
            per_fold = result.get("results", {}).get("per_fold", [])
            warning = result.get("results", {}).get("warning")
            if warning:
                st.warning(f"⚠️ {warning}")

            if agg:
                metric_cols = st.columns(len(agg))
                for col, (k, v) in zip(metric_cols, agg.items()):
                    col.metric(k, f"{v:.4f}" if isinstance(v, float) else str(v))

                if per_fold:
                    st.markdown("#### Kết quả từng Fold")
                    fold_rows = []
                    for fold in per_fold:
                        row = {"Fold": fold.get("fold_idx", "?")}
                        if fold.get("skipped"):
                            row["Status"] = f"SKIP: {fold.get('reason', '')}"
                        else:
                            m = fold.get("metrics", {})
                            row["Precision"] = f"{m.get('precision', 0):.4f}"
                            row["Recall"] = f"{m.get('recall', 0):.4f}"
                            row["Brier"] = f"{m.get('brier', 0):.4f}"
                            row["Threshold"] = f"{m.get('threshold', 0.5):.2f}"
                            row["Train"] = f"{fold.get('train_size', 0)} ({fold.get('train_positives', 0)}+)"
                            row["Test"] = f"{fold.get('test_size', 0)} ({fold.get('test_positives', 0)}+)"
                        fold_rows.append(row)
                    st.dataframe(pd.DataFrame(fold_rows), use_container_width=True)

                # Check if all metrics are 0
                all_zero = all(v == 0 for v in agg.values() if isinstance(v, (int, float)))
                if all_zero:
                    st.error(
                        "❌ Tất cả metrics = 0. Nguyên nhân có thể:\n"
                        "- Mô hình dự đoán tất cả là 0 (không phát hiện phân phối)\n"
                        "- Dữ liệu train/test không cân bằng\n"
                        "- Cần điều chỉnh threshold hoặc thêm feature"
                    )
            else:
                st.info("Không có metrics.")

        # --- Tab: Baselines ---
        with tab_baselines:
            baselines = result.get("results", {}).get("baselines", {})
            model_agg = result.get("results", {}).get("aggregate", {})

            if baselines:
                # Build comparison table
                comparison_rows = []
                # Add model row
                comparison_rows.append({
                    "Model": "LogReg (mô hình)",
                    "Precision": model_agg.get("precision_mean", 0.0),
                    "Recall": model_agg.get("recall_mean", 0.0),
                    "Brier": model_agg.get("brier_mean", 0.0),
                })
                # Add baseline rows
                for name, metrics in baselines.items():
                    comparison_rows.append({
                        "Model": name,
                        "Precision": metrics.get("precision_mean", 0.0),
                        "Recall": metrics.get("recall_mean", 0.0),
                        "Brier": metrics.get("brier_mean", 0.0),
                    })

                df_comp = pd.DataFrame(comparison_rows)
                st.dataframe(
                    df_comp.style.format({
                        "Precision": "{:.4f}",
                        "Recall": "{:.4f}",
                        "Brier": "{:.4f}",
                    }),
                    use_container_width=True,
                )

                # Bar chart comparison
                chart_df = df_comp.set_index("Model")[["Precision", "Recall"]]
                st.bar_chart(chart_df)

                # Conclusion
                model_precision = model_agg.get("precision_mean", 0.0)
                best_baseline_prec = max(
                    (m.get("precision_mean", 0.0) for m in baselines.values()),
                    default=0.0,
                )
                if model_precision > best_baseline_prec:
                    st.success(
                        f"✅ Mô hình LogReg vượt baseline tốt nhất "
                        f"(precision {model_precision:.4f} > {best_baseline_prec:.4f})"
                    )
                else:
                    st.warning(
                        f"⚠️ Mô hình chưa vượt baseline "
                        f"(precision {model_precision:.4f} ≤ {best_baseline_prec:.4f}). "
                        "Cần cải thiện feature hoặc mô hình."
                    )
            else:
                st.info("Không có baseline comparison.")

        # --- Tab: Data Quality & Leakage ---
        with tab_quality:
            dq = result.get("results", {}).get("data_quality", {})
            leak = result.get("results", {}).get("leakage_report", {})

            # Leakage status
            st.markdown("#### Kiểm tra Leakage")
            leak_status = leak.get("status", "unknown")
            if leak_status == "passed":
                st.success("✅ Không phát hiện leakage")
            else:
                st.error(f"❌ Phát hiện leakage: {leak.get('forbidden_columns', [])}")

            st.markdown(f"- Future data check: `{leak.get('future_data_check', 'N/A')}`")
            st.markdown(f"- Split overlap: `{leak.get('split_overlap', 'N/A')}`")

            # Data quality
            st.markdown("---")
            st.markdown("#### Data Quality")

            if dq:
                qc1, qc2, qc3, qc4 = st.columns(4)
                qc1.metric("Tổng rows", f"{dq.get('total_rows', 0):,}")
                qc2.metric("Cột", dq.get("columns", 0))
                qc3.metric("Duplicates", dq.get("duplicate_count", 0))
                qc4.metric("Prevalence", f"{dq.get('label_distribution', {}).get('prevalence', 0):.4f}")

                # Time range
                tr = dq.get("time_range", {})
                if tr:
                    st.markdown(
                        f"**Thời gian:** {tr.get('start', '?')} → {tr.get('end', '?')} "
                        f"({tr.get('duration_days', 0):.1f} ngày)"
                    )

                # Label distribution
                ld = dq.get("label_distribution", {})
                if ld:
                    st.markdown(
                        f"**Phân phối nhãn:** {ld.get('positive', 0)} positive, "
                        f"{ld.get('negative', 0)} negative, {ld.get('null', 0)} null"
                    )

                # Null counts
                nc = dq.get("null_counts", {})
                if nc:
                    st.markdown("**Top 10 cột có null nhiều nhất:**")
                    nc_df = pd.DataFrame(
                        list(nc.items()), columns=["Cột", "Số null"]
                    )
                    st.dataframe(nc_df, use_container_width=True)

                # Warnings
                if dq.get("duplicate_count", 0) > 0:
                    st.warning(f"⚠️ {dq['duplicate_count']} rows trùng lặp")
                null_total = sum(nc.values())
                if null_total > 0:
                    st.warning(f"⚠️ Có {null_total} giá trị null trong top 10 cột")
            else:
                st.info("Không có data quality report.")

        # --- Tab: Report ---
        with tab_report:
            st.markdown(md_content)

        # --- Tab: Log ---
        with tab_log:
            st.code("\n".join(log_lines), language="text")

    except Exception as e:
        status_text.error(f"❌ Lỗi: {str(e)}")
        progress_bar.empty()
else:
    st.info("👈 Bấm 'Chạy toàn bộ quy trình' ở thanh bên trái để bắt đầu.")
