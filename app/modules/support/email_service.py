from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.errors import NuvlyError

logger = logging.getLogger(__name__)


class SupportEmailService:
    def send_support_contact_email(self, name: str, email: str, subject: str, message: str) -> None:
        settings = get_settings()
        if not settings.smtp_host or not settings.smtp_from_email:
            logger.warning(
                "SMTP not configured; support email could not be sent | fromUser=%s supportTo=%s",
                email,
                settings.support_contact_email,
            )
            raise NuvlyError(
                "El servicio de soporte por correo no está disponible en este momento.",
                503,
                "SUPPORT_EMAIL_UNAVAILABLE",
            )

        outbound = EmailMessage()
        outbound["Subject"] = f"[Nuvly soporte] {subject}"
        outbound["From"] = (
            f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
            if settings.smtp_from_name
            else settings.smtp_from_email
        )
        outbound["To"] = settings.support_contact_email
        outbound["Reply-To"] = email
        outbound.set_content(
            "\n".join(
                [
                    "Nuevo mensaje de soporte desde Nuvly.",
                    "",
                    f"Nombre: {name}",
                    f"Email: {email}",
                    f"Asunto: {subject}",
                    "",
                    "Mensaje:",
                    message,
                ]
            )
        )

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(outbound)
        except smtplib.SMTPException as exc:
            logger.exception("Support email send failed | fromUser=%s supportTo=%s", email, settings.support_contact_email)
            raise NuvlyError(
                "No pudimos enviar tu mensaje de soporte. Inténtalo nuevamente.",
                502,
                "SUPPORT_EMAIL_SEND_FAILED",
            ) from exc
