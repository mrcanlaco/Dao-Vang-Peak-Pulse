"""Alpha Quality Lab — Signal Intelligence & Model Quality Assurance.

Provides Triple-Barrier labeling, MFE/MAE signal attribution, market regime
classification, secondary meta-labeling execution filter, drift monitoring,
and alpha backtesting.
"""

from dao_vang.alpha_lab.alpha_backtester import AlphaBacktester, BacktestComparison
from dao_vang.alpha_lab.drift_guardian import (
    DriftGuardian,
    DriftReport,
    DriftStatus,
    calculate_brier_score,
    calculate_ece,
    calculate_psi,
)
from dao_vang.alpha_lab.meta_labeling import MetaFilterDecision, MetaLabelingModel
from dao_vang.alpha_lab.regime_classifier import (
    MarketRegime,
    RegimeState,
    classify_market_regimes,
    get_current_regime,
)
from dao_vang.alpha_lab.signal_attribution import (
    PerformanceSummary,
    calculate_expected_value,
    compute_mfe_mae,
    evaluate_signal_performance,
)
from dao_vang.alpha_lab.triple_barrier import (
    BarrierConfig,
    apply_triple_barrier,
    compute_atr,
    compute_daily_volatility,
)

__all__ = [
    "AlphaBacktester",
    "BacktestComparison",
    "BarrierConfig",
    "DriftGuardian",
    "DriftReport",
    "DriftStatus",
    "MarketRegime",
    "MetaFilterDecision",
    "MetaLabelingModel",
    "PerformanceSummary",
    "RegimeState",
    "apply_triple_barrier",
    "calculate_brier_score",
    "calculate_ece",
    "calculate_expected_value",
    "calculate_psi",
    "classify_market_regimes",
    "compute_atr",
    "compute_daily_volatility",
    "compute_mfe_mae",
    "evaluate_signal_performance",
    "get_current_regime",
]
