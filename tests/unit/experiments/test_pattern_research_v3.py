from __future__ import annotations

import pandas as pd

from dao_vang.experiments.pattern_research_v3 import (
    PATTERN_MODEL_VERSION,
    classify_snapshot,
    fit_pattern_model,
    run_pattern_research,
)


def frame(rows: int = 500) -> pd.DataFrame:
    start = pd.Timestamp("2026-01-01", tz="UTC")
    values = []
    for index in range(rows):
        phase = index % 3
        values.append(
            {
                "symbol": "AAAUSDT" if phase else "BBBUSDT",
                "feature_time": start + pd.Timedelta(hours=index),
                "price_ret_5m": 0.01 * phase,
                "price_ret_1h": 0.01 + 0.01 * phase,
                "price_ret_4h": 0.08 + 0.02 * phase,
                "price_ret_24h": 0.24 + 0.04 * phase,
                "price_volatility_24h": 0.08 + 0.01 * phase,
                "distance_from_high_24h": -0.01 - 0.01 * phase,
                "momentum_deceleration_4h": 0.02 * phase,
                "fake_breakout_1h": 0.01 * phase,
                "volume_percentile_24h": 0.5 + 0.1 * phase,
                "funding_percentile_30d": 0.7 + 0.1 * phase,
                "funding_change_8h": 0.0001 * (phase + 1),
                "funding_persistence_7d": 0.1 + phase,
                "oi_change_1h": 0.01 * phase,
                "oi_change_4h": 0.02 * phase,
                "oi_change_24h": 0.03 * phase,
                "_outcome_label": int((index + phase) % 2 == 0),
            }
        )
    return pd.DataFrame(values)


def test_pattern_classifier_unknown_preserves_nearest_and_discrepancies():
    data = frame(200)
    model = fit_pattern_model(data, n_patterns=3)
    assert model.version == PATTERN_MODEL_VERSION

    snapshot = data.iloc[0].to_dict()
    snapshot["price_ret_24h"] = 100.0
    result = classify_snapshot(snapshot, model)

    assert result["status"] == "unknown"
    assert result["pattern_id"] == "unknown"
    assert result["nearest_pattern"] is not None
    assert result["discrepancies"]
    assert result["unknown_reason"] == "nearest_template_distance_exceeds_train_radius"


def test_research_uses_common_holdout_and_refuses_legacy_quality():
    report, model = run_pattern_research(
        frame(),
        source_provenance={
            "label_kind": "diagnostic_entry1",
            "compact_contract_verified": False,
        },
    )

    assert report["promotion_eligible"] is False
    assert report["evidence_status"] == "unsupported_compact_outcome"
    assert report["contract"] == "diagnostic_entry1_legacy"
    assert report["contract_checksum"] is None
    assert len(report["heldout"]) == 5
    assert len(report["condition_ablation"]) == 5
    assert report["selection"]["common_split_for_all_variants"]
    assert all(item["quality"]["status"] == "unconfirmed" for item in report["heldout"])
    assert model.checksum


def test_declared_compact_requires_exact_contract_provenance():
    data = frame()
    report, _ = run_pattern_research(
        data,
        source_provenance={
            "label_kind": "compact_policy",
            "compact_contract_verified": True,
        },
    )
    assert report["evidence_status"] == "unsupported_compact_outcome"
    assert report["contract"] == "unknown_outcome_contract"

