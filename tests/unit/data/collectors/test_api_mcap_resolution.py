from unittest.mock import patch

from dao_vang.web.api_server import _resolve_market_cap_info


@patch(
    "dao_vang.data.collectors.binance_agent_os.fetch_market_cap",
    return_value=173_046_000.0,
)
def test_resolve_market_cap_info_uses_binance_agent_os(mock_fetch_market_cap):
    # Clear cache to force a remote fetch
    from dao_vang.web.api_server import _MARKET_CAP_CACHE, _MARKET_CAP_CACHE_LOCK
    with _MARKET_CAP_CACHE_LOCK:
        _MARKET_CAP_CACHE.clear()

    result = _resolve_market_cap_info("UAIUSDT", fetch_remote=True)

    assert result is not None
    assert result["market_cap_source"] == "binance_agent_os"
    assert result["market_cap_usd"] == 173046000.0
    assert result["market_cap_str"] == "$173M"
    mock_fetch_market_cap.assert_called_once()
