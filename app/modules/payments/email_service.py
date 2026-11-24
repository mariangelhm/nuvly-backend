"""Confirmed-payment email delivery; never interprets browser input as approval."""

import logging
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import formataddr, formatdate
from html import escape
from urllib.parse import quote

from app.core.config import get_settings
from app.core.utils import new_id, utc_now_iso
from app.modules.payments.receipt_pdf import render_accepted_terms_pdf

logger = logging.getLogger(__name__)


def build_payment_email(payment, settings):
    if payment.get("status") != "paid":
        raise ValueError("Only verified approved payments receive a confirmation")
    acceptance = payment.get("termsAcceptance") or {}
    recipient = (payment.get("ownerEmail") or acceptance.get("customerEmail") or "").strip()
    if not recipient:
        raise ValueError("Payment has no authenticated customer email")
    test = payment.get("testMode") is True or payment.get("environment") == "integration"
    project = payment.get("projectTitle") or acceptance.get("projectTitle") or "Tu proyecto"
    amount = f"${float(payment['amount']):,.0f}".replace(",", ".") + " CLP"
    provider = {"transbank": "Webpay Plus - Transbank", "mercadopago": "Mercado Pago"}.get(
        payment.get("provider"), "Pago en línea"
    )
    base = (settings.frontend_public_base_url or payment.get("checkoutBaseUrl") or "").rstrip("/")
    product = "invitations" if payment.get("projectType") == "invitation" else "websites"
    editor_url = f"{base}/customer/{product}/{quote(payment['projectId'], safe='')}/edit"
    support = settings.support_contact_email
    reference = payment.get("paymentId") or payment["id"]
    approved_at = payment.get("paidAt") or payment.get("updatedAt") or utc_now_iso()
    public_url = payment.get("websiteUrl") or payment.get("invitationUrl") or ""
    billing = payment.get("billingTerms") or acceptance.get("billingTerms") or {}
    steps = [
        "Guarda este correo y el PDF adjunto con las condiciones que aceptaste."
        if acceptance.get("document")
        else "Guarda este correo como confirmación de la transacción."
    ]
    if test:
        steps.append(
            "Este pago es una simulación sin cobro real. El proyecto sigue el flujo de pago y publicación del ambiente de pruebas. Puedes revisar su estado y dirección en Mis productos."
        )
    elif payment.get("withCustomDomain"):
        steps.append(
            "Te contactaremos para asesorarte con la compra de tu dominio si aún no tienes uno. Nuestro equipo se encargará de configurarlo y conectarlo a tu web."
        )
        steps.append("Puedes seguir editando tu página mientras coordinamos la configuración del dominio.")
    elif public_url:
        steps.append(
            "Tu página ya está publicada. Abre la URL de este correo para verla y compartirla; también queda guardada en Mis productos."
        )
    else:
        steps.append(
            "Puedes volver al editor para continuar con tu proyecto. La dirección pública estará disponible en Mis productos cuando se complete la publicación."
        )
    if billing:
        renewal = f"${float(billing['renewalAmount']):,.0f}".replace(",", ".")
        steps.append(
            f"Tu plan cubre {billing['initialMonths']} meses desde la publicación. Desde el mes {billing['renewalStartsMonth']}, la continuidad cuesta {renewal} CLP al mes y requiere un nuevo pago. No se autorizaron cobros recurrentes automáticos."
        )
    facts = [
        ("Proyecto", project),
        ("Monto aprobado", amount),
        ("Medio de pago", provider),
        ("Referencia", reference),
        ("Fecha de aprobación (UTC)", approved_at),
    ]
    if public_url:
        facts.append(("URL de tu publicación de prueba" if test else "URL de tu página", public_url))
    if payment.get("withCustomDomain"):
        facts.append(("Dominio propio", payment.get("customDomain") or "Por definir con nuestro equipo"))
    heading = "Pago aprobado" if not test else "Confirmación de pago de prueba"
    notice = "PRUEBA: no se realizó un cobro real." if test else "Recibimos la confirmación de tu pago."
    message = EmailMessage()
    subject_project = str(project).replace("\r", " ").replace("\n", " ")
    message["Subject"] = f"{'[PRUEBA] ' if test else ''}Pago aprobado - {subject_project} | Nuvly"
    message["From"] = formataddr((settings.smtp_from_name or "Nuvly", settings.smtp_from_email))
    message["To"] = recipient
    message["Reply-To"] = support
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = f"<nuvly-payment-{reference}@{settings.smtp_from_email.rsplit('@', 1)[-1]}>"
    message.set_content(
        "\n".join(
            [
                "NUVLY",
                heading,
                notice,
                "",
                *[f"{label}: {value}" for label, value in facts],
                "",
                "Qué sigue",
                *[f"- {step}" for step in steps],
                "",
                f"Volver a mi página: {editor_url}",
                f"Ayuda: {support}",
                "",
                "Esta confirmación no reemplaza una boleta o factura.",
            ]
        )
    )
    rows = "".join(
        f'<tr><td style="padding:9px;color:#64748b">{escape(str(label))}</td><td style="padding:9px;color:#172d4b;font-weight:600;overflow-wrap:anywhere">{escape(str(value))}</td></tr>'
        for label, value in facts
    )
    if public_url:
        url = escape(public_url, quote=True)
        rows += f'<tr><td colspan="2" style="padding:14px"><a href="{url}" style="color:#315bb5;font-weight:600">Abrir mi página ↗</a></td></tr>'
    items = "".join(f'<li style="margin-bottom:10px">{escape(step)}</li>' for step in steps)
    message.add_alternative(
        f'''<!doctype html><html lang="es"><body style="margin:0;background:#f3f6ff;font-family:Arial,sans-serif;color:#172d4b"><div style="max-width:580px;margin:24px auto;padding:28px;background:white;border:1px solid #e5e2f7;border-radius:20px"><div style="font-size:28px;font-weight:800;color:#162848">nuvly</div><h1 style="font-size:24px">{heading}</h1><p>{notice}</p><table style="width:100%;border-collapse:collapse;background:#f5f7ff;font-size:14px">{rows}</table><h2 style="font-size:18px">Qué sigue</h2><ul style="padding-left:20px;font-size:14px;line-height:1.6">{items}</ul><p><a href="{escape(editor_url, quote=True)}" style="display:inline-block;padding:13px 22px;border-radius:24px;background:#735cff;color:white;text-decoration:none;font-weight:600">Volver a mi página</a></p><p style="font-size:13px">¿Necesitas ayuda? Escríbenos a <a href="mailto:{escape(support, quote=True)}">{escape(support)}</a>.</p><p style="font-size:11px;color:#64748b">Esta confirmación no reemplaza una boleta o factura.</p></div></body></html>''',
        subtype="html",
    )
    if acceptance.get("document"):
        message.add_attachment(
            render_accepted_terms_pdf(payment),
            maintype="application",
            subtype="pdf",
            filename=f"nuvly-condiciones-{reference}.pdf",
        )
    return message


def send_payment_email(payment):
    settings = get_settings()
    if not settings.smtp_host or not settings.smtp_from_email:
        return "unavailable"
    message = build_payment_email(payment, settings)
    factory = smtplib.SMTP_SSL if settings.smtp_port == 465 else smtplib.SMTP
    with factory(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
        if settings.smtp_use_tls and settings.smtp_port != 465:
            smtp.starttls(context=ssl.create_default_context())
        if settings.smtp_username and settings.smtp_password:
            smtp.login(settings.smtp_username, settings.smtp_password)
        refused = smtp.send_message(message)
        if refused:
            raise smtplib.SMTPRecipientsRefused(refused)
    return "sent"


class PaymentReceiptEmailService:
    def __init__(self, repository, sender=None):
        self.repository = repository
        self.sender = sender or send_payment_email

    def enqueue(self, payment):
        if payment.get("status") != "paid":
            return
        now = utc_now_iso()
        self.repository.enqueue_payment_email(
            {
                "id": payment["id"],
                "paymentId": payment["id"],
                "recipient": payment.get("ownerEmail") or (payment.get("termsAcceptance") or {}).get("customerEmail"),
                "status": "pending",
                "attempts": 0,
                "createdAt": now,
                "nextAttemptAt": now,
            }
        )

    def status(self, payment_id):
        record = self.repository.find_document("payment_receipt_emails", {"id": payment_id})
        return {key: record.get(key) for key in ("status", "recipient", "sentAt", "nextAttemptAt")} if record else None

    def deliver(self, payment):
        if payment.get("status") != "paid":
            return None
        now = datetime.now(timezone.utc)
        lease_id = new_id("email")
        record = self.repository.claim_payment_email(
            payment["id"], now.isoformat(), lease_id, (now + timedelta(minutes=2)).isoformat()
        )
        if not record:
            return self.status(payment["id"])
        try:
            state = self.sender(payment)
            if state not in ("sent", "unavailable"):
                raise ValueError("Email transport did not confirm sending")
        except Exception as exc:
            # Delivery failures must never turn an approved payment into a failure.
            logger.warning(
                "Payment receipt email failed | paymentId=%s errorType=%s", payment["id"], type(exc).__name__
            )
            state = "failed"
        finished = datetime.now(timezone.utc)
        self.repository.finish_payment_email(
            payment["id"],
            lease_id,
            {
                "status": state,
                "sentAt": finished.isoformat() if state == "sent" else None,
                "nextAttemptAt": (finished + timedelta(minutes=1)).isoformat(),
            },
        )
        return self.status(payment["id"])
