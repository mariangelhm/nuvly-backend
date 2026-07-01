from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

PASSWORD_POLICY_PATTERN = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[-/#$%!.,])[A-Za-z\d\-/#$%!.,]{8,}$")


def validate_nuvly_password(value: str) -> str:
    if not PASSWORD_POLICY_PATTERN.fullmatch(value):
        raise ValueError(
            "La clave debe tener minimo 8 caracteres, una mayuscula, una minuscula, un numero y un simbolo permitido (-/#$%!.,)."
        )
    return value


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    confirmEmail: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    confirmPassword: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)

    @field_validator("email", "confirmEmail")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Debe ser un email valido.")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part or domain_part.startswith(".") or domain_part.endswith("."):
            raise ValueError("Debe ser un email valido.")
        return normalized

    @model_validator(mode="after")
    def validate_confirmations(self) -> "RegisterRequest":
        if self.email != self.confirmEmail:
            raise ValueError("email y confirmEmail deben coincidir.")
        if self.password != self.confirmPassword:
            raise ValueError("password y confirmPassword deben coincidir.")
        return self

    @field_validator("password", "confirmPassword")
    @classmethod
    def validate_password_policy(cls, value: str) -> str:
        return validate_nuvly_password(value)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Debe ser un email valido.")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part or domain_part.startswith(".") or domain_part.endswith("."):
            raise ValueError("Debe ser un email valido.")
        return normalized


class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Debe ser un email valido.")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part or domain_part.startswith(".") or domain_part.endswith("."):
            raise ValueError("Debe ser un email valido.")
        return normalized


class ForgotPasswordResponse(BaseModel):
    ok: bool = True
    message: str = "Si el email existe, enviaremos un enlace para recuperar la clave."


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=20, max_length=512)
    password: str = Field(min_length=8, max_length=128)
    confirmPassword: str = Field(min_length=8, max_length=128)

    @field_validator("password", "confirmPassword")
    @classmethod
    def validate_password_policy(cls, value: str) -> str:
        return validate_nuvly_password(value)

    @model_validator(mode="after")
    def validate_confirmations(self) -> "ResetPasswordRequest":
        if self.password != self.confirmPassword:
            raise ValueError("password y confirmPassword deben coincidir.")
        return self


class AuthUserResponse(BaseModel):
    id: str
    name: str
    email: str
    accountType: Literal["customer", "internal"] = "customer"
    internalRole: Literal["admin", "developer"] | None = None
    emailVerified: bool = False
    active: bool = True
    authProviders: list[str] = Field(default_factory=list)
    createdAt: str
    updatedAt: str
    lastLoginAt: str | None = None
    model_config = ConfigDict(from_attributes=True)


class AuthSessionResponse(BaseModel):
    token: str
    tokenType: str = "bearer"
    expiresAt: str
    authProvider: str = "nuvly"
    authScope: Literal["customer", "internal"] = "customer"
    user: AuthUserResponse


class LogoutResponse(BaseModel):
    ok: bool = True


class InternalUserCreateRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=120)
    internalRole: Literal["admin", "developer"]

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, value: str) -> str:
        normalized = value.strip().lower()
        if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
            raise ValueError("Debe ser un email valido.")
        local_part, domain_part = normalized.split("@", 1)
        if not local_part or "." not in domain_part or domain_part.startswith(".") or domain_part.endswith("."):
            raise ValueError("Debe ser un email valido.")
        return normalized

    @field_validator("password")
    @classmethod
    def validate_password_policy(cls, value: str) -> str:
        return validate_nuvly_password(value)
