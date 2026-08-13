"""Tests for pump filter — detect coins that pumped 50-300% in 1-5 days."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from dao_vang.config.settings import PumpFilterConfig
from dao_vang.scanner.pump_filter import analyze_pump, scan_pumps


@pytest.fixture
def config() -> PumpFilterConfig:
    return PumpFilterConfig()


def _make_klines(prices: list[float]) -> list[dict[str, Any]]:
    """Build klines from a list of close prices (1 day each)."""
    klines = []
    for i, price in enumerate(prices):
        klines.append(
            {
                "open_time": i,
                "open": prices[i - 1] if i > 0 else price,
                "high": price * 1.05,
                "low": price * 0.95,
                "close": price,
                "volume": 1000.0,
                "quote_volume": 5_000_000,
            }
        )
    return klines


class TestAnalyzePump:
    def test_strong_pump_at_peak(self, config: PumpFilterConfig) -> None:
        """Coin pumped 200% and still at peak → candidate."""
        # $1 → $3 over 3 days
        klines = _make_klines([1.0, 1.5, 2.5, 3.0])
        result = analyze_pump(klines, 0.50, 5.0, 0.70)
        assert result is not None
        assert result.pump_pct >= 1.5  # +150%+
        assert result.current_vs_peak >= 0.9  # still near peak

    def test_pumped_then_dumped(self, config: PumpFilterConfig) -> None:
        """Coin pumped 200% then dumped to 50% of peak → skip."""
        # $1 → $3 → $1.2 (40% of peak)
        klines = _make_klines([1.0, 2.0, 3.0, 1.2])
        result = analyze_pump(klines, 0.50, 5.0, 0.70)
        # current_vs_peak = 1.2/3.0 = 0.4 < 0.7 threshold → skip
        assert result is None

    def test_no_pump(self, config: PumpFilterConfig) -> None:
        """Coin only +10% → below threshold, skip."""
        klines = _make_klines([1.0, 1.03, 1.07, 1.10])
        result = analyze_pump(klines, 0.50, 5.0, 0.70)
        assert result is None

    def test_insufficient_data(self, config: PumpFilterConfig) -> None:
        """Only 1 kline → None."""
        result = analyze_pump([_make_klines([1.0])[0]], 0.50, 5.0, 0.70)
        assert result is None


class TestScanPumps:
    def test_empty_symbols(self, config: PumpFilterConfig) -> None:
        """Empty symbol list → empty result."""
        result = scan_pumps(config, [])
        assert result == []

    @patch("dao_vang.scanner.pump_filter.fetch_daily_klines")
    def test_scan_finds_candidate(
        self, mock_fetch: patch, config: PumpFilterConfig
    ) -> None:
        """Should find pump candidate from mocked klines."""

        def _mock_fetch(sym: str, base_url: str = "", days: int = 7):
            if sym == "BTCUSDT":
                return _make_klines([1.0, 1.5, 2.5, 3.0])
            return []

        mock_fetch.side_effect = _mock_fetch
        result = scan_pumps(config, ["BTCUSDT", "ETHUSDT"])
        assert len(result) == 1
        assert result[0].symbol == "BTCUSDT"
        assert result[0].pump_pct >= 1.5

    @patch("dao_vang.scanner.pump_filter.fetch_daily_klines")
    def test_scan_sorted_by_pump_desc(
        self, mock_fetch: patch, config: PumpFilterConfig
    ) -> None:
        """Results should be sorted by pump_pct descending."""

        def _mock_fetch(sym: str, base_url: str = "", days: int = 7):
            data = {
                "BTCUSDT": _make_klines([1.0, 2.0, 3.0, 3.5]),  # +250%
                "ETHUSDT": _make_klines([1.0, 1.3, 1.6, 1.8]),  # +80%
            }
            return data.get(sym, [])

        mock_fetch.side_effect = _mock_fetch
        result = scan_pumps(config, ["BTCUSDT", "ETHUSDT"])
        assert len(result) == 2
        assert result[0].pump_pct > result[1].pump_pct
        assert result[0].symbol == "BTCUSDT"
