"""Tests for watchlist builder — manual + auto market scan by mode."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dao_vang.config.settings import ScannerConfig
from dao_vang.scanner.watchlist import (
    _is_stablecoin,
    add_to_watchlist,
    build_comparison_universe,
    build_scan_list,
    fetch_top_gainers,
    fetch_top_losers,
    fetch_top_volatile,
    fetch_top_volume,
    load_manual_watchlist,
    normalize_scan_modes,
    remove_from_watchlist,
    reset_tickers_cache,
    save_manual_watchlist,
)


def _ticker(
    symbol: str,
    *,
    change: float,
    volume: float,
    price: float = 1.0,
) -> dict[str, str]:
    return {
        "symbol": symbol,
        "priceChangePercent": str(change),
        "quoteVolume": str(volume),
        "lastPrice": str(price),
    }


@pytest.fixture
def config(tmp_path: Path) -> ScannerConfig:
    """ScannerConfig with temp watchlist path."""
    return ScannerConfig(
        max_coins=10,
        min_volume_usd=1_000_000,
        watchlist_path=tmp_path / "watchlist.json",
    )



@pytest.fixture(autouse=True)
def clear_cache() -> None:
    reset_tickers_cache()

class TestManualWatchlist:
    def test_load_nonexistent(self, tmp_path: Path) -> None:
        """Loading non-existent file should return empty list."""
        assert load_manual_watchlist(tmp_path / "nope.json") == []

    def test_load_valid(self, tmp_path: Path) -> None:
        """Loading valid JSON should return symbols."""
        path = tmp_path / "watchlist.json"
        path.write_text(json.dumps(["BTCUSDT", "ETHUSDT"]), encoding="utf-8")
        result = load_manual_watchlist(path)
        assert result == ["BTCUSDT", "ETHUSDT"]

    def test_load_uppercase(self, tmp_path: Path) -> None:
        """Symbols should be uppercased."""
        path = tmp_path / "watchlist.json"
        path.write_text(json.dumps(["btcusdt", "ethusdt"]), encoding="utf-8")
        result = load_manual_watchlist(path)
        assert result == ["BTCUSDT", "ETHUSDT"]

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Invalid JSON should return empty list, not raise."""
        path = tmp_path / "watchlist.json"
        path.write_text("not json", encoding="utf-8")
        assert load_manual_watchlist(path) == []

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Save then load should round-trip."""
        path = tmp_path / "watchlist.json"
        save_manual_watchlist(path, ["BTCUSDT", "ETHUSDT"])
        assert load_manual_watchlist(path) == ["BTCUSDT", "ETHUSDT"]

    def test_add_new(self, tmp_path: Path) -> None:
        """Add new symbol to watchlist."""
        path = tmp_path / "watchlist.json"
        result = add_to_watchlist(path, "SOLUSDT")
        assert "SOLUSDT" in result
        # Add another
        result = add_to_watchlist(path, "DOGEUSDT")
        assert "SOLUSDT" in result
        assert "DOGEUSDT" in result

    def test_add_duplicate(self, tmp_path: Path) -> None:
        """Adding duplicate should not create duplicate entry."""
        path = tmp_path / "watchlist.json"
        add_to_watchlist(path, "BTCUSDT")
        result = add_to_watchlist(path, "BTCUSDT")
        assert result.count("BTCUSDT") == 1

    def test_remove_existing(self, tmp_path: Path) -> None:
        """Remove existing symbol from watchlist."""
        path = tmp_path / "watchlist.json"
        save_manual_watchlist(path, ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
        result = remove_from_watchlist(path, "ETHUSDT")
        assert "ETHUSDT" not in result
        assert "BTCUSDT" in result
        assert "SOLUSDT" in result

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        """Removing non-existent symbol should not raise."""
        path = tmp_path / "watchlist.json"
        save_manual_watchlist(path, ["BTCUSDT"])
        result = remove_from_watchlist(path, "NONEXIST")
        assert result == ["BTCUSDT"]


class TestStablecoinFilter:
    def test_usdc_is_stablecoin(self) -> None:
        assert _is_stablecoin("USDCUSDT") is True

    def test_btc_not_stablecoin(self) -> None:
        assert _is_stablecoin("BTCUSDT") is False

    def test_dai_is_stablecoin(self) -> None:
        assert _is_stablecoin("DAIUSDT") is True

    def test_fdusd_is_stablecoin(self) -> None:
        assert _is_stablecoin("FDUSDUSDT") is True


class TestFetchTopGainers:
    @patch("dao_vang.scanner.watchlist.httpx.Client")
    def test_fetch_success(self, mock_client_cls: patch) -> None:
        """Should return sorted USDT pairs filtered by volume."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "symbol": "BTCUSDT",
                "priceChangePercent": "5.0",
                "quoteVolume": "5000000",
            },
            {
                "symbol": "ETHUSDT",
                "priceChangePercent": "3.0",
                "quoteVolume": "3000000",
            },
            {"symbol": "SOLUSDT", "priceChangePercent": "8.0", "quoteVolume": "500000"},
            {
                "symbol": "BNBUSDT",
                "priceChangePercent": "1.0",
                "quoteVolume": "2000000",
            },
        ]
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = fetch_top_gainers(min_volume_usd=1_000_000, limit=10)
        # SOL filtered out (volume < 1M), rest sorted by gain desc
        symbols = [d["symbol"] for d in result]
        assert symbols == ["BTCUSDT", "ETHUSDT", "BNBUSDT"]

    @patch("dao_vang.scanner.watchlist.httpx.Client")
    def test_fetch_http_error(self, mock_client_cls: patch) -> None:
        """HTTP error should return empty list, not raise."""
        import httpx

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.ConnectError("fail")
        mock_client_cls.return_value = mock_client

        assert fetch_top_gainers() == []

    @patch("dao_vang.scanner.watchlist.httpx.Client")
    def test_exclude_stablecoins(self, mock_client_cls: patch) -> None:
        """Stablecoins should be excluded when exclude_stablecoins=True."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"symbol": "USDCUSDT", "priceChangePercent": "0.01", "quoteVolume": "5000000"},
            {"symbol": "BTCUSDT", "priceChangePercent": "5.0", "quoteVolume": "5000000"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = fetch_top_gainers(exclude_stablecoins=True)
        symbols = [d["symbol"] for d in result]
        assert "USDCUSDT" not in symbols
        assert "BTCUSDT" in symbols


class TestFetchTopLosers:
    @patch("dao_vang.scanner.watchlist.httpx.Client")
    def test_sorted_by_loss(self, mock_client_cls: patch) -> None:
        """Should return sorted by priceChangePercent asc (biggest losers first)."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"symbol": "BTCUSDT", "priceChangePercent": "5.0", "quoteVolume": "5000000"},
            {"symbol": "ETHUSDT", "priceChangePercent": "-3.0", "quoteVolume": "3000000"},
            {"symbol": "SOLUSDT", "priceChangePercent": "-10.0", "quoteVolume": "5000000"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = fetch_top_losers(min_volume_usd=1_000_000)
        symbols = [d["symbol"] for d in result]
        assert symbols == ["SOLUSDT", "ETHUSDT", "BTCUSDT"]


class TestFetchTopVolume:
    @patch("dao_vang.scanner.watchlist.httpx.Client")
    def test_sorted_by_volume(self, mock_client_cls: patch) -> None:
        """Should return sorted by quoteVolume desc."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"symbol": "BTCUSDT", "priceChangePercent": "1.0", "quoteVolume": "5000000"},
            {"symbol": "ETHUSDT", "priceChangePercent": "2.0", "quoteVolume": "10000000"},
            {"symbol": "SOLUSDT", "priceChangePercent": "3.0", "quoteVolume": "3000000"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = fetch_top_volume(min_volume_usd=1_000_000)
        symbols = [d["symbol"] for d in result]
        assert symbols == ["ETHUSDT", "BTCUSDT", "SOLUSDT"]


class TestFetchTopVolatile:
    @patch("dao_vang.scanner.watchlist.httpx.Client")
    def test_sorted_by_abs_change(self, mock_client_cls: patch) -> None:
        """Should return sorted by |priceChangePercent| desc."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"symbol": "BTCUSDT", "priceChangePercent": "2.0", "quoteVolume": "5000000"},
            {"symbol": "ETHUSDT", "priceChangePercent": "-15.0", "quoteVolume": "3000000"},
            {"symbol": "SOLUSDT", "priceChangePercent": "8.0", "quoteVolume": "5000000"},
        ]
        mock_response.raise_for_status = MagicMock()
        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value = mock_client

        result = fetch_top_volatile(min_volume_usd=1_000_000)
        symbols = [d["symbol"] for d in result]
        # |−15| > |8| > |2|
        assert symbols == ["ETHUSDT", "SOLUSDT", "BTCUSDT"]


class TestBuildScanList:
    def test_manual_only(self, config: ScannerConfig) -> None:
        """With no gainers (mocked empty), should return manual watchlist."""
        save_manual_watchlist(config.watchlist_path, ["BTCUSDT", "ETHUSDT"])
        with patch("dao_vang.scanner.watchlist.fetch_top_gainers", return_value=[]):
            result = build_scan_list(config)
        assert "BTCUSDT" in result
        assert "ETHUSDT" in result

    def test_auto_only(self, config: ScannerConfig) -> None:
        """With no manual watchlist, should return auto gainers."""
        gainers = [
            {"symbol": "SOLUSDT"},
            {"symbol": "DOGEUSDT"},
            {"symbol": "ADAUSDT"},
        ]
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_gainers",
            return_value=gainers,
        ):
            result = build_scan_list(config)
        assert "SOLUSDT" in result
        assert "DOGEUSDT" in result
        assert "ADAUSDT" in result

    def test_merge_with_dedup(self, config: ScannerConfig) -> None:
        """Manual + auto should merge with de-dup, manual first."""
        save_manual_watchlist(config.watchlist_path, ["BTCUSDT", "ETHUSDT"])
        gainers = [
            {"symbol": "ETHUSDT"},  # dup with manual
            {"symbol": "SOLUSDT"},
            {"symbol": "DOGEUSDT"},
        ]
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_gainers",
            return_value=gainers,
        ):
            result = build_scan_list(config)
        # Manual first, then auto without dups
        assert result[0] == "BTCUSDT"
        assert result[1] == "ETHUSDT"
        assert "SOLUSDT" in result
        assert "DOGEUSDT" in result

    def test_capped_at_max_coins(self, config: ScannerConfig) -> None:
        """Result should not exceed max_coins."""
        config.max_coins = 3
        save_manual_watchlist(config.watchlist_path, ["BTCUSDT", "ETHUSDT"])
        gainers = [{"symbol": f"COIN{i}USDT"} for i in range(20)]
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_gainers",
            return_value=gainers,
        ):
            result = build_scan_list(config)
        assert len(result) <= config.max_coins
        # Manual should be included first
        assert result[0] == "BTCUSDT"
        assert result[1] == "ETHUSDT"

    def test_empty_when_no_source(self, config: ScannerConfig) -> None:
        """No manual + no gainers = empty list (or BTC if include_btc)."""
        config.include_btc = False
        with patch("dao_vang.scanner.watchlist.fetch_top_gainers", return_value=[]):
            assert build_scan_list(config) == []

    def test_include_btc(self, config: ScannerConfig) -> None:
        """BTC should be included when include_btc=True."""
        config.include_btc = True
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_gainers",
            return_value=[{"symbol": "ETHUSDT"}],
        ):
            result = build_scan_list(config)
        assert "BTCUSDT" in result

    def test_scan_mode_losers(self, config: ScannerConfig) -> None:
        """scan_mode=losers should call fetch_top_losers."""
        config.scan_mode = "losers"
        losers = [{"symbol": "SOLUSDT"}, {"symbol": "DOGEUSDT"}]
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_losers",
            return_value=losers,
        ) as mock_losers:
            result = build_scan_list(config)
        mock_losers.assert_called_once()
        assert "SOLUSDT" in result

    def test_scan_mode_volume(self, config: ScannerConfig) -> None:
        """scan_mode=volume should call fetch_top_volume."""
        config.scan_mode = "volume"
        volume = [{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}]
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_volume",
            return_value=volume,
        ) as mock_vol:
            result = build_scan_list(config)
        mock_vol.assert_called_once()
        assert "BTCUSDT" in result

    def test_scan_mode_manual_uses_only_persisted_watchlist(self, config: ScannerConfig) -> None:
        """Manual mode must not silently add automatic market symbols."""
        config.scan_mode = "manual"
        config.include_btc = False
        save_manual_watchlist(config.watchlist_path, ["SUIUSDT", "INJUSDT"])
        with patch("dao_vang.scanner.watchlist.fetch_top_gainers") as mock_gainers:
            result = build_scan_list(config)

        mock_gainers.assert_not_called()
        assert result == ["SUIUSDT", "INJUSDT"]

    def test_scan_mode_all(self, config: ScannerConfig) -> None:
        """scan_mode=all should combine gainers + losers + volume."""
        config.scan_mode = "all"
        config.include_btc = False
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_gainers",
            return_value=[{"symbol": "BTCUSDT"}],
        ), patch(
            "dao_vang.scanner.watchlist.fetch_top_losers",
            return_value=[{"symbol": "ETHUSDT"}, {"symbol": "BTCUSDT"}],
        ), patch(
            "dao_vang.scanner.watchlist.fetch_top_volume",
            return_value=[{"symbol": "SOLUSDT"}],
        ):
            result = build_scan_list(config)
        # All 3 unique symbols should be present
        assert "BTCUSDT" in result
        assert "ETHUSDT" in result
        assert "SOLUSDT" in result

    def test_scan_mode_multiple_groups_merges_and_deduplicates(self, config: ScannerConfig) -> None:
        """Multiple selected groups should be combined in selection order."""
        config.scan_mode = "gainers,losers"
        config.include_btc = False
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_gainers",
            return_value=[{"symbol": "BTCUSDT"}, {"symbol": "SOLUSDT"}],
        ) as mock_gainers, patch(
            "dao_vang.scanner.watchlist.fetch_top_losers",
            return_value=[{"symbol": "SOLUSDT"}, {"symbol": "ETHUSDT"}],
        ) as mock_losers:
            result = build_scan_list(config)

        mock_gainers.assert_called_once()
        mock_losers.assert_called_once()
        assert result == ["BTCUSDT", "SOLUSDT", "ETHUSDT"]

    def test_normalize_scan_modes_supports_legacy_all(self) -> None:
        assert normalize_scan_modes("all") == ["gainers", "losers", "volume"]
        assert normalize_scan_modes(["volatile", "gainers", "volatile"]) == ["volatile", "gainers"]

    def test_min_price_change_filter(self, config: ScannerConfig) -> None:
        """min_price_change_pct should filter out low-change coins."""
        config.min_price_change_pct = 10.0
        config.include_btc = False
        gainers = [
            {"symbol": "BTCUSDT", "priceChangePercent": "5.0", "quoteVolume": "5000000"},
            {"symbol": "ETHUSDT", "priceChangePercent": "15.0", "quoteVolume": "5000000"},
        ]
        with patch(
            "dao_vang.scanner.watchlist.fetch_top_gainers",
            return_value=gainers,
        ):
            # The filter happens inside fetch_top_gainers, but we mock it
            # So we test the filter logic directly via _filter_tickers
            from dao_vang.scanner.watchlist import _filter_tickers
            filtered = _filter_tickers(
                gainers, min_volume_usd=1_000_000,
                min_price_change_pct=10.0, exclude_stablecoins=True,
            )
            symbols = [d["symbol"] for d in filtered]
            assert "BTCUSDT" not in symbols  # 5% < 10% threshold
            assert "ETHUSDT" in symbols      # 15% >= 10% threshold


class TestComparisonUniverse:
    def test_pins_production_symbols_and_includes_low_change_liquidity(
        self, config: ScannerConfig
    ) -> None:
        config.max_coins = 4
        config.min_price_change_pct = 5.0
        tickers = [
            _ticker("AAAUSDT", change=12, volume=2_000_000),
            _ticker("BBBUSDT", change=9, volume=3_000_000),
            _ticker("CCCUSDT", change=1, volume=90_000_000),
            _ticker("BTCUSDT", change=0.5, volume=100_000_000),
            _ticker("USDCUSDT", change=20, volume=100_000_000),
        ]

        with patch(
            "dao_vang.scanner.watchlist.fetch_all_tickers",
            return_value=tickers,
        ):
            rows = build_comparison_universe(
                config,
                pinned_symbols=["BBBUSDT", "AAAUSDT"],
                limit=4,
            )

        assert [row["symbol"] for row in rows[:2]] == ["BBBUSDT", "AAAUSDT"]
        assert len(rows) == 4
        assert "CCCUSDT" in {row["symbol"] for row in rows}
        assert "BTCUSDT" in {row["symbol"] for row in rows}
        assert "USDCUSDT" not in {row["symbol"] for row in rows}

    def test_respects_volume_floor(self, config: ScannerConfig) -> None:
        config.include_btc = False
        tickers = [
            _ticker("AAAUSDT", change=50, volume=999_999),
            _ticker("BBBUSDT", change=1, volume=2_000_000),
        ]
        with patch(
            "dao_vang.scanner.watchlist.fetch_all_tickers",
            return_value=tickers,
        ):
            rows = build_comparison_universe(config, limit=10)

        assert [row["symbol"] for row in rows] == ["BBBUSDT"]
