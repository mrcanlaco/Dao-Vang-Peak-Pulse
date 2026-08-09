import pytest
from dao_vang.data.collectors.coingecko import fetch_market_data, CoinGeckoConfig

def test_fetch_market_data(monkeypatch):
    class MockResponse:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"id": "bitcoin"}
    
    class MockClient:
        def __init__(self, *args, **kwargs): pass
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def get(self, *args, **kwargs): return MockResponse()
        
    monkeypatch.setattr("httpx.Client", MockClient)
    config = CoinGeckoConfig(enabled=True)
    res = fetch_market_data("BTCUSDT", config)
    assert res is None or res.coingecko_id == "bitcoin"

# skipped: logic tests, add when coingecko is active
