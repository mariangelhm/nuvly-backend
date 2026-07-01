from fastapi import APIRouter, Depends, Header

from app.modules.auth.dependencies import extract_bearer_token, get_current_user
from app.modules.auth.schemas import (
    AuthSessionResponse,
    AuthUserResponse,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutResponse,
    ResetPasswordRequest,
)
from app.modules.auth.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])
admin_router = APIRouter(prefix="/admin/auth", tags=["admin-auth"])
service = AuthService()


@router.post("/login", response_model=AuthSessionResponse)
def login(payload: LoginRequest):
    return service.login(payload)


@admin_router.post("/login", response_model=AuthSessionResponse)
def admin_login(payload: LoginRequest):
    return service.login_internal(payload)


@router.get("/me", response_model=AuthUserResponse)
def me(current_user: dict = Depends(get_current_user)):
    return current_user


@router.post("/logout", response_model=LogoutResponse)
def logout(authorization: str | None = Header(default=None)):
    token = extract_bearer_token(authorization)
    if not token:
        return {"ok": True}
    return service.logout(token)


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
def forgot_password(payload: ForgotPasswordRequest):
    return service.forgot_password(payload)


@router.post("/reset-password", response_model=LogoutResponse)
def reset_password(payload: ResetPasswordRequest):
    return service.reset_password(payload)
