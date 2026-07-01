from __future__ import annotations

from fastapi import Header

from app.core.errors import NuvlyError
from app.modules.auth.service import AuthService

service = AuthService()


def extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise NuvlyError("Authorization header invalido.", 401, "INVALID_AUTHORIZATION_HEADER")
    return token.strip()


def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    token = extract_bearer_token(authorization)
    if not token:
        raise NuvlyError("Autenticacion requerida.", 401, "AUTH_REQUIRED")
    return service.get_user_from_token(token)


def get_current_internal_user(authorization: str | None = Header(default=None)) -> dict:
    token = extract_bearer_token(authorization)
    if not token:
        raise NuvlyError("Autenticacion requerida.", 401, "AUTH_REQUIRED")
    return service.get_user_from_token(token, required_account_type="internal")


def get_current_admin_user(authorization: str | None = Header(default=None)) -> dict:
    current_user = get_current_internal_user(authorization)
    if current_user.get("internalRole") != "admin":
        raise NuvlyError("No tienes permisos para realizar esta accion.", 403, "ADMIN_ROLE_REQUIRED")
    return current_user


def get_current_user_optional(authorization: str | None = Header(default=None)) -> dict | None:
    token = extract_bearer_token(authorization)
    if not token:
        return None
    return service.get_user_from_token(token)
