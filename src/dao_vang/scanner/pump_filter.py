"""Pump filter — find coins that pumped 50-300% in last 1-5 days.

Core principle: "tăng đột biến thì mới sụt đột biến".
Only coins with abnormal pump are candidates for short distribution.

Skip coins that already dumped (close < 70% of peak) — distribution done.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from dao_vang.config.settings import PumpFilterConfig
from dao_vang.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PumpCandidate:
    """A coin that passed the pump filter."""

    symbol: str
    pump_pct: float  # max cumulative return in window (e.g. 1.8 = +180%)
    pump_days: int  # how many days to reach peak (1-5)
    current_vs_peak: float  # close / peak (1.0 = at peak, 0.7 = dumped 30%)
    peak_price: float
    current_price: float
    quote_volume: float


def fetch_daily_klines(
    symbol: str,
    base_url: str = "https://fapi.binance.com",
    days: int = 7,
) -> list[dict[str, Any]]:
    """Fetch daily klines for a symbol from Binance USD-M futures.

    Returns list of dicts with keys: open_time, open, high, low, close,
    volume, quote_volume.
    """
    try:
        with httpx.Client(timeout=2.5) as client:
            resp = client.get(
                f"{base_url}/fapi/v1/klines",
                params={
                    "symbol": symbol,
                    "interval": "1d",
                    "limit": days + 1,
                },
            )
            resp.raise_for_status()
            raw = resp.json()
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("pump_kline_fetch_failed", symbol=symbol, error=str(exc))
        return []

    klines: list[dict[str, Any]] = []
    for k in raw:
        klines.append(
            {
                "open_time": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "quote_volume": float(k[7]),
            }
        )
    return klines


def analyze_pump(
    klines: list[dict[str, Any]],
    min_pump_pct: float,
    max_pump_pct: float,
    dump_threshold: float,
) -> PumpCandidate | None:
    """Analyze klines to detect pump pattern.

    Returns PumpCandidate if coin is still in pump phase (not yet dumped),
    None if no pump or already dumped.
    """
    if len(klines) < 2:
        return None

    # Compute cumulative return from each starting day to each subsequent day
    # Find max pump in 1-5 day window
    best_pump_pct = 0.0
    best_pump_days = 0
    peak_price = 0.0

    for start_idx in range(len(klines)):
        for end_idx in range(start_idx + 1, len(klines)):
            window_days = end_idx - start_idx
            if window_days > 5:  # only 1-5 day windows
                break
            start_close = klines[start_idx]["open"]
            end_high = max(klines[j]["high"] for j in range(start_idx, end_idx + 1))
            if start_close <= 0:
                continue
            pump_pct = (end_high / start_close) - 1.0
            if pump_pct > best_pump_pct:
                best_pump_pct = pump_pct
                best_pump_days = window_days
                peak_price = end_high

    # Filter by pump magnitude
    if best_pump_pct < min_pump_pct or best_pump_pct > max_pump_pct:
        return None

    # Check if already dumped — current close < threshold * peak
    current_close = klines[-1]["close"]
    current_vs_peak = current_close / peak_price if peak_price > 0 else 0.0

    if current_vs_peak < dump_threshold:
        # Already dumped — distribution done, skip
        return None

    return PumpCandidate(
        symbol="",  # filled by caller
        pump_pct=best_pump_pct,
        pump_days=best_pump_days,
        current_vs_peak=current_vs_peak,
        peak_price=peak_price,
        current_price=current_close,
        quote_volume=klines[-1]["quote_volume"],
    )


def scan_pumps(
    config: PumpFilterConfig,
    symbols: list[str],
    base_url: str = "https://fapi.binance.com",
) -> list[PumpCandidate]:
    """Scan a list of symbols for pump pattern.

    Args:
        config: PumpFilterConfig with thresholds.
        symbols: List of symbols to scan (e.g. ["BTCUSDT", "ETHUSDT"]).
        base_url: Binance USD-M futures base URL.

    Returns list of PumpCandidate sorted by pump_pct desc.
    """
    candidates: list[PumpCandidate] = []
    for symbol in symbols:
        klines = fetch_daily_klines(symbol, base_url, days=config.lookback_days + 2)
        if not klines:
            continue
        candidate = analyze_pump(
            klines,
            min_pump_pct=config.min_pump_pct,
            max_pump_pct=config.max_pump_pct,
            dump_threshold=config.dump_threshold,
        )
        if candidate is None:
            continue
        # Filter by volume
        if candidate.quote_volume < config.min_volume_usd:
            continue
        candidate = PumpCandidate(
            symbol=symbol,
            pump_pct=candidate.pump_pct,
            pump_days=candidate.pump_days,
            current_vs_peak=candidate.current_vs_peak,
            peak_price=candidate.peak_price,
            current_price=candidate.current_price,
            quote_volume=candidate.quote_volume,
        )
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.pump_pct, reverse=True)
    logger.info(
        "pump_scan_done",
        n_scanned=len(symbols),
        n_candidates=len(candidates),
    )
    return candidates
