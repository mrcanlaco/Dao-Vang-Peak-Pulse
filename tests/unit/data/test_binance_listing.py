import pytest
from dao_vang.data.binance_listing import fetch_listing_stats

def test_fetch_listing_stats(monkeypatch):
    def mock_get(url, timeout=20.0):
        return {"data": []}
    monkeypatch.setattr("dao_vang.data.binance_listing._http_get", mock_get)
    res = fetch_listing_stats()
    assert isinstance(res, dict)

# skipped: full integration mock, add when pipeline uses listing
