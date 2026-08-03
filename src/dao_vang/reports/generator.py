from typing import Any, Dict


def generate_markdown_report(artifact: Dict[str, Any]) -> str:
    """
    Generates a markdown report from an experiment artifact.
    Includes: config, aggregate results, per-fold, baselines, data quality,
    leakage audit, and a clear conclusion (Constitution §9).
    """
    artifact_id = artifact.get("artifact_id", "UNKNOWN")
    created_at = artifact.get("created_at", "UNKNOWN")
    data = artifact.get("data", {})

    config = data.get("config", {})
    results = data.get("results", {})
    aggregate = results.get("aggregate", {})
    per_fold = results.get("per_fold", [])
    baselines = results.get("baselines", {})
    leakage = results.get("leakage_report", {})
    data_quality = results.get("data_quality", {})
    lead_time = results.get("lead_time_stats", {})
    warning = results.get("warning")

    lines = [
        f"# Experiment Report: {artifact_id}",
        "",
        f"**Date:** {created_at}",
        f"**Hypothesis ID:** {config.get('hypothesis_id', 'N/A')}",
        f"**Model:** {config.get('baseline_model', 'N/A')}",
        "",
        "## Configuration",
        f"- **Dataset Version:** {config.get('dataset_version', 'N/A')}",
        f"- **Label Version:** {config.get('label_version', 'N/A')}",
        f"- **Feature Set Version:** {config.get('feature_set_version', 'N/A')}",
        f"- **Split Version:** {config.get('split_version', 'N/A')}",
        f"- **Seed:** {config.get('seed', 'N/A')}",
        "",
        "## Aggregate Results",
    ]

    if aggregate:
        for metric, value in aggregate.items():
            if isinstance(value, float):
                lines.append(f"- **{metric}:** {value:.4f}")
            else:
                lines.append(f"- **{metric}:** {value}")
    else:
        lines.append("*No aggregate results available.*")

    # Per-fold results
    lines.extend(["", "## Per-Fold Results"])

    if per_fold:
        for fold in per_fold:
            fold_idx = fold.get("fold_idx", "N/A")
            metrics = fold.get("metrics", {})
            lines.append(f"### Fold {fold_idx}")
            if fold.get("skipped"):
                lines.append(f"*Skipped: {fold.get('reason', 'N/A')}*")
                continue
            for metric, value in metrics.items():
                if isinstance(value, float):
                    lines.append(f"- {metric}: {value:.4f}")
                else:
                    lines.append(f"- {metric}: {value}")
            if "train_size" in fold:
                lines.append(f"- train: {fold['train_size']} rows ({fold.get('train_positives', 0)} positive)")
                lines.append(f"- test: {fold.get('test_size', 0)} rows ({fold.get('test_positives', 0)} positive)")
    else:
        lines.append("*No per-fold results available.*")

    # Baseline comparison
    if baselines:
        lines.extend(["", "## Baseline Comparison"])
        lines.append("| Model | Precision | Recall | Brier |")
        lines.append("|---|---|---|---|")
        # Model row
        model_p = aggregate.get("precision_mean", 0.0)
        model_r = aggregate.get("recall_mean", 0.0)
        model_b = aggregate.get("brier_mean", 0.0)
        lines.append(f"| **LogReg** | **{model_p:.4f}** | **{model_r:.4f}** | **{model_b:.4f}** |")
        for name, m in baselines.items():
            lines.append(
                f"| {name} | {m.get('precision_mean', 0):.4f} | "
                f"{m.get('recall_mean', 0):.4f} | {m.get('brier_mean', 0):.4f} |"
            )

    # Data quality
    if data_quality:
        lines.extend(["", "## Data Quality"])
        lines.append(f"- **Total rows:** {data_quality.get('total_rows', 0):,}")
        lines.append(f"- **Columns:** {data_quality.get('columns', 0)}")
        lines.append(f"- **Duplicates:** {data_quality.get('duplicate_count', 0)}")
        ld = data_quality.get("label_distribution", {})
        if ld:
            lines.append(
                f"- **Label distribution:** {ld.get('positive', 0)} positive, "
                f"{ld.get('negative', 0)} negative, {ld.get('null', 0)} null"
            )
            lines.append(f"- **Prevalence:** {ld.get('prevalence', 0):.4f}")
        tr = data_quality.get("time_range", {})
        if tr:
            lines.append(
                f"- **Time range:** {tr.get('start', '?')} → {tr.get('end', '?')} "
                f"({tr.get('duration_days', 0):.1f} days)"
            )
        nc = data_quality.get("null_counts", {})
        if nc:
            lines.append("- **Top null columns:**")
            for col, count in list(nc.items())[:5]:
                lines.append(f"  - {col}: {count}")

    # Lead time stats
    if lead_time and lead_time.get("status") == "ok":
        lines.extend(["", "## Lead Time (time-to-distribution)"])
        lines.append(
            f"- **Median lead time:** {lead_time.get('median_minutes', 0):.0f} min "
            f"(~{lead_time.get('median_hours', 0):.1f}h)"
        )
        lines.append(
            f"- **Mean:** {lead_time.get('mean_minutes', 0):.0f} min | "
            f"**p25:** {lead_time.get('p25_minutes', 0):.0f} min | "
            f"**p75:** {lead_time.get('p75_minutes', 0):.0f} min"
        )
        lines.append(
            f"- **Range:** {lead_time.get('min_minutes', 0):.0f}–"
            f"{lead_time.get('max_minutes', 0):.0f} min"
        )
        lines.append(
            f"- **Invalidation horizon:** {lead_time.get('horizon_minutes', 1440)} min "
            f"(signal expires after this; un-materialized positive = false positive)"
        )
        lines.append(
            f"- **Positive labels with lead time:** "
            f"{lead_time.get('n_positive_with_lead_time', 0)}"
        )
    elif lead_time and lead_time.get("status") == "no_positive_labels":
        lines.extend(["", "## Lead Time (time-to-distribution)"])
        lines.append("*No positive labels — lead time not available.*")

    # Leakage audit
    if leakage:
        lines.extend(["", "## Leakage Audit"])
        status = leakage.get("status", "unknown")
        lines.append(f"- **Status:** {status}")
        lines.append(f"- **Future data check:** {leakage.get('future_data_check', 'N/A')}")
        lines.append(f"- **Split overlap:** {leakage.get('split_overlap', 'N/A')}")
        if leakage.get("forbidden_columns"):
            lines.append(f"- **Forbidden columns found:** {leakage['forbidden_columns']}")

    # Warning
    if warning:
        lines.extend(["", "## ⚠️ Warning", warning])

    # Conclusion (Constitution §9: "có kết luận rõ: tiếp tục, sửa giả thuyết hoặc dừng")
    lines.extend(["", "## Conclusion"])
    conclusion = _generate_conclusion(aggregate, baselines, data_quality, leakage, warning)
    lines.append(conclusion)

    return "\n".join(lines)


def _generate_conclusion(
    aggregate: Dict[str, Any],
    baselines: Dict[str, Any],
    data_quality: Dict[str, Any],
    leakage: Dict[str, Any],
    warning: Any = None,
) -> str:
    """Generate a clear conclusion per Constitution §9: continue, revise hypothesis, or stop."""
    if warning:
        return f"**DỪNG/KHÔNG THỂ ĐÁNH GIÁ.** {warning} Cần thu thêm dữ liệu hoặc thay đổi phạm vi."

    model_p = aggregate.get("precision_mean", 0.0)
    model_b = aggregate.get("brier_mean", 0.0)
    leak_status = leakage.get("status", "unknown")

    # Find best baseline precision
    best_baseline_p = 0.0
    best_baseline_name = "N/A"
    for name, m in baselines.items():
        bp = m.get("precision_mean", 0.0)
        if bp > best_baseline_p:
            best_baseline_p = bp
            best_baseline_name = name

    ld = data_quality.get("label_distribution", {})
    n_positive = ld.get("positive", 0)

    parts = []

    # Leakage check
    if leak_status != "passed":
        parts.append("❌ **Leakage detected** — cần fix trước khi kết luận gì.")

    # Model vs baseline
    if model_p > best_baseline_p and model_p > 0:
        parts.append(
            f"✅ **Mô hình vượt baseline** (precision {model_p:.4f} > "
            f"{best_baseline_name} {best_baseline_p:.4f}, brier {model_b:.4f})."
        )
        if n_positive < 100:
            parts.append(
                f"⚠️ Nhưng chỉ có {n_positive} event positive — kết quả chưa đủ ổn định. "
                "Nên tiếp tục thu dữ liệu và chạy forward test."
            )
        parts.append("**Khuyến nghị: TIẾP TỤC** — phát triển thêm feature, chạy forward test.")
    elif model_p > 0:
        parts.append(
            f"⚠️ **Mô hình chưa vượt baseline** (precision {model_p:.4f} ≤ "
            f"{best_baseline_name} {best_baseline_p:.4f})."
        )
        parts.append(
            "**Khuyến nghị: SỬA GIẢ THUYẾT** — thử feature khác, điều chỉnh label, "
            "hoặc thử coin biến động hơn."
        )
    else:
        parts.append("❌ **Mô hình không hoạt động** (metrics = 0).")
        parts.append(
            "**Khuyến nghị: DỪNG** — cần xem lại data quality, label, hoặc split strategy."
        )

    return "\n".join(parts)
