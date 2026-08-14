"""Alpha Backtester and Meta-Labeling Microstructure Simulator.

Simulates and compares end-to-end trading performance of raw primary signals
versus meta-model filtered signals with realistic transaction costs, slippage,
and regime conditioning.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from dao_vang.alpha_lab.meta_labeling import MetaLabelingModel
from dao_vang.alpha_lab.regime_classifier import classify_market_regimes
from dao_vang.alpha_lab.signal_attribution import (
    PerformanceSummary,
    compute_mfe_mae,
    evaluate_signal_performance,
)
from dao_vang.alpha_lab.triple_barrier import apply_triple_barrier


@dataclass(frozen=True)
class BacktestComparison:
    """Side-by-side performance comparison between raw and meta-filtered signals."""

    total_test_signals: int
    executed_signals: int
    dropped_signals: int
    pass_rate: float
    unfiltered_summary: PerformanceSummary
    filtered_summary: PerformanceSummary
    ev_improvement_bps: float
    winrate_improvement_pct: float
    profit_factor_improvement: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_test_signals": self.total_test_signals,
            "executed_signals": self.executed_signals,
            "dropped_signals": self.dropped_signals,
            "pass_rate": self.pass_rate,
            "unfiltered_summary": self.unfiltered_summary.to_dict(),
            "filtered_summary": self.filtered_summary.to_dict(),
            "ev_improvement_bps": self.ev_improvement_bps,
            "winrate_improvement_pct": self.winrate_improvement_pct,
            "profit_factor_improvement": self.profit_factor_improvement,
        }


class AlphaBacktester:
    """End-to-end validation engine for Alpha Quality Lab."""

    def __init__(
        self,
        pt_sl: tuple[float, float] = (2.0, 1.0),
        min_ret: float = 0.005,
        fee_bps: float = 8.0,
        meta_threshold: float = 0.60,
    ) -> None:
        self.pt_sl = pt_sl
        self.min_ret = min_ret
        self.fee_bps = fee_bps
        self.meta_threshold = meta_threshold

    def run_simulation(
        self,
        prices: pd.DataFrame,
        signals_df: pd.DataFrame,
        train_ratio: float = 0.70,
        high_col: str = "high",
        low_col: str = "low",
        close_col: str = "close",
    ) -> BacktestComparison:
        """Run a walk-forward train-and-test simulation.

        Parameters
        ----------
        prices : pd.DataFrame
            OHLCV time-series.
        signals_df : pd.DataFrame
            Candidate signals with timestamps, side, and features.
        train_ratio : float
            Fraction of signals used for training the meta-model (default: 0.70).

        Returns
        -------
        BacktestComparison
            Comparative performance report of Unfiltered vs Filtered signals
            on the test set.
        """
        # 1. Classify Regimes across price history
        regime_prices = classify_market_regimes(
            prices,
            high_col=high_col,
            low_col=low_col,
            close_col=close_col,
        )

        # 2. Enrich signals with regime information if not present
        sig_enriched = signals_df.copy()
        if "regime" not in sig_enriched.columns:
            regimes = []
            for ts in sig_enriched.index:
                if ts in regime_prices.index:
                    regimes.append(regime_prices.loc[ts, "regime"])
                else:
                    locs = regime_prices.index.get_indexer([ts], method="ffill")
                    if locs[0] != -1:
                        regimes.append(regime_prices.iloc[locs[0]]["regime"])
                    else:
                        regimes.append("SIDEWAY_DISTRIBUTION")
            sig_enriched["regime"] = regimes

        # 3. Apply Triple-Barrier Labeling
        labeled = apply_triple_barrier(
            prices=prices,
            events=sig_enriched,
            pt_sl=self.pt_sl,
            min_ret=self.min_ret,
        )

        # 4. Enrich with MFE / MAE
        enriched = compute_mfe_mae(
            prices=prices,
            labeled_events=labeled,
            high_col=high_col,
            low_col=low_col,
            close_col=close_col,
        )

        # Merge original features back into labeled dataset
        for col in sig_enriched.columns:
            if col not in enriched.columns:
                enriched[col] = sig_enriched[col]

        total_samples = len(enriched)
        split_idx = int(total_samples * train_ratio)

        train_data = enriched.iloc[:split_idx]
        test_data = enriched.iloc[split_idx:]

        if len(test_data) == 0:
            raise ValueError("Insufficient signal samples to form a test set.")

        # 5. Train Meta-Model on In-Sample data
        meta_model = MetaLabelingModel(threshold=self.meta_threshold)
        y_train = train_data["label"].to_numpy()
        meta_model.fit(train_data, y_train)

        # 6. Evaluate Unfiltered Test Signals
        unfiltered_summary = evaluate_signal_performance(
            test_data, fee_bps=self.fee_bps
        )

        # 7. Evaluate Filtered Test Signals (Approved by Meta-Model)
        filtered_indices = []
        for idx, row in test_data.iterrows():
            decision = meta_model.filter_signal(
                features=row,
                primary_prob=float(row.get("primary_probability", 0.70)),
                regime=str(row.get("regime", "SIDEWAY_DISTRIBUTION")),
                threshold_override=self.meta_threshold,
            )
            if decision.should_execute:
                filtered_indices.append(idx)

        if len(filtered_indices) > 0:
            filtered_test_data = test_data.loc[filtered_indices]
            filtered_summary = evaluate_signal_performance(
                filtered_test_data, fee_bps=self.fee_bps
            )
        else:
            filtered_summary = evaluate_signal_performance(
                test_data.iloc[0:0], fee_bps=self.fee_bps
            )

        pass_rate = len(filtered_indices) / len(test_data)
        dropped_count = len(test_data) - len(filtered_indices)

        ev_diff_bps = (
            filtered_summary.expected_value_bps - unfiltered_summary.expected_value_bps
        )
        winrate_diff_pct = (
            filtered_summary.win_rate - unfiltered_summary.win_rate
        ) * 100.0
        pf_diff = filtered_summary.profit_factor - unfiltered_summary.profit_factor

        return BacktestComparison(
            total_test_signals=len(test_data),
            executed_signals=len(filtered_indices),
            dropped_signals=dropped_count,
            pass_rate=pass_rate,
            unfiltered_summary=unfiltered_summary,
            filtered_summary=filtered_summary,
            ev_improvement_bps=ev_diff_bps,
            winrate_improvement_pct=winrate_diff_pct,
            profit_factor_improvement=pf_diff,
        )
