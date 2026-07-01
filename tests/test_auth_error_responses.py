from __future__ import annotations

import asyncio
import json

from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.core.errors import handle_request_validation_error


def _build_request(path: str) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": "https",
            "server": ("testserver", 443),
            "method": "POST",
            "root_path": "",
            "path": path,
            "headers": [],
        }
    )


def test_register_returns_auth_specific_validation_error_payload() -> None:
    request = _build_request("/api/auth/register")
    exc = RequestValidationError(
        [
            {"loc": ("body", "email"), "msg": "Debe ser un email valido.", "type": "value_error"},
            {"loc": ("body", "name"), "msg": "String should have at least 1 character", "type": "string_too_short"},
        ]
    )

    response = asyncio.run(handle_request_validation_error(request, exc))

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "error": {
            "code": "AUTH_REGISTER_VALIDATION_ERROR",
            "message": "Datos inválidos para registro.",
            "details": [
                {"field": "email", "message": "Debe ser un email valido.", "type": "value_error"},
                {"field": "name", "message": "String should have at least 1 character", "type": "string_too_short"},
            ],
        }
    }


def test_login_returns_auth_specific_validation_error_payload() -> None:
    request = _build_request("/api/auth/login")
    exc = RequestValidationError(
        [
            {"loc": ("body", "email"), "msg": "Debe ser un email valido.", "type": "value_error"},
            {"loc": ("body", "password"), "msg": "String should have at least 8 characters", "type": "string_too_short"},
        ]
    )

    response = asyncio.run(handle_request_validation_error(request, exc))

    assert response.status_code == 422
    assert json.loads(response.body) == {
        "error": {
            "code": "AUTH_LOGIN_VALIDATION_ERROR",
            "message": "Datos inválidos para inicio de sesión.",
            "details": [
                {"field": "email", "message": "Debe ser un email valido.", "type": "value_error"},
                {"field": "password", "message": "String should have at least 8 characters", "type": "string_too_short"},
            ],
        }
    }
