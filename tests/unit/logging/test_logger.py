import logging

import structlog

from dao_vang.logging.logger import (
    bind_context,
    clear_context,
    configure_logging,
    get_logger,
    redact_secrets,
)


def test_redact_secrets() -> None:
    event_dict = {"safe_key": "value", "api_key": "secret_123", "my_PASSWORD": "abc"}
    logger = logging.getLogger("dummy")
    redacted = redact_secrets(logger, "test", event_dict)

    assert redacted["safe_key"] == "value"
    assert redacted["api_key"] == "***REDACTED***"
    assert redacted["my_PASSWORD"] == "***REDACTED***"


def test_configure_logging_json() -> None:
    configure_logging(json_format=True)
    logger = get_logger("test_json")
    assert hasattr(logger, "bind")


def test_bind_context() -> None:
    clear_context()
    bind_context(run_id="test_123")
    context = structlog.contextvars.get_contextvars()
    assert context.get("run_id") == "test_123"
    clear_context()
    assert not structlog.contextvars.get_contextvars()
