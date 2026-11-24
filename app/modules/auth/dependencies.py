from __future__ import annotations

from fastapi import Header, Request

from app.core.errors import NuvlyError
from app.modules.auth.browser_session import browser_scope, cookie_token
from app.modules.auth.service import AuthService

service = AuthService()


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise NuvlyError("Authorization header invalido.", 401, "INVALID_AUTHORIZATION_HEADER")
    return token.strip()


def _request_token(authorization: str | None, request: Request | None) -> str | None:
    token = extract_bearer_token(authorization)
    if token or request is None:
        return token
    if request.headers.get("x-nuvly-session-mode") != "cookie":
        return None
    return cookie_token(request)


def get_current_user(authorization: str | None = Header(default=None), request: Request = None) -> dict:
    token = _request_token(authorization, request)
    if not token:
        raise NuvlyError("Autenticacion requerida.", 401, "AUTH_REQUIRED")
    return service.get_user_from_token(
        token, required_account_type=browser_scope(request) if request is not None and not authorization else None
    )


def get_current_internal_user(authorization: str | None = Header(default=None), request: Request = None) -> dict:
    if (
        request is not None
        and not authorization
        and request.headers.get("x-nuvly-session-mode") == "cookie"
        and browser_scope(request) != "internal"
    ):
        raise NuvlyError("No tienes permisos para acceder a este recurso.", 403, "AUTH_SCOPE_FORBIDDEN")
    token = _request_token(authorization, request)
    if not token:
        raise NuvlyError("Autenticacion requerida.", 401, "AUTH_REQUIRED")
    return service.get_user_from_token(token, required_account_type="internal")


def get_current_admin_user(authorization: str | None = Header(default=None), request: Request = None) -> dict:
    current_user = (
        get_current_internal_user(authorization, request)
        if request is not None
        else get_current_internal_user(authorization)
    )
    if current_user.get("internalRole") != "admin":
        raise NuvlyError("No tienes permisos para realizar esta accion.", 403, "ADMIN_ROLE_REQUIRED")
    return current_user


def get_current_user_optional(authorization: str | None = Header(default=None), request: Request = None) -> dict | None:
    token = _request_token(authorization, request)
    if not token:
        return None
    return service.get_user_from_token(
        token, required_account_type=browser_scope(request) if request is not None and not authorization else None
    )
