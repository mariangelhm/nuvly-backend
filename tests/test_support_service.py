from __future__ import annotations

import pytest

import app.main as main_module
from app.core.errors import NuvlyError
from app.modules.support.schemas import SupportContactRequest
from app.modules.support.service import SupportService


class StubSupportEmailService:
    def __init__(self) -> None:
        self.sent_messages: list[dict[str, str]] = []

    def send_support_contact_email(self, name: str, email: str, subject: str, message: str) -> None:
        self.sent_messages.append(
            {
                "name": name,
                "email": email,
                "subject": subject,
                "message": message,
            }
        )


class FailingSupportEmailService:
    def send_support_contact_email(self, name: str, email: str, subject: str, message: str) -> None:
        raise NuvlyError(
            "El servicio de soporte por correo no está disponible en este momento.",
            503,
            "SUPPORT_EMAIL_UNAVAILABLE",
        )


def test_support_contact_sends_email() -> None:
    email_service = StubSupportEmailService()
    service = SupportService(email_service=email_service)

    response = service.contact(
        SupportContactRequest(
            name="Lara",
            email="lara@test.dev",
            subject="Necesito ayuda",
            message="Hola, necesito ayuda con mi acceso al estudio.",
        )
    )

    assert response == {"ok": True, "message": "Tu mensaje fue enviado correctamente."}
    assert email_service.sent_messages == [
        {
            "name": "Lara",
            "email": "lara@test.dev",
            "subject": "Necesito ayuda",
            "message": "Hola, necesito ayuda con mi acceso al estudio.",
        }
    ]


def test_support_contact_propagates_email_service_error() -> None:
    service = SupportService(email_service=FailingSupportEmailService())

    with pytest.raises(NuvlyError) as exc:
        service.contact(
            SupportContactRequest(
                name="Lara",
                email="lara@test.dev",
                subject="Necesito ayuda",
                message="Hola, necesito ayuda con mi acceso al estudio.",
            )
        )

    assert exc.value.status_code == 503
    assert exc.value.code == "SUPPORT_EMAIL_UNAVAILABLE"


def test_support_contact_validates_email_format() -> None:
    with pytest.raises(ValueError):
        SupportContactRequest(
            name="Lara",
            email="correo-invalido",
            subject="Necesito ayuda",
            message="Hola, necesito ayuda con mi acceso al estudio.",
        )


def test_support_route_is_registered_in_openapi() -> None:
    paths = main_module.app.openapi()["paths"]

    assert "/api/support/contact" in paths
    assert "post" in paths["/api/support/contact"]
