import json
import urllib.error
from io import BytesIO
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.domain.errors import RateLimitError, SourceAPIError


def create_mock_response(
    status: int, body: dict[str, Any], headers: dict[str, str] | None = None
) -> MagicMock:
    mock_resp = MagicMock()
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.getcode.return_value = status
    mock_resp.read.return_value = json.dumps(body).encode("utf-8")

    mock_headers = MagicMock()

    def _get_header(k: str, d: Any = None) -> Any:
        return (headers or {}).get(k, d)

    mock_headers.get.side_effect = _get_header
    mock_resp.info.return_value = mock_headers
    return mock_resp


def test_binance_client_success() -> None:
    client = BinanceClient(max_retries=0)
    mock_resp = create_mock_response(
        200, {"key": "value"}, {"X-MBX-USED-WEIGHT-1M": "10"}
    )

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        result = client.get("/test", {"param": 1, "empty": None})

        assert result == {"key": "value"}
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        assert "param=1" in req.full_url
        assert "empty" not in req.full_url


def test_binance_client_4xx_error() -> None:
    client = BinanceClient(max_retries=1)

    error = urllib.error.HTTPError(
        url="http://test",
        code=400,
        msg="Bad Request",
        hdrs=MagicMock(get=lambda k: None),  # type: ignore
        fp=BytesIO(b'{"msg": "Invalid symbol"}'),
    )
    error.headers = MagicMock(get=lambda k: None)  # type: ignore

    with patch("urllib.request.urlopen", side_effect=error):
        with pytest.raises(SourceAPIError, match="Client error 400"):
            client.get("/test")


@patch("time.sleep")
def test_binance_client_rate_limit(mock_sleep: MagicMock) -> None:
    client = BinanceClient(max_retries=2, respect_retry_after=True)

    error = urllib.error.HTTPError(
        url="http://test",
        code=429,
        msg="Too Many Requests",
        hdrs=MagicMock(get=lambda k: "2" if k == "Retry-After" else None),  # type: ignore
        fp=BytesIO(b""),
    )
    error.headers = MagicMock(get=lambda k: "2" if k == "Retry-After" else None)  # type: ignore

    success_resp = create_mock_response(200, {"success": True})

    with patch("urllib.request.urlopen", side_effect=[error, error, success_resp]):
        result = client.get("/test")

        assert result == {"success": True}
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(2)


@patch("time.sleep")
def test_binance_client_rate_limit_exceeded(mock_sleep: MagicMock) -> None:
    client = BinanceClient(max_retries=1)

    error = urllib.error.HTTPError(
        url="http://test",
        code=429,
        msg="Too Many Requests",
        hdrs=MagicMock(get=lambda k: None),  # type: ignore
        fp=BytesIO(b""),
    )
    error.headers = MagicMock(get=lambda k: None)  # type: ignore

    with patch("urllib.request.urlopen", side_effect=[error, error]):
        with pytest.raises(RateLimitError):
            client.get("/test")


@patch("time.sleep")
def test_binance_client_network_error(mock_sleep: MagicMock) -> None:
    client = BinanceClient(max_retries=1)

    error = urllib.error.URLError("Connection refused")

    success_resp = create_mock_response(200, {"success": True})

    with patch("urllib.request.urlopen", side_effect=[error, success_resp]):
        result = client.get("/test")

        assert result == {"success": True}
        assert mock_sleep.call_count == 1
