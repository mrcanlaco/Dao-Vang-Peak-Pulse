from unittest.mock import patch, MagicMock
from dao_vang.data.collectors.coinmarketcap import (
    clean_symbol,
    resolve_token_meta,
    fetch_market_data,
    batch_fetch_market_data,
    fetch_market_cap,
    CoinMarketCapData,
)


def test_clean_symbol_normalization():
    assert clean_symbol("CVCUSDT") == "CVC"
    assert clean_symbol("1000PEPEUSDT") == "PEPE"
    assert clean_symbol("1000000MOGUSDT") == "MOG"
    assert clean_symbol("BTCUSDC") == "BTC"
    assert clean_symbol("ETHPERP") == "ETH"
    assert clean_symbol("LUNA2USDT") == "LUNA"
    assert clean_symbol("1MBABYDOGEUSDT") == "BABYDOGE"
    assert clean_symbol("RONINUSDT") == "RON"


def test_resolve_token_meta_offline():
    cvc_meta = resolve_token_meta("CVCUSDT")
    assert cvc_meta["slug"] == "civic"
    assert cvc_meta["name"] == "Civic"
    assert cvc_meta["cmc_url"] == "https://coinmarketcap.com/currencies/civic/"

    pepe_meta = resolve_token_meta("1000PEPEUSDT")
    assert pepe_meta["slug"] == "pepe"

    bonk_meta = resolve_token_meta("1000BONKUSDT")
    assert bonk_meta["slug"] == "bonk1"


@patch("httpx.Client.get")
def test_fetch_market_data_parses_cmc_response(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": "000000",
        "data": {
            "body": {
                "data": {
                    "CVC": [
                        {
                            "id": 1816,
                            "name": "Civic",
                            "symbol": "CVC",
                            "slug": "civic",
                            "is_active": 1,
                            "cmc_rank": 446,
                            "quote": {
                                "USD": {
                                    "market_cap": 37080433.9,
                                    "price": 0.03708,
                                }
                            },
                        },
                        {
                            "id": 9999,
                            "name": "Fake Coin",
                            "symbol": "CVC",
                            "slug": "fake-cvc",
                            "is_active": 0,
                            "cmc_rank": None,
                            "quote": {"USD": {"market_cap": None}},
                        },
                    ]
                }
            }
        },
    }
    mock_get.return_value = mock_resp

    data = fetch_market_data("CVCUSDT")
    assert data is not None
    assert data.symbol == "CVCUSDT"
    assert data.clean_symbol == "CVC"
    assert data.name == "Civic"
    assert data.slug == "civic"
    assert data.market_cap_usd == 37080433.9
    assert data.cmc_rank == 446
    assert data.cmc_url == "https://coinmarketcap.com/currencies/civic/"


@patch("httpx.Client.get")
def test_batch_fetch_market_data(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "code": "000000",
        "data": {
            "body": {
                "data": {
                    "BTC": [
                        {
                            "id": 1,
                            "name": "Bitcoin",
                            "symbol": "BTC",
                            "slug": "bitcoin",
                            "is_active": 1,
                            "cmc_rank": 1,
                            "quote": {"USD": {"market_cap": 1500000000000.0, "price": 80000.0}},
                        }
                    ],
                    "ETH": [
                        {
                            "id": 2,
                            "name": "Ethereum",
                            "symbol": "ETH",
                            "slug": "ethereum",
                            "is_active": 1,
                            "cmc_rank": 2,
                            "quote": {"USD": {"market_cap": 300000000000.0, "price": 2500.0}},
                        }
                    ],
                }
            }
        },
    }
    mock_get.return_value = mock_resp

    results = batch_fetch_market_data(["BTCUSDT", "ETHUSDT"])
    assert "BTCUSDT" in results
    assert "ETHUSDT" in results
    assert results["BTCUSDT"].slug == "bitcoin"
    assert results["BTCUSDT"].market_cap_usd == 1500000000000.0
    assert results["ETHUSDT"].slug == "ethereum"
    assert results["ETHUSDT"].market_cap_usd == 300000000000.0
