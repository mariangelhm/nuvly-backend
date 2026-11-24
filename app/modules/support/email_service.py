from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.errors import NuvlyError

logger = logging.getLogger(__name__)


class SupportEmailService:
    def send_customer_reply(self, ticket, body):
        settings = get_settings()
        if not settings.smtp_host or not settings.smtp_from_email:
            raise NuvlyError("El envío de correo no está disponible.", 503, "SUPPORT_EMAIL_UNAVAILABLE")
        outbound = EmailMessage()
        outbound["Subject"] = f"[{ticket['reference']}] " + ticket["subject"].replace("\r", " ").replace("\n", " ")
        outbound["From"] = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
        outbound["To"] = ticket["email"]
        outbound["Reply-To"] = settings.support_contact_email
        outbound.set_content(
            f"Hola, {ticket['name']}.\n\n{body}\n\nReferencia: {ticket['reference']}\nEquipo Nuvly\nPuedes responder a este correo para contactarnos."
        )
        try:
            factory = smtplib.SMTP_SSL if settings.smtp_port == 465 else smtplib.SMTP
            with factory(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                if settings.smtp_use_tls and settings.smtp_port != 465:
                    smtp.starttls()
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                if smtp.send_message(outbound):
                    raise smtplib.SMTPException("Recipient not accepted")
        except (smtplib.SMTPException, OSError) as exc:
            raise NuvlyError(
                "No pudimos enviar la respuesta. El caso conserva el mensaje para que puedas reintentarlo.",
                502,
                "SUPPORT_REPLY_FAILED",
            ) from exc

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
            logger.exception(
                "Support email send failed | fromUser=%s supportTo=%s", email, settings.support_contact_email
            )
            raise NuvlyError(
                "No pudimos enviar tu mensaje de soporte. Inténtalo nuevamente.",
                502,
                "SUPPORT_EMAIL_SEND_FAILED",
            ) from exc
