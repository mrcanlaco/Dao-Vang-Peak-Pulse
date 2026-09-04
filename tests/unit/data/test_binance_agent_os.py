from __future__ import annotations

from dao_vang.config.settings import BinanceAgentOSConfig
from dao_vang.data.collectors.binance_agent_os import fetch_market_cap


def test_fetch_market_cap_uses_binance_agent_os_search(monkeypatch):
    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "code": "000000",
                "data": [
                    {
                        "symbol": "BTC",
                        "marketCap": "1900000000000",
                        "volume24h": "1000000000",
                    }
                ],
            }

    class MockClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["headers"]["User-Agent"] == "dao-vang/binance-agent-os"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, *args, **kwargs):
            assert args[0].endswith("/bapi/defi/v5/public/wallet-direct/buw/wallet/market/token/search/ai")
            assert kwargs["params"]["keyword"] == "BTC"
            assert kwargs["params"]["orderBy"] == "volume24h"
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockClient)
    config = BinanceAgentOSConfig(enabled=True)
    assert fetch_market_cap("BTCUSDT", config) == 1_900_000_000_000


def test_fetch_market_cap_prefers_exact_symbol_match(monkeypatch):
    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {
                "code": "000000",
                "data": [
                    {"symbol": "BTCX", "marketCap": "999999999"},
                    {"symbol": "BTC", "marketCap": "123456789"},
                ],
            }

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, *args, **kwargs):
            return MockResponse()

    monkeypatch.setattr("httpx.Client", MockClient)
    assert fetch_market_cap("BTCUSDT", BinanceAgentOSConfig()) == 123456789
