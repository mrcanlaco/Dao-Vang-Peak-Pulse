from unittest.mock import patch, MagicMock

from dao_vang.web.api_server import _resolve_market_cap_info, _settings
from dao_vang.data.collectors.coinmarketcap import CoinMarketCapData


@patch("dao_vang.data.collectors.coinmarketcap.fetch_market_data")
def test_resolve_market_cap_info_uses_coinmarketcap(mock_fetch_cmc):
    mock_fetch_cmc.return_value = CoinMarketCapData(
        symbol="CVCUSDT",
        clean_symbol="CVC",
        name="Civic",
        slug="civic",
        market_cap_usd=37_000_000.0,
        price_usd=0.037,
        cmc_rank=446,
        cmc_url="https://coinmarketcap.com/currencies/civic/",
    )
    from dao_vang.web.api_server import _MARKET_CAP_CACHE, _MARKET_CAP_CACHE_LOCK
    with _MARKET_CAP_CACHE_LOCK:
        _MARKET_CAP_CACHE.clear()

    result = _resolve_market_cap_info("CVCUSDT", fetch_remote=True)

    assert result is not None
    assert result["market_cap_source"] == "coinmarketcap"
    assert result["market_cap_usd"] == 37_000_000.0
    assert result["market_cap_str"] == "$37M"
    assert result["cmc_slug"] == "civic"
    assert result["cmc_url"] == "https://coinmarketcap.com/currencies/civic/"
    mock_fetch_cmc.assert_called_once()


@patch("dao_vang.data.collectors.binance_agent_os.fetch_market_cap", return_value=173_046_000.0)
def test_resolve_market_cap_info_falls_back_to_binance_agent_os(mock_agent_os, monkeypatch):
    monkeypatch.setattr(_settings.coinmarketcap, "enabled", False)
    monkeypatch.setattr(_settings.binance_agent_os, "enabled", True)

    from dao_vang.web.api_server import _MARKET_CAP_CACHE, _MARKET_CAP_CACHE_LOCK
    with _MARKET_CAP_CACHE_LOCK:
        _MARKET_CAP_CACHE.clear()

    result = _resolve_market_cap_info("UAIUSDT", fetch_remote=True)

    assert result is not None
    assert result["market_cap_source"] == "binance_agent_os"
    assert result["market_cap_usd"] == 173046000.0
    assert result["market_cap_str"] == "$173M"
    mock_agent_os.assert_called_once()
