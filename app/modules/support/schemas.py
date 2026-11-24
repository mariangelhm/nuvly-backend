from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SupportCategory = Literal["question", "payment", "complaint", "domain", "technical", "other"]
SupportStatus = Literal["open", "in_progress", "waiting_customer", "resolved"]
SupportPriority = Literal["normal", "high", "urgent"]


def validate_email_format(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized or normalized.startswith("@") or normalized.endswith("@"):
        raise ValueError("Debe ser un email valido.")
    local_part, domain_part = normalized.split("@", 1)
    if not local_part or "." not in domain_part or domain_part.startswith(".") or domain_part.endswith("."):
        raise ValueError("Debe ser un email valido.")
    return normalized


class SupportContactRequest(BaseModel):
    category: SupportCategory = "question"
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=5, max_length=254)
    subject: str = Field(min_length=3, max_length=160)
    message: str = Field(min_length=10, max_length=4000)

    @field_validator("name", "subject", "message")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Este campo no puede estar vacio.")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return validate_email_format(value)


class SupportContactResponse(BaseModel):
    ticketId: str | None = None
    reference: str | None = None
    notificationSent: bool = False
    ok: bool = True
    message: str = "Tu mensaje fue enviado correctamente."


class SupportTicketUpdate(BaseModel):
    status: SupportStatus | None = None
    category: SupportCategory | None = None
    priority: SupportPriority | None = None
    assignToMe: bool = False


class SupportReplyRequest(BaseModel):
    body: str = Field(min_length=2, max_length=8000)
    internal: bool = False

    @field_validator("body")
    @classmethod
    def validate_body(cls, value):
        if len(value.strip()) < 2:
            raise ValueError("Escribe un mensaje antes de enviarlo.")
        return value.strip()
