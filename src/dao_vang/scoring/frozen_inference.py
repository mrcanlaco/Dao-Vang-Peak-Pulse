# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportMissingTypeStubs=false
"""Single, fail-closed serving path for frozen model inference.

The scanner still computes the heuristic score for candidate generation and
explanations, but a heuristic score is never a probability.  This module
keeps the two values separate and returns an immutable result that can be
used by replay and live serving alike.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

import joblib
import pandas as pd

from dao_vang.config.settings import ScoringConfig, ThresholdPolicy
from dao_vang.experiments.forward_test import FrozenModelInfo
from dao_vang.logging import get_logger
from dao_vang.scoring.distribution_scorer import (
    DistributionScore,
    compute_distribution_score,
)
from dao_vang.scoring.evidence import evaluate_evidence

logger = get_logger(__name__)


class FrozenInferenceError(ValueError):
    """A frozen bundle cannot safely score the supplied snapshot."""


@dataclass(frozen=True)
class SnapshotQuality:
    """Quality decision attached to every scored snapshot."""

    status: str
    score: float | None
    max_feature_age_minutes: float | None
    missing_features: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    @property
    def is_usable(self) -> bool:
        """Whether the snapshot may be used for model/alert decisions."""

        return self.status == "valid" and not self.reason_codes


@dataclass(frozen=True)
class SnapshotScore:
    """Result of the shared live/replay scoring contract.

    ``heuristic`` is a 0-100 candidate score.  ``model_probability`` is the
    estimator output and ``calibrated_probability`` is the output of the
    frozen calibrator.  The latter is the only value used for thresholds.

    ``__iter__`` intentionally preserves the old three-value unpacking API
    (heuristic, calibrated probability, tier) for callers outside the scanner.
    New code should use the named fields.
    """

    heuristic: DistributionScore
    model_probability: float | None
    calibrated_probability: float | None
    risk_tier: str
    threshold: float
    threshold_policy_version: str
    quality: SnapshotQuality
    model_id: str
    calibrator_id: str | None = None
    evidence_groups: tuple[str, ...] = ()

    def __iter__(self):  # type: ignore[no-untyped-def]
        yield self.heuristic
        yield self.calibrated_probability
        yield self.risk_tier

    @property
    def alertable(self) -> bool:
        """True only when quality, calibration and threshold policy pass."""

        return (
            self.quality.is_usable
            and self.calibrated_probability is not None
            and self.risk_tier in {"HIGH_CONFIDENCE", "WATCH"}
        )


def _as_utc_timestamp(value: Any) -> pd.Timestamp | None:
    """Parse a timestamp without allowing a machine-local timezone."""

    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        localized = parsed.tz_localize("UTC")
        return None if pd.isna(localized) else cast(pd.Timestamp, localized)
    converted = parsed.tz_convert("UTC")
    return None if pd.isna(converted) else cast(pd.Timestamp, converted)


def _normalise_quality_status(value: Any) -> str:
    if value is None:
        return "valid"
    status = str(value).lower()
    if "." in status:
        status = status.rsplit(".", 1)[-1]
    return status


def assess_snapshot_quality(
    feature_dict: Mapping[str, Any],
    frozen_info: FrozenModelInfo,
    *,
    now: datetime | None = None,
    max_feature_age_minutes: int | None = None,
    min_data_quality_score: float = 0.8,
    require_feature_time: bool = True,
) -> SnapshotQuality:
    """Evaluate freshness, quality status and required feature completeness.

    Missing model inputs are *not* silently replaced with zero.  The caller
    may still persist the heuristic candidate with this quality result, but
    it must not create an alert from an unusable snapshot.
    """

    reasons: list[str] = []
    missing: list[str] = []
    for col in frozen_info.feature_cols:
        value = feature_dict.get(col)
        if value is None or pd.isna(value):
            missing.append(col)
    if missing:
        reasons.append("missing_required_features")

    status = _normalise_quality_status(feature_dict.get("quality_status"))
    if status in {"invalid", "quarantined", "failed", "fail"}:
        reasons.append(f"quality_status_{status}")
    elif status not in {"valid", "warning"}:
        reasons.append("quality_status_unknown")

    quality_raw = feature_dict.get("data_quality_score")
    quality_score: float | None
    try:
        quality_score = float(quality_raw) if quality_raw is not None else None
    except (TypeError, ValueError):
        quality_score = None
        reasons.append("quality_score_invalid")
    if quality_score is None:
        # A missing score is only acceptable when the source explicitly says
        # valid.  Warning data receives a conservative penalty.
        quality_score = 1.0 if status == "valid" else 0.75
    quality_score = max(0.0, min(1.0, quality_score))
    if quality_score < min_data_quality_score:
        reasons.append("quality_score_below_threshold")

    feature_time = feature_dict.get("feature_time", feature_dict.get("timestamp"))
    parsed_feature_time = _as_utc_timestamp(feature_time)
    age_minutes: float | None = None
    if parsed_feature_time is None:
        if require_feature_time:
            reasons.append("feature_time_missing")
    else:
        clock = _as_utc_timestamp(now or datetime.now(timezone.utc))
        assert clock is not None
        age_minutes = (clock - parsed_feature_time).total_seconds() / 60.0
        if age_minutes < -1.0:
            reasons.append("feature_time_in_future")
        elif (
            max_feature_age_minutes is not None
            and age_minutes > max_feature_age_minutes
        ):
            reasons.append("feature_stale")

    return SnapshotQuality(
        status="valid" if not reasons else "invalid",
        score=quality_score,
        max_feature_age_minutes=age_minutes,
        missing_features=tuple(missing),
        reason_codes=tuple(dict.fromkeys(reasons)),
    )


def _load_metadata(frozen_info: FrozenModelInfo) -> dict[str, Any]:
    try:
        return json.loads(frozen_info.metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _metadata_value(metadata: Mapping[str, Any], *keys: str) -> Any:
    """Read a value from top-level metadata or the config block."""

    config = metadata.get("config")
    config_map = config if isinstance(config, Mapping) else {}
    for key in keys:
        if key in metadata:
            return metadata[key]
        if key in config_map:
            return config_map[key]
    return None


def _resolve_artifact_ref(ref: Any, metadata_path: Path) -> Path | None:
    if isinstance(ref, Mapping):
        ref = ref.get("path") or ref.get("ref") or ref.get("file")
    if not isinstance(ref, str) or not ref:
        return None
    path = Path(ref)
    if not path.is_absolute():
        path = metadata_path.parent / path
    return path


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_bundle_checksums(
    frozen_info: FrozenModelInfo,
    metadata: Mapping[str, Any],
) -> str | None:
    """Verify hashes declared by the frozen bundle, fail-closed on drift."""

    checksums = metadata.get("checksums")
    if not isinstance(checksums, Mapping) or not checksums:
        # Legacy artifacts without an integrity manifest are not safe for live
        # serving.  They may still be inspected in research mode, but produce
        # no probability/alert from this path.
        return "bundle_checksums_missing"

    candidates: list[tuple[str, Path | None, Any]] = []
    for key in ("model_sha256", "model_hash", "model", "model.joblib"):
        if key in checksums:
            value = checksums[key]
            expected = value.get("sha256") if isinstance(value, Mapping) else value
            path = frozen_info.model_path
            candidates.append(("model", path, expected))
            break

    metadata_calibrator = _metadata_value(
        metadata,
        "calibrator_path",
        "calibrator_ref",
        "calibrator_file",
        "calibrator",
    )
    for key in (
        "calibrator_sha256",
        "calibrator_hash",
        "calibrator",
        "calibrator.joblib",
    ):
        if key in checksums:
            value = checksums[key]
            expected = value.get("sha256") if isinstance(value, Mapping) else value
            candidates.append(
                (
                    "calibrator",
                    _resolve_artifact_ref(
                        metadata_calibrator, frozen_info.metadata_path
                    ),
                    expected,
                )
            )
            break

    # A model hash is mandatory.  Calibrator hash is mandatory whenever a
    # calibrator is external and documented by the bundle.
    if not any(name == "model" for name, _, _ in candidates):
        return "model_checksum_missing"
    if metadata_calibrator is not None and not any(
        name == "calibrator" for name, _, _ in candidates
    ):
        return "calibrator_checksum_missing"
    for name, path, expected in candidates:
        if path is None or not path.exists() or not isinstance(expected, str):
            return f"{name}_checksum_missing"
        try:
            actual = _sha256_file(path).lower()
        except OSError:
            return f"{name}_checksum_unreadable"
        if actual != expected.lower().removeprefix("sha256:"):
            return f"{name}_checksum_mismatch"
    return None


def _apply_calibrator(
    model_probability: float,
    frozen_info: FrozenModelInfo,
    metadata: Mapping[str, Any],
) -> tuple[float | None, str | None, str | None]:
    """Apply the frozen calibrator, returning (probability, id, reason)."""

    ref = _metadata_value(
        metadata,
        "calibrator_path",
        "calibrator_ref",
        "calibrator_file",
        "calibrator",
    )
    calibrator_id = _metadata_value(metadata, "calibrator_id", "calibration_id")
    if str(calibrator_id or "").strip().lower() == "identity_v1":
        return None, "identity_v1", "calibrator_unvalidated_identity"
    if ref is None:
        # A bundle may explicitly document that its estimator is already a
        # calibrated pipeline.  Do not silently treat an undocumented model
        # as calibrated.
        method = _metadata_value(metadata, "calibration_method")
        if method in {"precalibrated", "embedded", "pipeline"}:
            return model_probability, str(calibrator_id or method), None
        return None, None, "calibrator_missing"

    path = _resolve_artifact_ref(ref, frozen_info.metadata_path)
    if path is None or not path.exists():
        return None, str(calibrator_id) if calibrator_id else None, "calibrator_missing"
    try:
        calibrator = joblib.load(path)
        if hasattr(calibrator, "predict_proba"):
            calibrated = float(calibrator.predict_proba([[model_probability]])[0, 1])
        elif hasattr(calibrator, "transform"):
            calibrated = float(calibrator.transform([model_probability])[0])
        elif callable(calibrator):
            calibrator_func = cast(Callable[[float], float], calibrator)
            calibrated = float(calibrator_func(model_probability))
        else:
            return (
                None,
                str(calibrator_id) if calibrator_id else None,
                "calibrator_invalid",
            )
    except Exception as exc:  # pragma: no cover - defensive boundary
        logger.warning(
            "frozen_calibrator_failed",
            model_id=frozen_info.model_id,
            error=str(exc),
        )
        return None, str(calibrator_id) if calibrator_id else None, "calibrator_error"
    if not math.isfinite(calibrated) or not 0.0 <= calibrated <= 1.0:
        return (
            None,
            str(calibrator_id) if calibrator_id else None,
            "calibrator_out_of_range",
        )
    return calibrated, str(calibrator_id) if calibrator_id else path.name, None


def _threshold_contract(
    frozen_info: FrozenModelInfo,
    threshold_policy: ThresholdPolicy,
    metadata: Mapping[str, Any],
) -> tuple[float, float, str]:
    """Resolve frozen high/watch thresholds and policy version."""

    contract = _metadata_value(metadata, "threshold_policy", "thresholds")
    contract_map = contract if isinstance(contract, Mapping) else {}
    high = contract_map.get(
        "high_confidence_min_prob", contract_map.get("high_confidence")
    )
    watch = contract_map.get("watch_min_prob", contract_map.get("watch"))
    # The legacy frozen threshold is the high-confidence threshold.  The
    # runtime policy is only a compatibility fallback for old artifacts.
    high_threshold = float(high if high is not None else frozen_info.threshold)
    watch_threshold = float(
        watch if watch is not None else threshold_policy.watch_min_prob
    )
    if watch_threshold > high_threshold:
        raise FrozenInferenceError("threshold_policy_invalid_order")
    version = str(
        contract_map.get("version")
        or _metadata_value(metadata, "threshold_policy_version")
        or threshold_policy.version
    )
    return high_threshold, watch_threshold, version


def score_snapshot(
    symbol: str,
    feature_dict: dict[str, Any],
    btc_context: Any,
    frozen_info: FrozenModelInfo,
    config: ScoringConfig,
    threshold_policy: ThresholdPolicy,
    pump_pct: float = 0.0,
    pump_days: int = 0,
    *,
    quality: SnapshotQuality | None = None,
    now: datetime | None = None,
    max_feature_age_minutes: int | None = None,
    min_data_quality_score: float = 0.8,
) -> SnapshotScore:
    """Score one snapshot through the frozen model and policy contract.

    The function is deliberately fail-closed: an incomplete/stale snapshot or
    bundle without a documented calibrator returns ``WAIT`` with no calibrated
    probability.  The heuristic score remains available for diagnostics.
    """

    heuristic = compute_distribution_score(
        symbol=symbol,
        features=feature_dict,
        btc=btc_context,
        config=config,
        pump_pct=pump_pct,
        pump_days=pump_days,
    )
    quality_result = quality or assess_snapshot_quality(
        feature_dict,
        frozen_info,
        now=now,
        max_feature_age_minutes=max_feature_age_minutes,
        min_data_quality_score=min_data_quality_score,
        require_feature_time=max_feature_age_minutes is not None,
    )
    metadata = _load_metadata(frozen_info)
    high_threshold, watch_threshold, policy_version = _threshold_contract(
        frozen_info, threshold_policy, metadata
    )

    model_probability: float | None = None
    calibrated_probability: float | None = None
    calibrator_id: str | None = None
    reasons = list(quality_result.reason_codes)

    if quality_result.is_usable:
        checksum_reason = _verify_bundle_checksums(frozen_info, metadata)
        if checksum_reason:
            reasons.append(checksum_reason)
        else:
            try:
                model = joblib.load(frozen_info.model_path)
                frame = pd.DataFrame(
                    [{name: feature_dict[name] for name in frozen_info.feature_cols}]
                )
                # Do not fill missing values here; assess_snapshot_quality already
                # rejected them.  This keeps live and replay semantics explicit.
                if hasattr(model, "predict_proba"):
                    probabilities = model.predict_proba(frame)
                    model_probability = float(probabilities[0, 1])
                else:
                    prediction = float(model.predict(frame)[0])
                    model_probability = 1.0 if prediction > 0.5 else 0.0
                if not math.isfinite(model_probability) or not (
                    0.0 <= model_probability <= 1.0
                ):
                    reasons.append("model_probability_out_of_range")
                    model_probability = None
            except Exception as exc:  # fail closed; scanner records quality reason
                logger.warning(
                    "frozen_model_inference_failed",
                    model_id=frozen_info.model_id,
                    error=str(exc),
                )
                reasons.append("model_inference_failed")

        if model_probability is not None:
            calibrated_probability, calibrator_id, calibration_reason = (
                _apply_calibrator(model_probability, frozen_info, metadata)
            )
            if calibration_reason:
                reasons.append(calibration_reason)

    if reasons:
        quality_result = SnapshotQuality(
            status="invalid",
            score=quality_result.score,
            max_feature_age_minutes=quality_result.max_feature_age_minutes,
            missing_features=quality_result.missing_features,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    risk_tier = "WAIT"
    evidence_groups: tuple[str, ...] = ()
    if quality_result.is_usable and calibrated_probability is not None:
        evidence = evaluate_evidence(
            heuristic.components,
            min_groups=threshold_policy.high_confidence_min_evidence_groups,
            quality_usable=quality_result.is_usable,
        )
        evidence_groups = evidence.groups
        if calibrated_probability >= high_threshold:
            if evidence.passed:
                risk_tier = "HIGH_CONFIDENCE"
            else:
                risk_tier = "WATCH"
        elif calibrated_probability >= watch_threshold:
            risk_tier = "WATCH"

    return SnapshotScore(
        heuristic=heuristic,
        model_probability=model_probability,
        calibrated_probability=calibrated_probability,
        risk_tier=risk_tier,
        threshold=high_threshold,
        threshold_policy_version=policy_version,
        quality=quality_result,
        model_id=frozen_info.model_id,
        calibrator_id=calibrator_id,
        evidence_groups=evidence_groups,
    )
