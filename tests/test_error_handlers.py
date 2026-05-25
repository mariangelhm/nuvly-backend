from __future__ import annotations

import asyncio
import logging

from fastapi import FastAPI
from starlette.requests import Request

from app.core.errors import (
    NuvlyError,
    handle_nuvly_error,
    handle_unexpected_error,
    register_exception_handlers,
)


def _build_request() -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "https",
            "server": ("testserver", 443),
            "method": "GET",
            "root_path": "",
            "path": "/api/pricing/components",
            "headers": [],
        }
    )


def test_register_exception_handlers_adds_global_handlers() -> None:
    app = FastAPI()

    register_exception_handlers(app)

    assert NuvlyError in app.exception_handlers
    assert Exception in app.exception_handlers


def test_nuvly_error_is_logged(caplog) -> None:
    request = _build_request()

    with caplog.at_level(logging.WARNING):
        response = asyncio.run(handle_nuvly_error(request, NuvlyError("boom", 409, "TEST_ERROR")))

    assert response.status_code == 409
    assert "Handled NuvlyError" in caplog.text
    assert "GET /api/pricing/components" in caplog.text


def test_unexpected_error_is_logged(caplog) -> None:
    request = _build_request()

    with caplog.at_level(logging.ERROR):
        response = asyncio.run(handle_unexpected_error(request, RuntimeError("broken response")))

    assert response.status_code == 500
    assert "Unhandled exception" in caplog.text
    assert "broken response" in caplog.text

