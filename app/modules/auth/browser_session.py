"""Opaque browser sessions. Custom headers and exact origins protect cookie auth."""

from datetime import datetime, timezone

from fastapi import Request, Response

from app.core.config import get_settings
from app.core.errors import NuvlyError


def require_browser_origin(request: Request) -> None:
    origin = request.headers.get("origin", "")
    if not origin or origin == "null" or origin not in get_settings().cors_origin_list:
        raise NuvlyError("Origen de autenticación no permitido.", 403, "AUTH_ORIGIN_FORBIDDEN")


def cookie_name(scope: str) -> str:
    return f"nuvly_{scope}_session"


def browser_scope(request: Request) -> str:
    scope = request.headers.get("x-nuvly-auth-scope", "")
    if scope not in {"customer", "internal"}:
        raise NuvlyError("Scope de autenticación requerido.", 403, "AUTH_SCOPE_REQUIRED")
    return scope


def cookie_token(request: Request) -> str | None:
    # Cookies alone never authorize a request. The custom header forces a CORS
    # preflight cross-origin; writes additionally require an exact trusted Origin.
    scope = browser_scope(request)
    origin = request.headers.get("origin")
    if request.method not in {"GET", "HEAD", "OPTIONS"} or origin is not None:
        require_browser_origin(request)
    return request.cookies.get(cookie_name(scope))


def _cookie_options() -> dict:
    settings = get_settings()
    secure = settings.app_env not in {"development", "test"}
    return dict(httponly=True, secure=secure, samesite="none" if secure else "lax", path=settings.api_prefix or "/")


def browser_session_response(request: Request, response: Response, session: dict) -> dict:
    if request.headers.get("x-nuvly-session-mode") != "cookie":
        return session  # Explicit bearer API clients remain supported.
    require_browser_origin(request)
    scope = browser_scope(request)
    if scope != session["authScope"]:
        raise NuvlyError("Scope de autenticación inválido.", 403, "AUTH_SCOPE_FORBIDDEN")
    expires = datetime.fromisoformat(session["expiresAt"].replace("Z", "+00:00"))
    response.set_cookie(
        cookie_name(scope),
        session["token"],
        expires=expires,
        max_age=max(0, int((expires - datetime.now(timezone.utc)).total_seconds())),
        **_cookie_options(),
    )
    response.headers["Cache-Control"] = "no-store"
    return {**session, "token": "", "sessionKind": "cookie"}


def clear_browser_session(request: Request, response: Response) -> None:
    response.delete_cookie(cookie_name(browser_scope(request)), **_cookie_options())
    response.headers["Cache-Control"] = "no-store"
