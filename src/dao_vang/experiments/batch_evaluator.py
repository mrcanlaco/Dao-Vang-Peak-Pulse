import logging
from typing import Callable, cast

import numpy as np
import pandas as pd

from dao_vang.config.settings import ThresholdPolicy
from dao_vang.experiments.forward_test import FrozenModelInfo
from dao_vang.scoring.frozen_inference import (
    FrozenInferenceError,
    _load_metadata,
    _threshold_contract,
    load_verified_bundle,
)

logger = logging.getLogger(__name__)

def score_snapshot_batch(
    df: pd.DataFrame,
    frozen_info: FrozenModelInfo,
    threshold_policy: ThresholdPolicy,
) -> pd.DataFrame:
    """Vectorized scoring for a batch of snapshots.
    
    Returns a DataFrame with the exact same index as `df`.
    Rows missing features or failing range checks will have is_usable=False.
    Bundle-level failures raise FrozenInferenceError before predicting.
    """
    metadata = _load_metadata(frozen_info)
    
    # 1. Fail-closed Bundle Loading
    model, calibrator_obj, is_precalibrated = load_verified_bundle(frozen_info, metadata)
    high_threshold, _, policy_version = _threshold_contract(
        frozen_info, threshold_policy, metadata
    )
    
    n_rows = len(df)
    out = pd.DataFrame(index=df.index)
    out["model_id"] = frozen_info.model_id
    out["threshold_policy_version"] = policy_version
    out["threshold"] = high_threshold
    out["model_probability"] = np.nan
    out["calibrated_probability"] = np.nan
    
    is_usable = np.ones(n_rows, dtype=bool)
    reasons = np.full(n_rows, "", dtype=object)
    
    # Row Validation
    missing_features = [c for c in frozen_info.feature_cols if c not in df.columns]
    if missing_features:
        is_usable[:] = False
        reasons[:] = f"missing_features:{','.join(missing_features)}"
    else:
        has_nan = np.asarray(df[frozen_info.feature_cols].isna().any(axis=1), dtype=bool)
        is_usable[has_nan] = False
        reasons[has_nan] = "missing_feature_values"
        
    out["is_usable"] = is_usable
    out["reason"] = reasons
    
    if not is_usable.any():
        return out
        
    valid_idx = np.where(is_usable)[0]
    # Extract just the valid rows, keep their original index order internally via valid_idx
    X_valid = df.iloc[valid_idx][frozen_info.feature_cols]
    
    # 3. Prediction
    try:
        if hasattr(model, "predict_proba"):
            probs = np.asarray(model.predict_proba(X_valid)[:, 1], dtype=float)
        else:
            preds = np.asarray(model.predict(X_valid), dtype=float)
            probs = np.where(preds > 0.5, 1.0, 0.0)
    except Exception as exc:
        raise FrozenInferenceError(f"Batch model prediction failed: {exc}")
        
    out_of_range = ~np.isfinite(probs) | (probs < 0.0) | (probs > 1.0)
    if out_of_range.any():
        bad_local_idx = np.where(out_of_range)[0]
        bad_global_idx = valid_idx[bad_local_idx]
        is_usable[bad_global_idx] = False
        reasons[bad_global_idx] = "model_probability_out_of_range"
        
        good_local_idx = np.where(~out_of_range)[0]
        valid_idx = valid_idx[good_local_idx]
        probs = probs[good_local_idx]
        
    if len(probs) == 0:
        out["is_usable"] = is_usable
        out["reason"] = reasons
        return out
        
    # Assign valid probabilities using iloc to bypass index alignment issues
    out.iloc[valid_idx, out.columns.get_loc("model_probability")] = probs
    
    # 4. Calibration
    try:
        if is_precalibrated:
            cal_probs = probs
        elif hasattr(calibrator_obj, "predict_proba"):
            cal_probs = np.asarray(calibrator_obj.predict_proba(probs.reshape(-1, 1))[:, 1], dtype=float)
        elif hasattr(calibrator_obj, "transform"):
            cal_probs = np.asarray(calibrator_obj.transform(probs), dtype=float)
        elif callable(calibrator_obj):
            calibrator_func = cast(Callable[[float], float], calibrator_obj)
            cal_probs = np.asarray([float(calibrator_func(p)) for p in probs], dtype=float)
        else:
            raise FrozenInferenceError("Batch calibration failed: Invalid calibrator type")
    except Exception as exc:
        raise FrozenInferenceError(f"Batch calibration transform failed: {exc}")
        
    cal_out_of_range = ~np.isfinite(cal_probs) | (cal_probs < 0.0) | (cal_probs > 1.0)
    if cal_out_of_range.any():
        bad_local_idx = np.where(cal_out_of_range)[0]
        bad_global_idx = valid_idx[bad_local_idx]
        is_usable[bad_global_idx] = False
        reasons[bad_global_idx] = "calibrator_out_of_range"
        
        good_local_idx = np.where(~cal_out_of_range)[0]
        valid_idx = valid_idx[good_local_idx]
        cal_probs = cal_probs[good_local_idx]
        
    out.iloc[valid_idx, out.columns.get_loc("calibrated_probability")] = cal_probs
    out["is_usable"] = is_usable
    out["reason"] = reasons
    
    return out
