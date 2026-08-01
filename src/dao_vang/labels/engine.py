from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Tuple

import duckdb

from dao_vang.labels.models import DistributionLabelResult

# Type alias for a row from the database
RowType = Tuple[str, datetime, float, float, float, float, str]


class DistributionLabelEngine:
    """
    Engine to compute Distribution Label v0.1 based on LABEL_SPEC.md.
    """

    def __init__(
        self,
        target_drawdown: Decimal = Decimal("0.08"),
        max_adverse_excursion: Decimal = Decimal("0.04"),
        max_horizon_minutes: int = 1440,
    ):
        self.target_drawdown = target_drawdown
        self.max_ae = max_adverse_excursion
        self.max_horizon_minutes = max_horizon_minutes

    def compute_all(
        self, db: duckdb.DuckDBPyConnection, input_table: str
    ) -> List[DistributionLabelResult]:
        """
        Compute labels for all rows in the input table.
        The input table must have: symbol, feature_time, open, high, low, close, quality_status.
        """
        rows = db.query(
            f"SELECT symbol, feature_time, open, high, low, close, quality_status FROM {input_table} ORDER BY symbol, feature_time"
        ).fetchall()

        results = []

        for i in range(len(rows)):
            results.append(self._process_row(rows, i))

        return results

    def _process_row(self, rows: List[RowType], i: int) -> DistributionLabelResult:
        symbol, signal_time, o, h, l, c, qs = rows[i]
        P0 = Decimal(str(c)) if c is not None else None

        def null_result(reason: str) -> DistributionLabelResult:
            return DistributionLabelResult(
                signal_time=signal_time,
                symbol=symbol,
                signal_price=P0 if P0 is not None else Decimal("0"),
                exclusion_reason=reason,
            )

        if qs in ("invalid", "quarantined"):
            return null_result("invalid_signal_quality")

        if P0 is None or P0 <= 0:
            return null_result("invalid_signal_price")

        target_threshold = float(P0) * float(1 - self.target_drawdown)
        float(P0) * float(1 + self.max_ae)

        horizon_end_time = signal_time + timedelta(minutes=self.max_horizon_minutes)

        target_reached = False
        target_time: Optional[datetime] = None
        max_fe = 0.0
        future_max_high: Optional[float] = None
        future_min_low: Optional[float] = None

        prior_max_ae = 0.0
        final_mae = 0.0
        ambiguous = False
        gap_exceeded = False
        reached_horizon = False

        last_time = signal_time

        for j in range(i + 1, len(rows)):
            sym_j, fj, oj, hj, lj, cj, qsj = rows[j]

            if sym_j != symbol:
                break

            if fj > horizon_end_time:
                reached_horizon = True
                break

            gap_minutes = (fj - last_time).total_seconds() / 60
            if gap_minutes > 15:
                gap_exceeded = True
                break

            last_time = fj

            if future_max_high is None or hj > future_max_high:
                future_max_high = hj
            if future_min_low is None or lj < future_min_low:
                future_min_low = lj

            P0_float = float(P0)
            fe_j = float(1 - float(lj) / P0_float)
            ae_j = float(float(hj) / P0_float - 1)

            if fe_j > max_fe:
                max_fe = fe_j

            if not target_reached:
                if float(lj) <= target_threshold:
                    target_reached = True
                    target_time = fj
                    final_mae = max(prior_max_ae, ae_j)

                    if prior_max_ae <= float(self.max_ae) and ae_j > float(self.max_ae):
                        ambiguous = True
                else:
                    if ae_j > prior_max_ae:
                        prior_max_ae = ae_j

            if fj == horizon_end_time:
                reached_horizon = True
                break

        if not reached_horizon and (last_time < horizon_end_time):
            if gap_exceeded:
                return null_result("gap_exceeds_threshold")
            else:
                return null_result("missing_future_data")

        recorded_mae = final_mae if target_reached else prior_max_ae
        lead_time_minutes = None
        if target_time:
            lead_time_minutes = int((target_time - signal_time).total_seconds() / 60)

        label_value: Optional[int] = None
        exclusion_reason: Optional[str] = None

        if ambiguous:
            label_value = None
            exclusion_reason = "ambiguous_intrabar"
        else:
            if target_reached and prior_max_ae <= float(self.max_ae):
                label_value = 1
            else:
                label_value = 0

        return DistributionLabelResult(
            signal_time=signal_time,
            symbol=symbol,
            signal_price=P0,
            label_value=label_value,
            target_reached=target_reached,
            target_time=target_time,
            lead_time_minutes=lead_time_minutes,
            max_adverse_excursion=recorded_mae,
            max_favorable_excursion_24h=max_fe,
            future_max_high=Decimal(str(future_max_high))
            if future_max_high is not None
            else None,
            future_min_low=Decimal(str(future_min_low))
            if future_min_low is not None
            else None,
            exclusion_reason=exclusion_reason,
        )
