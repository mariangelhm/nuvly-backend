from fastapi import APIRouter, Depends, Header, Request, Response

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.core.rate_limits import consume_rate_limit
from app.modules.auth.browser_session import (
    browser_scope,
    browser_session_response,
    clear_browser_session,
    cookie_token,
    require_browser_origin,
)
from app.modules.auth.dependencies import extract_bearer_token, get_current_user
from app.modules.auth.schemas import (
    AuthSessionResponse,
    AuthUserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    GoogleChallengeResponse,
    GoogleLoginRequest,
    LoginRequest,
    LogoutResponse,
    ResetPasswordRequest,
)
from app.modules.auth.service import AuthService


def validate_browser_mode(request: Request) -> None:
    if request.headers.get("x-nuvly-session-mode") == "cookie":
        require_browser_origin(request)
        browser_scope(request)


router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(validate_browser_mode)])
admin_router = APIRouter(prefix="/admin/auth", tags=["admin-auth"], dependencies=[Depends(validate_browser_mode)])
service = AuthService()


def require_google_origin(request: Request) -> None:
    origin = request.headers.get("origin", "").rstrip("/")
    if not origin or origin not in {value.rstrip("/") for value in get_settings().cors_origin_list}:
        raise NuvlyError("Origen de autenticación no permitido.", 403, "GOOGLE_AUTH_ORIGIN_NOT_ALLOWED")


@router.post("/google/challenge", response_model=GoogleChallengeResponse, dependencies=[Depends(require_google_origin)])
def google_challenge():
    return service.create_google_challenge()


@router.post("/google", response_model=AuthSessionResponse, dependencies=[Depends(require_google_origin)])
def google_login(payload: GoogleLoginRequest, request: Request, response: Response):
    return browser_session_response(request, response, service.login_google(payload))


@router.post("/login", response_model=AuthSessionResponse)
def login(payload: LoginRequest, request: Request, response: Response):
    consume_rate_limit("login-account", payload.email, 10, 60)
    return browser_session_response(request, response, service.login(payload))


@admin_router.post("/login", response_model=AuthSessionResponse)
def admin_login(payload: LoginRequest, request: Request, response: Response):
    consume_rate_limit("login-internal-account", payload.email, 10, 60)
    return browser_session_response(request, response, service.login_internal(payload))


@router.get("/me", response_model=AuthUserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post("/logout", response_model=LogoutResponse)
def logout(request: Request, response: Response, authorization: str | None = Header(default=None)):
    token = extract_bearer_token(authorization)
    if token is None and request.headers.get("x-nuvly-session-mode") == "cookie":
        token = cookie_token(request)
        clear_browser_session(request, response)
    if not token:
        return {"ok": True}
    return service.logout(token)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest):
    consume_rate_limit("reset-account", payload.email, 3, 900)
    return service.forgot_password(payload)


@router.post("/reset-password", response_model=LogoutResponse)
def reset_password(payload: ResetPasswordRequest):
    consume_rate_limit("reset-token", payload.token, 5, 900)
    return service.reset_password(payload)
