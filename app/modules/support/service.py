from __future__ import annotations

from typing import Any

from app.modules.support.email_service import SupportEmailService
from app.modules.support.schemas import SupportContactRequest


class SupportService:
    def __init__(self, email_service: SupportEmailService | None = None) -> None:
        self.email_service = email_service or SupportEmailService()

    def contact(self, payload: SupportContactRequest) -> dict[str, Any]:
        self.email_service.send_support_contact_email(
            name=payload.name,
            email=payload.email,
            subject=payload.subject,
            message=payload.message,
        )
        return {"ok": True, "message": "Tu mensaje fue enviado correctamente."}
