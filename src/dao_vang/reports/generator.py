from typing import Any, Dict


def generate_markdown_report(artifact: Dict[str, Any]) -> str:
    """
    Generates a markdown report from an experiment artifact.
    """
    artifact_id = artifact.get("artifact_id", "UNKNOWN")
    created_at = artifact.get("created_at", "UNKNOWN")
    data = artifact.get("data", {})

    config = data.get("config", {})
    results = data.get("results", {})
    aggregate = results.get("aggregate", {})
    per_fold = results.get("per_fold", [])

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

    lines.extend(["", "## Per-Fold Results"])

    if per_fold:
        for fold in per_fold:
            fold_idx = fold.get("fold_idx", "N/A")
            metrics = fold.get("metrics", {})
            lines.append(f"### Fold {fold_idx}")
            for metric, value in metrics.items():
                if isinstance(value, float):
                    lines.append(f"- {metric}: {value:.4f}")
                else:
                    lines.append(f"- {metric}: {value}")
    else:
        lines.append("*No per-fold results available.*")

    return "\n".join(lines)
