from unittest.mock import MagicMock, patch

from dao_vang.config.settings import CoinGeckoConfig
from dao_vang.data.collectors.coingecko import fetch_market_data


@patch("dao_vang.data.collectors.coingecko.httpx.Client")
def test_fetch_market_data_uses_circulating_market_cap_not_fdv(mock_client_class):
    # Setup mock response
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "id": "unifai-network",
        "symbol": "uai",
        "name": "UnifAI Network",
        "market_data": {
            "current_price": {"usd": 0.71},
            "total_volume": {"usd": 3160560},
            "market_cap": {"usd": 173046000},
            "fully_diluted_valuation": {"usd": 724041000},
            "price_change_percentage_24h": 19.27,
            "price_change_percentage_7d": 5.4,
        }
    }
    
    mock_client_instance = MagicMock()
    mock_client_instance.__enter__.return_value = mock_client_instance
    mock_client_instance.get.return_value = mock_resp
    mock_client_class.return_value = mock_client_instance

    config = CoinGeckoConfig(market_cap_lookup_enabled=True)
    
    # Execute
    result = fetch_market_data("UAIUSDT", config)

    # Assert
    assert result is not None
    assert result.symbol == "uai"
    # Ensure it extracts market_cap (173M), NOT fully_diluted_valuation (724M)
    assert result.market_cap_usd == 173046000.0

