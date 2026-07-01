from __future__ import annotations

from html import escape
import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings
from app.core.errors import NuvlyError

logger = logging.getLogger(__name__)


class AuthEmailService:
    @staticmethod
    def _build_password_reset_message(
        *,
        to_email: str,
        reset_url: str,
        from_email: str,
        from_name: str | None = None,
    ) -> EmailMessage:
        safe_reset_url = escape(reset_url, quote=True)
        subject = "Restablece tu clave de Nuvly"
        text_body = (
            "Hola,\n\n"
            "Recibimos una solicitud para restablecer tu clave de Nuvly.\n\n"
            f"Usa este enlace para crear una nueva clave:\n{reset_url}\n\n"
            "Si no solicitaste este cambio, puedes ignorar este correo.\n\n"
            "Equipo Nuvly"
        )
        html_body = f"""\
<!DOCTYPE html>
<html lang="es">
  <body style="margin:0;padding:0;background:#f4f8ff;font-family:Arial,'Helvetica Neue',Helvetica,sans-serif;color:#0f172a;">
    <div style="padding:32px 16px;background:
      radial-gradient(circle at 12% 18%, rgba(79,140,255,0.18), transparent 24%),
      radial-gradient(circle at 82% 12%, rgba(46,167,255,0.14), transparent 24%),
      radial-gradient(circle at 76% 82%, rgba(176,108,255,0.18), transparent 22%),
      linear-gradient(180deg, #f4f8ff 0%, #eef4ff 42%, #f8fbff 100%);
    ">
      <div style="max-width:620px;margin:0 auto;border-radius:32px;overflow:hidden;background:rgba(255,255,255,0.94);border:1px solid rgba(79,140,255,0.14);box-shadow:0 22px 60px rgba(15,23,42,0.12);">

        <div style="padding:28px 32px 20px;background:
          radial-gradient(circle at top left, rgba(255,255,255,0.22), transparent 30%),
          linear-gradient(135deg, #2EA7FF 0%, #7B61FF 52%, #B06CFF 100%);
          color:#ffffff;
        ">
          <div style="display:inline-block;padding:8px 14px;border-radius:999px;background:rgba(255,255,255,0.16);border:1px solid rgba(255,255,255,0.22);font-size:12px;letter-spacing:0.18em;text-transform:uppercase;font-weight:700;">
            Nuvly
          </div>

          <h1 style="margin:18px 0 10px;font-size:32px;line-height:1.12;font-weight:800;letter-spacing:-0.03em;">
            Restablece tu contraseña
          </h1>

          <p style="margin:0;max-width:470px;font-size:15px;line-height:1.65;color:rgba(255,255,255,0.92);">
            Recupera el acceso a tu cuenta y vuelve a editar tus invitaciones y páginas en Nuvly.
          </p>
        </div>

        <div style="padding:32px;">
          <p style="margin:0 0 16px;font-size:16px;line-height:1.7;color:#0f172a;">
            Hola,
          </p>

          <p style="margin:0 0 16px;font-size:16px;line-height:1.7;color:#334155;">
            Recibimos una solicitud para restablecer la contraseña de tu cuenta en
            <strong style="color:#0f172a;">Nuvly</strong>.
          </p>

          <p style="margin:0 0 26px;font-size:16px;line-height:1.7;color:#334155;">
            Haz clic en el botón para crear una nueva contraseña segura.
          </p>

          <div style="margin:0 0 28px;">
            <a
              href="{safe_reset_url}"
              style="display:inline-block;padding:15px 26px;border-radius:999px;background:linear-gradient(135deg, #2EA7FF 0%, #7B61FF 52%, #B06CFF 100%);color:#ffffff;text-decoration:none;font-size:15px;font-weight:800;box-shadow:0 24px 70px rgba(123,97,255,0.24);"
            >
              Crear nueva clave
            </a>
          </div>

          <div style="margin:0 0 24px;padding:18px 20px;border-radius:18px;background:#f8fbff;border:1px solid rgba(148,163,184,0.22);">
            <p style="margin:0;font-size:13px;line-height:1.7;color:#64748b;">
              Por seguridad, este enlace es personal y temporal. Si no solicitaste este cambio, puedes ignorar este correo.
            </p>
          </div>

          <p style="margin:0 0 10px;font-size:13px;line-height:1.7;color:#64748b;">
            Si el botón no funciona, copia y pega este enlace en tu navegador:
          </p>

          <p style="margin:0;font-size:13px;line-height:1.7;word-break:break-word;">
            <a href="{safe_reset_url}" style="color:#4F8CFF;text-decoration:underline;">
              {safe_reset_url}
            </a>
          </p>
        </div>

        <div style="padding:20px 32px;background:#f8fbff;border-top:1px solid rgba(148,163,184,0.16);">
          <p style="margin:0;font-size:12px;line-height:1.7;color:#64748b;">
            Este es un correo automático de Nuvly. Si necesitas ayuda, responde este mensaje o contáctanos desde tu cuenta.
          </p>
        </div>
      </div>
    </div>
  </body>
</html>
"""
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = f"{from_name} <{from_email}>" if from_name else from_email
        message["To"] = to_email
        message.set_content(text_body)
        message.add_alternative(html_body, subtype="html")
        return message

    def send_password_reset_email(self, email: str, reset_url: str) -> None:
        settings = get_settings()

        if not settings.smtp_host or not settings.smtp_from_email:
            logger.warning(
                "SMTP not configured; password reset email was not sent externally | to=%s resetUrl=%s",
                email,
                reset_url,
            )
            raise NuvlyError(
                "El servicio de recuperacion por correo no está disponible en este momento.",
                503,
                "AUTH_EMAIL_UNAVAILABLE",
            )

        message = self._build_password_reset_message(
            to_email=email,
            reset_url=reset_url,
            from_email=settings.smtp_from_email,
            from_name=settings.smtp_from_name,
        )

        try:
            logger.info(
                "Password reset SMTP send starting | to=%s host=%s port=%s tls=%s username=%s",
                email,
                settings.smtp_host,
                settings.smtp_port,
                settings.smtp_use_tls,
                settings.smtp_username,
            )
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
                if settings.smtp_use_tls:
                    smtp.starttls()
                    logger.info("Password reset SMTP TLS started | to=%s host=%s", email, settings.smtp_host)
                if settings.smtp_username and settings.smtp_password:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                    logger.info("Password reset SMTP login ok | to=%s username=%s", email, settings.smtp_username)
                smtp.send_message(message)
                logger.info("Password reset SMTP send accepted | to=%s host=%s", email, settings.smtp_host)
        except smtplib.SMTPException as exc:
            logger.exception("Password reset email send failed | to=%s", email)
            raise NuvlyError(
                "No pudimos enviar el correo de recuperacion. Revisa la configuracion SMTP e intentalo nuevamente.",
                502,
                "AUTH_EMAIL_SEND_FAILED",
            ) from exc
