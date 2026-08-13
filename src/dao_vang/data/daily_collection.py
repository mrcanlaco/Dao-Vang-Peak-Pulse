"""Daily derivative-data collection for symbols on the volatile altcoin watchlist.

Collects funding, open interest, taker ratio, global ratio and top trader ratio
from Binance USD-M futures for a list of symbols. Designed to run once per day
via cron / Task Scheduler to backfill the data needed by OI/taker-related
features.
"""

import uuid
from datetime import timedelta
from typing import Any, Dict, List

from dao_vang.config.settings import AppSettings
from dao_vang.domain.time import system_now
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.funding import FundingCollector
from dao_vang.data.collectors.open_interest import OpenInterestCollector
from dao_vang.data.collectors.ratios import GlobalRatioCollector, TopRatioCollector
from dao_vang.data.collectors.taker import TakerRatioCollector
from dao_vang.logging import get_logger

logger = get_logger(__name__)

_COLLECTORS: Dict[str, Any] = {
    "funding": FundingCollector,
    "open_interest": OpenInterestCollector,
    "taker_ratio": TakerRatioCollector,
    "global_ratio": GlobalRatioCollector,
    "top_ratio": TopRatioCollector,
}


def _run_id() -> str:
    today = system_now().strftime("%Y%m%d")
    return f"daily_derivatives_{today}_{uuid.uuid4().hex[:8]}"


def collect_derivatives(
    symbols: List[str],
    settings: AppSettings,
    hours_back: int = 24,
    run_id: str | None = None,
) -> Dict[str, Any]:
    """Collect derivative metrics for a list of symbols over the last N hours.

    Args:
        symbols: List of USD-M futures symbols (e.g. ["BTCUSDT", "ETHUSDT"]).
        settings: Application settings (data dir, API config, ...).
        hours_back: How many hours of history to fetch. Use 24 for a daily run.
        run_id: Optional run ID. Generated automatically if omitted.

    Returns:
        Summary dict with `run_id`, `symbols`, `hours_back`, `total_rows_raw`,
        `manifests` (one per symbol/collector), and `failures`.
    """
    if not symbols:
        raise ValueError("symbols must not be empty")
    if hours_back <= 0:
        raise ValueError("hours_back must be positive")

    effective_run_id = run_id or _run_id()
    end_time = system_now()
    start_time = end_time - timedelta(hours=hours_back)

    client = BinanceClient()
    manifests: List[Dict[str, Any]] = []
    failures: List[Dict[str, str]] = []
    total_rows_raw = 0

    for symbol in symbols:
        settings.binance.symbol = symbol
        for data_type, collector_cls in _COLLECTORS.items():
            collector = collector_cls(client, settings)
            try:
                manifest = collector.collect(start_time, end_time, effective_run_id)
            except Exception as exc:  # pragma: no cover - API failures logged
                logger.error(
                    "daily_collection_failed",
                    symbol=symbol,
                    data_type=data_type,
                    error=str(exc),
                )
                failures.append({
                    "symbol": symbol,
                    "data_type": data_type,
                    "error": str(exc),
                })
                continue

            manifests.append(
                {
                    "symbol": symbol,
                    "data_type": data_type,
                    "run_id": manifest.collection_run_id,
                    "rows_raw": manifest.rows_raw,
                    "status": manifest.status.value,
                }
            )
            total_rows_raw += manifest.rows_raw

    return {
        "run_id": effective_run_id,
        "symbols": symbols,
        "hours_back": hours_back,
        "range_start": start_time.isoformat(),
        "range_end": end_time.isoformat(),
        "total_rows_raw": total_rows_raw,
        "manifests": manifests,
        "failures": failures,
    }
