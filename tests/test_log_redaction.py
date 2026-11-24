import asyncio
import logging
from types import SimpleNamespace

import pytest
from fastapi.exceptions import RequestValidationError
from test_error_handlers import _build_request

from app.core.errors import NuvlyError, handle_request_validation_error
from app.core.logging import SensitiveFormatter
from app.modules.auth import email_service


def test_auth_validation_logs_field_names_and_types_without_inputs(caplog):
    secret = "CANARY_PASSWORD_NOT_FOR_LOGS"
    error = RequestValidationError(
        [{"loc": ("body", "password"), "type": "value_error", "msg": secret, "input": secret}]
    )
    with caplog.at_level(logging.WARNING):
        response = asyncio.run(handle_request_validation_error(_build_request(), error))
    assert response.status_code == 422
    assert "password" in caplog.text
    assert secret not in caplog.text


def test_reset_url_is_never_logged_when_smtp_is_unavailable(monkeypatch, caplog):
    monkeypatch.setattr(email_service, "get_settings", lambda: SimpleNamespace(smtp_host=None, smtp_from_email=None))
    with caplog.at_level(logging.WARNING), pytest.raises(NuvlyError):
        email_service.AuthEmailService().send_password_reset_email(
            "user@example.test", "https://example.test/reset?token=PRIVATE_CANARY"
        )
    assert "PRIVATE_CANARY" not in caplog.text


def test_sensitive_formatter_redacts_nested_fields_and_exception_message():
    record = logging.LogRecord(
        "audit",
        logging.ERROR,
        "test",
        1,
        "payload=%s",
        ({"password": "PRIVATE_CANARY", "nested": {"access_token": "PRIVATE_CANARY"}},),
        None,
    )
    assert "PRIVATE_CANARY" not in SensitiveFormatter().format(record)
    record = logging.LogRecord("audit", logging.ERROR, "test", 1, "token=%s", ("PRIVATE_CANARY",), None)
    assert "PRIVATE_CANARY" not in SensitiveFormatter().format(record)
    record = logging.LogRecord(
        "audit",
        logging.ERROR,
        "test",
        1,
        "Authorization: Bearer PRIVATE_CANARY",
        (),
        (RuntimeError, RuntimeError("PRIVATE_CANARY"), None),
    )
    assert "PRIVATE_CANARY" not in SensitiveFormatter().format(record)
