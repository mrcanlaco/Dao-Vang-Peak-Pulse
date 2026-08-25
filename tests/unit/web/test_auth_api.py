"""Unit tests for access password authentication and endpoint protection."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from dao_vang.web.api_server import APIHandler


def test_check_auth_methods():
    handler = MagicMock(spec=APIHandler)
    handler.headers = {}
    handler.path = "/api/status"

    # When access password is set to Hailong200%
    with patch("dao_vang.web.api_server._settings.web.access_password", "Hailong200%"):
        # 1. No auth headers -> False
        assert APIHandler._check_auth(handler) is False

        # 2. Correct X-Access-Password header -> True
        handler.headers = {"X-Access-Password": "Hailong200%"}
        assert APIHandler._check_auth(handler) is True

        # 3. Incorrect X-Access-Password header -> False
        handler.headers = {"X-Access-Password": "wrongpassword"}
        assert APIHandler._check_auth(handler) is False

        # 4. Bearer Authorization header -> True
        handler.headers = {"Authorization": "Bearer Hailong200%"}
        assert APIHandler._check_auth(handler) is True

        # 5. Raw Authorization header -> True
        handler.headers = {"Authorization": "Hailong200%"}
        assert APIHandler._check_auth(handler) is True

        # 6. Cookie auth -> True
        handler.headers = {"Cookie": "session=abc; dao_vang_password=Hailong200%; foo=bar"}
        assert APIHandler._check_auth(handler) is True

        # 7. Query param token -> True
        handler.headers = {}
        handler.path = "/api/signals?token=Hailong200%"
        assert APIHandler._check_auth(handler) is True


def test_verify_auth_password_success():
    handler = MagicMock(spec=APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()

    with patch("dao_vang.web.api_server._settings.web.access_password", "Hailong200%"):
        APIHandler.verify_auth_password(handler, {"password": "Hailong200%"})

        handler._set_headers.assert_called_once()
        args, kwargs = handler._set_headers.call_args
        assert args[0] == 200
        assert "Set-Cookie" in kwargs.get("extra_headers", {})

        written = handler.wfile.write.call_args[0][0].decode("utf-8")
        data = json.loads(written)
        assert data.get("ok") is True
        assert data.get("authenticated") is True


def test_verify_auth_password_failure():
    handler = MagicMock(spec=APIHandler)
    handler.wfile = MagicMock()
    handler._set_headers = MagicMock()

    with patch("dao_vang.web.api_server._settings.web.access_password", "Hailong200%"):
        APIHandler.verify_auth_password(handler, {"password": "wrong"})

        handler._set_headers.assert_called_once()
        args, _ = handler._set_headers.call_args
        assert args[0] == 401

        written = handler.wfile.write.call_args[0][0].decode("utf-8")
        data = json.loads(written)
        assert data.get("ok") is False
        assert data.get("authenticated") is False
