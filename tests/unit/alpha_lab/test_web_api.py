"""Unit tests for Alpha Lab Web API endpoints."""

import json
from unittest.mock import MagicMock, patch

import pytest

from dao_vang.web.api_server import APIHandler


@pytest.fixture
def mock_handler() -> APIHandler:
    """Create a mock APIHandler instance."""
    handler = MagicMock(spec=APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()
    return handler


def test_api_server_routes_registered() -> None:
    """Verify that alpha-lab routes exist in APIHandler."""
    assert hasattr(APIHandler, "get_alpha_lab_regime")
    assert hasattr(APIHandler, "get_alpha_lab_drift")
    assert hasattr(APIHandler, "get_alpha_lab_summary")


@patch("dao_vang.data.collectors.binance_client.BinanceClient.get")
def test_get_alpha_lab_regime_endpoint(mock_binance_get: MagicMock) -> None:
    # Mock Binance klines response
    mock_binance_get.return_value = [
        [
            1700000000000 + i * 3600000,
            100.0 + i,
            101.0 + i,
            99.0 + i,
            100.5 + i,
            1000.0,
            1700000000000 + (i + 1) * 3600000,
            100000.0,
            500,
            500.0,
            50000.0,
            "0",
        ]
        for i in range(50)
    ]

    handler = MagicMock(spec=APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()

    # Call actual unbound method
    APIHandler.get_alpha_lab_regime(handler)

    handler._set_headers.assert_called_with(200)
    written_data = handler.wfile.write.call_args[0][0].decode("utf-8")
    payload = json.loads(written_data)

    assert "regime" in payload
    assert "adx" in payload
    assert "bb_width" in payload
    assert "allow_short" in payload


def test_get_alpha_lab_drift_endpoint() -> None:
    handler = MagicMock(spec=APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()

    APIHandler.get_alpha_lab_drift(handler)

    handler._set_headers.assert_called_with(200)
    written_data = handler.wfile.write.call_args[0][0].decode("utf-8")
    payload = json.loads(written_data)

    assert "status" in payload
    assert "max_psi" in payload
    assert "feature_psi" in payload


@patch("dao_vang.data.collectors.binance_client.BinanceClient.get")
def test_get_alpha_lab_summary_endpoint(mock_binance_get: MagicMock) -> None:
    mock_binance_get.return_value = [
        [
            1700000000000 + i * 3600000,
            100.0,
            101.0,
            99.0,
            100.0,
            1000.0,
            1700000000000 + (i + 1) * 3600000,
            100000.0,
            500,
            500.0,
            50000.0,
            "0",
        ]
        for i in range(30)
    ]

    handler = MagicMock(spec=APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()

    APIHandler.get_alpha_lab_summary(handler)

    handler._set_headers.assert_called_with(200)
    written_data = handler.wfile.write.call_args[0][0].decode("utf-8")
    payload = json.loads(written_data)

    assert "regime" in payload
    assert "meta_labeling" in payload
    assert "drift_guardian" in payload
