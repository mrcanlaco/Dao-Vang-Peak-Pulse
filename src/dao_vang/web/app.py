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

# --- CSS for compact UI ---
st.markdown("""
<style>
    .stMetric { padding: 4px 0 !important; }
    .stMetric > div > div { gap: 2px !important; }
    .stTabs [data-baseweb="tab-list"] { gap: 4px; }
    .stTabs [data-baseweb="tab"] { padding: 6px 12px; font-size: 14px; }
    .stAlert { padding: 8px 12px !important; }
    div[data-testid="stSidebar"] { width: 320px !important; }
    div[data-testid="stSidebar"] > div { padding-top: 1rem; }
</style>
""", unsafe_allow_html=True)

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

    if _all_symbols:
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
    symbol: str, start_dt, end_dt, db_path: str, settings: AppSettings
) -> tuple[DuckDBQueryLayer, int, int, int, int, int, float]:
    """Run collect → normalize → labels → features. Returns (db, n_total, n_pos, n_neg, n_exc, n_rows, n_cols, elapsed)."""
    t0 = time.perf_counter()
    client = BinanceClient()
    run_id = f"run_{int(time.time())}"
    data_dir = Path(settings.paths.data_dir)

    collectors = [
        ("klines", KlinesCollector(client, settings)),
        ("funding", FundingCollector(client, settings)),
        ("open_interest", OpenInterestCollector(client, settings)),
        ("taker_ratio", TakerRatioCollector(client, settings)),
        ("global_ratio", GlobalRatioCollector(client, settings)),
        ("top_ratio", TopRatioCollector(client, settings)),
    ]
    for data_type, collector in collectors:
        inc_start = get_incremental_start(data_dir, data_type, symbol, start_dt)
        if inc_start > end_dt:
            continue
        collector.collect(inc_start, end_dt, run_id)

    process_raw_to_parquet(settings)
    db = DuckDBQueryLayer(db_path)
    build_raw_timeline(db, settings)

    engine = DistributionLabelEngine()
    n_total, n_pos, n_neg = engine.compute_all_to_table(db.conn, "raw_timeline", "labels")
    n_exc = n_total - n_pos - n_neg

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

        status.info("📡 Đang tải dữ liệu...")
        progress.progress(30, text="Thu thập + Chuẩn hóa")
        db, n_total, n_pos, n_neg, n_exc, n_rows, n_cols, t_pipe = _run_pipeline_steps(
            symbol, start_dt, end_dt, db_path, settings
        )

        if n_pos == 0:
            status.warning(
                f"⚠️ Không có event phân phối nào trong dữ liệu {symbol}. "
                "Thử coin biến động hơn hoặc khoảng thời gian dài hơn."
            )
            progress.empty()
        else:
            status.info("🧠 Đang train model + dự đoán...")
            progress.progress(80, text="Train + Predict")

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
                c1.metric("Probability cao nhất", f"{max_prob:.1%}")
                c2.metric("Tín hiệu CAO", len(high_risk))
                c3.metric("Tín hiệu TB", len(med_risk))
                c4.metric("Val Precision", f"{model_metrics.get('precision', 0):.1%}")

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
                    st.caption(f"🔴 Threshold = {thresh:.2f}")

                # === Feature importance ===
                top_feats = model_info.get("top_features", [])
                if top_feats:
                    with st.expander("🔍 Top 5 feature quan trọng nhất", expanded=False):
                        feat_df = pd.DataFrame(top_feats)
                        feat_df["coefficient"] = feat_df["coefficient"].apply(lambda x: f"{x:+.4f}")
                        feat_df.columns = ["Feature", "Hệ số"]
                        st.dataframe(feat_df, use_container_width=True, hide_index=True)

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

        # Steps 1-4
        status.info("📡 Đang tải + chuẩn hóa + sinh nhãn + tính feature...")
        progress.progress(50, text="Pipeline 1→4")
        db, n_total, n_positive, n_negative, n_excluded, row_count, col_count, t_pipe = _run_pipeline_steps(
            symbol, start_dt, end_dt, db_path, settings
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
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📈 Metrics", "📊 Baselines", "🏷️ Nhãn", "🔍 Chất lượng", "📄 Báo cáo"
        ])

        # --- Tab: Metrics ---
        with tab1:
            agg = results_data.get("aggregate", {})
            per_fold = results_data.get("per_fold", [])

            if agg:
                # Compact metric row
                mc = st.columns(6)
                metrics_display = [
                    ("Precision", agg.get("precision_mean", 0)),
                    ("±", agg.get("precision_std", 0)),
                    ("Recall", agg.get("recall_mean", 0)),
                    ("±", agg.get("recall_std", 0)),
                    ("Brier", agg.get("brier_mean", 0)),
                    ("±", agg.get("brier_std", 0)),
                ]
                for col, (k, v) in zip(mc, metrics_display):
                    if k == "±":
                        col.caption(f"±{v:.4f}")
                    else:
                        col.metric(k, f"{v:.4f}")

                if per_fold:
                    st.markdown("#### Walk-Forward Folds")
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
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Tổng", f"{n_total:,}")
            c2.metric("Phân phối (1)", n_positive)
            c3.metric("Bình thường (0)", f"{n_negative:,}")
            c4.metric("Loại trừ", n_excluded)

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

            leak_status = leak.get("status", "unknown")
            if leak_status == "passed":
                st.success("✅ Không phát hiện leakage")
            else:
                st.error(f"❌ Leakage: {leak.get('forbidden_columns', [])}")

            if dq:
                qc = st.columns(4)
                qc[0].metric("Rows", f"{dq.get('total_rows', 0):,}")
                qc[1].metric("Duplicates", dq.get("duplicate_count", 0))
                qc[2].metric("Prevalence", f"{dq.get('label_distribution', {}).get('prevalence', 0):.4f}")
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
