"""Operational safety primitives for shadow/canary serving.

The scanner is deliberately conservative at the serving boundary.  This
module contains the small, deterministic pieces that are shared by the
daemon, monitoring jobs and rollback drills:

* a file based kill switch (malformed state is treated as *on*);
* an explicit canary policy (only HIGH_CONFIDENCE, fresh/valid data, budgets
  and cooldowns);
* bundle/config contract verification; and
* health, drift and rollback artifacts.

The helpers never manufacture model KPIs.  When there is not enough
materialized evidence they return ``insufficient_data`` rather than a fake
pass/fail value.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import statistics
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from dao_vang.domain.time import system_iso, system_now


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return system_iso(value or system_now()) or ""


def _atomic_json_write(path: Path, value: Mapping[str, Any]) -> None:
    """Write a small control artifact atomically and durably enough for ops."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(dict(value), stream, indent=2, sort_keys=True, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass


class KillSwitch:
    """Persistent kill switch.

    A missing file means off.  A malformed file means on: an operator should
    never lose the ability to stop alerts because a control file was damaged.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def activate(self, reason: str, *, actor: str = "operator") -> None:
        _atomic_json_write(
            self.path,
            {
                "active": True,
                "reason": str(reason),
                "actor": actor,
                "changed_at": _iso(),
            },
        )

    def clear(self, *, actor: str = "operator") -> None:
        _atomic_json_write(
            self.path,
            {
                "active": False,
                "reason": None,
                "actor": actor,
                "changed_at": _iso(),
            },
        )

    def state(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"active": False, "reason": None, "source": "missing"}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("active"), bool):
                raise ValueError("invalid kill switch shape")
            return {**payload, "source": str(self.path)}
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            return {
                "active": True,
                "reason": "kill_switch_state_invalid",
                "error": str(exc),
                "source": str(self.path),
            }

    @property
    def active(self) -> bool:
        return bool(self.state().get("active"))


@dataclass(frozen=True)
class CanaryDecision:
    allowed: bool
    reason: str
    mode: str
    tier: str
    global_count: int = 0
    coin_count: int = 0


def evaluate_canary_policy(
    *,
    mode: str,
    tier: str,
    quality_status: str,
    calibrated_probability: float | None,
    threshold: float | None,
    in_cooldown: bool,
    global_count: int,
    coin_count: int,
    global_limit: int,
    coin_limit: int,
    kill_switch_active: bool = False,
    bundle_valid: bool = True,
    allow_shadow_telegram: bool = False,
    telegram_min_probability: float | None = None,
) -> CanaryDecision:
    """Evaluate the action-alert policy without side effects.

    ``research`` always denies alerts.  ``shadow`` may send explicitly
    labelled observational Telegram messages when
    ``allow_shadow_telegram`` is enabled. Shadow still respects the
    kill switch and serving bundle checks, while its Telegram feed bypasses
    action-alert cooldown and budget gates. When configured, the Telegram
    probability gate applies to every mode and is strict (``>``).
    Quality/tier gates remain enforced for canary and production modes.
    """

    normalized_mode = str(mode).lower()
    normalized_tier = str(tier).upper()
    if normalized_mode == "research":
        return CanaryDecision(False, "mode_no_action_alerts", normalized_mode, normalized_tier, global_count, coin_count)
    if normalized_mode == "shadow" and not allow_shadow_telegram:
        return CanaryDecision(False, "mode_no_action_alerts", normalized_mode, normalized_tier, global_count, coin_count)
    if kill_switch_active:
        return CanaryDecision(False, "kill_switch_active", normalized_mode, normalized_tier, global_count, coin_count)
    if not bundle_valid:
        return CanaryDecision(False, "bundle_contract_invalid", normalized_mode, normalized_tier, global_count, coin_count)
    if telegram_min_probability is not None:
        if calibrated_probability is None or not math.isfinite(float(calibrated_probability)):
            return CanaryDecision(False, "telegram_probability_missing", normalized_mode, normalized_tier, global_count, coin_count)
        if float(calibrated_probability) <= float(telegram_min_probability):
            return CanaryDecision(False, "telegram_probability_below_threshold", normalized_mode, normalized_tier, global_count, coin_count)
    if normalized_mode == "shadow":
        return CanaryDecision(True, "shadow_observation", normalized_mode, normalized_tier, global_count, coin_count)
    if quality_status.lower() != "valid":
        return CanaryDecision(False, "data_quality_invalid", normalized_mode, normalized_tier, global_count, coin_count)
    if normalized_tier != "HIGH_CONFIDENCE":
        return CanaryDecision(False, "tier_not_high_confidence", normalized_mode, normalized_tier, global_count, coin_count)
    if calibrated_probability is None or not math.isfinite(float(calibrated_probability)):
        return CanaryDecision(False, "calibrated_probability_missing", normalized_mode, normalized_tier, global_count, coin_count)
    if threshold is None or float(calibrated_probability) < float(threshold):
        return CanaryDecision(False, "probability_below_threshold", normalized_mode, normalized_tier, global_count, coin_count)
    if in_cooldown:
        return CanaryDecision(False, "cooldown_active", normalized_mode, normalized_tier, global_count, coin_count)
    if global_count >= max(0, int(global_limit)):
        return CanaryDecision(False, "global_daily_budget_exhausted", normalized_mode, normalized_tier, global_count, coin_count)
    if coin_count >= max(0, int(coin_limit)):
        return CanaryDecision(False, "coin_daily_budget_exhausted", normalized_mode, normalized_tier, global_count, coin_count)
    return CanaryDecision(True, "policy_pass", normalized_mode, normalized_tier, global_count, coin_count)


def bundle_config_fingerprint(config: Mapping[str, Any]) -> str:
    """Stable fingerprint for the serving-relevant frozen configuration."""

    encoded = json.dumps(dict(config), sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def verify_bundle_config(
    frozen_info: Any,
    *,
    threshold_policy_version: str | None = None,
    expected_model_id: str | None = None,
    expected_feature_cols: Sequence[str] | None = None,
) -> tuple[bool, tuple[str, ...]]:
    """Check the immutable serving contract before an action alert.

    The function only compares declared metadata.  Artifact byte checksums
    remain the responsibility of ``score_snapshot``; both checks are needed.
    """

    reasons: list[str] = []
    model_id = str(getattr(frozen_info, "model_id", ""))
    if expected_model_id and model_id != expected_model_id:
        reasons.append("model_id_mismatch")
    cols = tuple(getattr(frozen_info, "feature_cols", ()) or ())
    if expected_feature_cols is not None and cols != tuple(expected_feature_cols):
        reasons.append("feature_schema_mismatch")
    policy = getattr(frozen_info, "threshold_policy", None) or {}
    if threshold_policy_version:
        declared = policy.get("version") if isinstance(policy, Mapping) else None
        if declared is not None and str(declared) != str(threshold_policy_version):
            reasons.append("threshold_policy_version_mismatch")
    schema = str(getattr(frozen_info, "schema_version", ""))
    if not schema.startswith("frozen_bundle_v1"):
        reasons.append("bundle_schema_unsupported")
    return not reasons, tuple(reasons)


@dataclass(frozen=True)
class DriftResult:
    status: str
    psi: float | None
    mean_delta: float | None
    n_reference: int
    n_current: int
    reasons: tuple[str, ...] = ()


def _psi(reference: Sequence[float], current: Sequence[float], bins: int = 10) -> float | None:
    if len(reference) == 0 or len(current) == 0:
        return None
    ref = [min(1.0, max(0.0, float(v))) for v in reference]
    cur = [min(1.0, max(0.0, float(v))) for v in current]
    def counts(values: Sequence[float]) -> list[float]:
        out = [0] * bins
        for value in values:
            idx = min(bins - 1, int(value * bins))
            out[idx] += 1
        total = float(len(values))
        return [max(1e-6, count / total) for count in out]
    ref_counts = counts(ref)
    cur_counts = counts(cur)
    return float(sum((c - r) * math.log(c / r) for r, c in zip(ref_counts, cur_counts)))


def compute_prediction_drift(
    reference: Sequence[float],
    current: Sequence[float],
    *,
    min_samples: int = 30,
    psi_warning: float = 0.10,
    psi_critical: float = 0.25,
) -> DriftResult:
    """Compare probability distributions without claiming a KPI on small n."""

    def finite_values(values: Sequence[float]) -> list[float]:
        result: list[float] = []
        for value in values:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(numeric):
                result.append(numeric)
        return result

    ref = finite_values(reference)
    cur = finite_values(current)
    if len(ref) < min_samples or len(cur) < min_samples:
        return DriftResult("insufficient_data", None, None, len(ref), len(cur), ("minimum_samples_not_met",))
    psi = _psi(ref, cur)
    mean_delta = float(statistics.fmean(cur) - statistics.fmean(ref))
    assert psi is not None
    if psi >= psi_critical:
        status = "critical"
        reasons = ("psi_critical",)
    elif psi >= psi_warning:
        status = "warning"
        reasons = ("psi_warning",)
    else:
        status = "ok"
        reasons = ()
    return DriftResult(status, psi, mean_delta, len(ref), len(cur), reasons)


@dataclass(frozen=True)
class HealthSnapshot:
    status: str
    checked_at: str
    mode: str
    heartbeat_age_minutes: float | None
    pending_outcomes: int | None
    kill_switch_active: bool
    bundle_valid: bool
    reasons: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)


def build_health_snapshot(
    *,
    mode: str,
    heartbeat_path: str | Path | None,
    pending_outcomes: int | None,
    kill_switch: KillSwitch | None = None,
    bundle_valid: bool = True,
    max_heartbeat_age_minutes: int = 15,
) -> HealthSnapshot:
    reasons: list[str] = []
    age: float | None = None
    if heartbeat_path is not None:
        path = Path(heartbeat_path)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            timestamp = datetime.fromisoformat(str(payload["timestamp"]))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            age = (utc_now() - timestamp.astimezone(timezone.utc)).total_seconds() / 60.0
            if age < -1.0:
                reasons.append("heartbeat_timestamp_in_future")
            elif age > max_heartbeat_age_minutes:
                reasons.append("heartbeat_stale")
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            reasons.append("heartbeat_missing_or_invalid")
    if pending_outcomes is not None and pending_outcomes > 0:
        reasons.append("outcome_backlog")
    if not bundle_valid:
        reasons.append("bundle_contract_invalid")
    switch_active = bool(kill_switch.active) if kill_switch else False
    if switch_active:
        reasons.append("kill_switch_active")
    status = "healthy" if not reasons else "degraded"
    return HealthSnapshot(
        status=status,
        checked_at=_iso(),
        mode=str(mode),
        heartbeat_age_minutes=age,
        pending_outcomes=pending_outcomes,
        kill_switch_active=switch_active,
        bundle_valid=bundle_valid,
        reasons=tuple(dict.fromkeys(reasons)),
        details={},
    )


class RollbackManager:
    """Persist serving mode/bundle transitions without deleting audit data."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def state(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"mode": "research", "active_bundle_id": None, "previous_bundle_id": None}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("rollback state must be an object")
            return payload
        except (OSError, ValueError, json.JSONDecodeError):
            # A corrupt rollout pointer must not enable canary.
            return {"mode": "shadow", "active_bundle_id": None, "previous_bundle_id": None, "reason": "rollback_state_invalid"}

    def promote(self, bundle_id: str, *, mode: str = "canary", actor: str = "operator") -> dict[str, Any]:
        if mode not in {"shadow", "canary", "production", "production_alerting"}:
            raise ValueError(f"unsupported serving mode: {mode}")
        previous = self.state().get("active_bundle_id")
        payload = {
            "mode": mode,
            "active_bundle_id": str(bundle_id),
            "previous_bundle_id": previous,
            "changed_at": _iso(),
            "actor": actor,
            "reason": "promote",
        }
        _atomic_json_write(self.path, payload)
        return payload

    def rollback_to_shadow(self, *, reason: str, actor: str = "operator") -> dict[str, Any]:
        current = self.state()
        payload = {
            **current,
            "mode": "shadow",
            "rollback_at": _iso(),
            "actor": actor,
            "reason": str(reason),
        }
        _atomic_json_write(self.path, payload)
        return payload

    def run_drill(self, *, audit_count_before: int, audit_count_after: int | None = None) -> dict[str, Any]:
        """Record a rollback drill; it never mutates prediction/audit rows."""

        after = audit_count_before if audit_count_after is None else int(audit_count_after)
        result = {
            "drill_id": f"rollback-{utc_now().strftime('%Y%m%dT%H%M%SZ')}",
            "performed_at": _iso(),
            "mode_after": self.state().get("mode", "shadow"),
            "audit_count_before": int(audit_count_before),
            "audit_count_after": after,
            "audit_preserved": after >= int(audit_count_before),
            "status": "pass" if after >= int(audit_count_before) else "fail",
        }
        report_path = self.path.with_name(f"{self.path.stem}_drill.json")
        _atomic_json_write(report_path, result)
        return result


__all__ = [
    "CanaryDecision",
    "DriftResult",
    "HealthSnapshot",
    "KillSwitch",
    "RollbackManager",
    "build_health_snapshot",
    "bundle_config_fingerprint",
    "compute_prediction_drift",
    "evaluate_canary_policy",
    "verify_bundle_config",
]
