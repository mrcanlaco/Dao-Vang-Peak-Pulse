import pytest
from unittest.mock import patch, MagicMock
from dao_vang.config.settings import CoinGeckoConfig
from dao_vang.data.collectors.coingecko import fetch_market_data, _COINGECKO_ID_CACHE

@pytest.fixture(autouse=True)
def clear_cache():
    # Clear cache before each test, but restore pre-filled mappings
    original_cache = _COINGECKO_ID_CACHE.copy()
    _COINGECKO_ID_CACHE.clear()
    _COINGECKO_ID_CACHE.update({
        "uai": "unifai-network",
        "btc": "bitcoin",
        "pepe": "pepe",
    })
    yield
    _COINGECKO_ID_CACHE.clear()
    _COINGECKO_ID_CACHE.update(original_cache)

@patch("dao_vang.data.collectors.coingecko.httpx.Client")
def test_resolve_mapped_id(mock_client_class):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"market_data": {}}
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.get.return_value = mock_resp
    mock_client_class.return_value = mock_client_instance

    config = CoinGeckoConfig(market_cap_lookup_enabled=True)
    fetch_market_data("BTCUSDT", config)
    
    # Assert it used the pre-mapped 'bitcoin' ID directly, NO search
    mock_client_instance.get.assert_called_once_with(
        "https://api.coingecko.com/api/v3/coins/bitcoin",
        params={"localization": "false", "tickers": "false", "market_data": "true", "community_data": "false", "developer_data": "false", "sparkline": "false"}
    )

@patch("dao_vang.data.collectors.coingecko.httpx.Client")
def test_resolve_multiplier_id(mock_client_class):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"market_data": {}}
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.get.return_value = mock_resp
    mock_client_class.return_value = mock_client_instance

    config = CoinGeckoConfig(market_cap_lookup_enabled=True)
    fetch_market_data("1000PEPEUSDT", config)
    
    # Assert it stripped the multiplier and used the mapped 'pepe' ID
    mock_client_instance.get.assert_called_once_with(
        "https://api.coingecko.com/api/v3/coins/pepe",
        params={"localization": "false", "tickers": "false", "market_data": "true", "community_data": "false", "developer_data": "false", "sparkline": "false"}
    )

@patch("dao_vang.data.collectors.coingecko.httpx.Client")
def test_resolve_unknown_ticker(mock_client_class):
    # First call to /search, second call to /coins/{id}
    def mock_get(url, params=None):
        resp = MagicMock()
        resp.status_code = 200
        if "search" in url:
            resp.json.return_value = {
                "coins": [
                    {"id": "wrong-hype", "symbol": "whype"},
                    {"id": "hyperliquid", "symbol": "hype"}
                ]
            }
        else:
            resp.json.return_value = {"market_data": {}}
        return resp

    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.get.side_effect = mock_get
    mock_client_class.return_value = mock_client_instance

    config = CoinGeckoConfig(market_cap_lookup_enabled=True)
    fetch_market_data("HYPEUSDT", config)
    
    # Assert it called search first, found 'hyperliquid', and called it
    assert mock_client_instance.get.call_count == 2
    mock_client_instance.get.assert_any_call("https://api.coingecko.com/api/v3/search", params={"query": "hype"})
    mock_client_instance.get.assert_called_with(
        "https://api.coingecko.com/api/v3/coins/hyperliquid",
        params={"localization": "false", "tickers": "false", "market_data": "true", "community_data": "false", "developer_data": "false", "sparkline": "false"}
    )
