"""Integration checkout with the complete project lifecycle and explicit test labels."""

import logging
from hashlib import sha256
from hmac import compare_digest
from hmac import new as hmac_new
from time import time
from urllib.parse import quote

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.payments import gateways
from app.modules.payments.email_service import PaymentReceiptEmailService
from app.modules.payments.schemas import PaymentWebhookPayload
from app.modules.payments.service import PaymentService
from app.modules.payments.terms import validate_terms_acceptance

logger = logging.getLogger(__name__)


class IntegrationPaymentService(PaymentService):
    environment = "integration"
    test_mode = True

    def _assert_mode(self):
        gateways.assert_integration_mode()

    def _create_gateway(self, *args, **kwargs):
        return gateways.create_test_checkout(*args, **kwargs)

    def _verify_gateway(self, *args, **kwargs):
        return gateways.verify_test_payment(*args, **kwargs)

    def __init__(self, repository=None, receipt_sender=None):
        super().__init__(repository=repository)
        self.receipt_email = PaymentReceiptEmailService(self.repository, sender=receipt_sender)

    def _complete_test_project(self, payment):
        self._assert_mode()
        if payment.get("projectEffectsAppliedAt"):
            return payment
        service = self._project_service(payment["projectType"])
        project = self.repository.find_document(service.config.collection, {"id": payment["projectId"]})
        if not project:
            raise NuvlyError("No encontramos el proyecto de este pago.", 404, "PROJECT_NOT_FOUND")
        info = project.get("payment") or {}
        if info.get("status") == "paid" and bool(info.get("testMode")) != self.test_mode:
            raise NuvlyError(
                "Este proyecto ya tiene un pago real. Usa otro proyecto para la prueba.",
                409,
                "PROJECT_HAS_REAL_PAYMENT",
            )
        completed = (
            info.get("paymentId") == payment["id"]
            and info.get("status") == "paid"
            and (payment.get("withCustomDomain") or project.get("publishedSnapshotId"))
        )
        if not completed:
            project["payment"] = {
                **info,
                "environment": self.environment,
                "testMode": self.test_mode,
                "paymentId": payment["id"],
            }
            self.repository.replace_document(
                service.config.collection,
                project["id"],
                project,
                "Proyecto no encontrado.",
                "PROJECT_NOT_FOUND",
                "Proyecto duplicado.",
            )
            payment = super().process_webhook(
                payment["provider"],
                PaymentWebhookPayload(
                    paymentId=payment["id"], status="approved", providerPaymentId=payment.get("providerPaymentId")
                ),
            )
        payment["projectEffectsAppliedAt"] = utc_now_iso()
        return self._save(payment)

    def _send_receipt(self, payment, enqueue=False):
        try:
            if enqueue:
                self.receipt_email.enqueue(payment)
            return self.receipt_email.deliver(payment)
        except Exception as exc:
            logger.warning(
                "Payment receipt processing failed | paymentId=%s errorType=%s", payment["id"], type(exc).__name__
            )
            return None

    def _record_confirmation(self, payment, verified):
        newly_paid = payment.get("status") != "paid" and verified.get("status") == "paid"
        payment.update(verified)
        if newly_paid:
            payment["paidAt"] = utc_now_iso()
        payment = self._save(payment)
        if payment["status"] == "paid":
            payment = self._complete_test_project(payment)
            self._send_receipt(payment, enqueue=newly_paid)
        return payment

    def providers(self):
        settings = get_settings()
        enabled = settings.payments_environment == "integration" and settings.app_env.lower() not in (
            "production",
            "prod",
        )
        return {
            "environment": "integration",
            "testMode": True,
            "providers": [
                {
                    "id": "mercadopago",
                    "label": "Mercado Pago",
                    "enabled": enabled
                    and bool(
                        settings.mercadopago_test_access_token
                        and settings.mercadopago_test_access_token.get_secret_value().strip()
                    ),
                    "helper": "Checkout Pro de pruebas"
                    if settings.mercadopago_test_access_token
                    else "Pendiente: configurar una aplicación de pruebas de Mercado Pago",
                },
                {
                    "id": "transbank",
                    "label": "Webpay Plus · Transbank",
                    "enabled": enabled,
                    "helper": "Ambiente de integración con tarjetas de prueba",
                },
            ],
        }

    def assert_project_owner(self, project_type, project_id, user):
        return self._project_service(project_type).get_for_owner(
            project_id, owner_id=user.get("id"), owner_email=user.get("email")
        )

    def _payment(self, payment_id, provider=None):
        filters = {"id": payment_id}
        if provider:
            filters["provider"] = provider
        payment = self.repository.find_document("payments", filters)
        if not payment or payment.get("environment") != self.environment:
            raise NuvlyError("No encontramos ese pago de pruebas.", 404, "PAYMENT_NOT_FOUND")
        return payment

    def _save(self, payment):
        payment["updatedAt"] = utc_now_iso()
        return self.repository.replace_document(
            "payments", payment["id"], payment, "Pago no encontrado.", "PAYMENT_NOT_FOUND", "Pago duplicado."
        )

    def create_integration_checkout(self, payload, user, base_url=None):
        self._assert_mode()
        project = self.assert_project_owner(payload.projectType, payload.projectId, user)
        self._assert_project_can_checkout(project)
        validate_terms_acceptance(payload)
        pricing = self._build_checkout_pricing(payload)
        payment_id = new_id("pay")
        settings = get_settings()
        backend = self._resolve_backend_base_url(base_url)
        callback = f"{backend}{settings.api_prefix}/payments/return/{payload.provider}/{quote(payment_id)}"
        notification_url = (
            f"{backend}{settings.api_prefix}/payments/webhooks/mercadopago"
            if settings.mercadopago_test_webhook_secret and backend.startswith("https://")
            else None
        )
        gateway = self._create_gateway(
            payload.provider,
            {
                "id": payment_id,
                "projectId": payload.projectId,
                "title": pricing["project"].get("title"),
                "amount": pricing["amount"],
            },
            callback,
            notification_url,
        )
        payment = super().create_checkout(payload, base_url, payment_id=payment_id)
        frontend = (settings.frontend_public_base_url or "http://localhost:5173").rstrip("/")
        payment.update(gateway)
        if payment.get("termsAcceptance"):
            payment["termsAcceptance"].update(
                {"customerId": user.get("id"), "customerEmail": (user.get("email") or "").lower()}
            )
        payment.update(
            {
                "environment": self.environment,
                "testMode": self.test_mode,
                "ownerId": user.get("id"),
                "ownerEmail": (user.get("email") or "").lower(),
                "checkoutBaseUrl": frontend,
                "checkoutUrl": f"{frontend}/checkout/{payload.provider}/{quote(payment_id)}",
            }
        )
        return self._save(payment)

    def _summary(self, payment):
        status = payment["status"]
        try:
            receipt = self.receipt_email.status(payment["id"])
        except Exception:
            receipt = None
        return {
            **{
                key: payment.get(key)
                for key in (
                    "projectTitle",
                    "publicSlug",
                    "planTier",
                    "basePrice",
                    "extrasTotal",
                    "billingTerms",
                    "withCustomDomain",
                    "customDomain",
                    "customDomainSurcharge",
                    "termsAcceptance",
                    "paymentId",
                    "provider",
                    "projectType",
                    "projectId",
                    "amount",
                    "subtotalAmount",
                    "discountAmount",
                    "discountCode",
                    "currency",
                    "checkoutUrl",
                    "gatewayUrl",
                    "redirectMethod",
                    "redirectFields",
                )
            },
            "finalUrl": payment.get("websiteUrl") or payment.get("invitationUrl"),
            "receiptEmail": receipt,
            "ok": True if status == "paid" else False if status == "failed" else None,
            "status": status,
            "environment": "integration",
            "testMode": True,
            "message": "Pago de prueba aprobado. El proyecto completó el flujo de pago y publicación que corresponde a su configuración. No se realizó un cobro real."
            if status == "paid"
            else "La prueba de pago no se completó."
            if status == "failed"
            else "Pago de prueba pendiente. Continúa en la pasarela y usa una tarjeta de prueba.",
        }

    def read_integration_payment(self, payment_id, provider, user):
        self._assert_mode()
        payment = self._payment(payment_id, provider)
        self.assert_project_owner(payment["projectType"], payment["projectId"], user)
        # Refresh through the provider only. Visiting this URL never approves a payment.
        if payment["status"] == "pending":
            verified = self._verify_gateway(payment)
            if verified["status"] != "pending":
                payment = self._record_confirmation(payment, verified)
        elif payment["status"] == "paid":
            payment = self._complete_test_project(payment)
            self._send_receipt(payment)
        return self._summary(payment)

    def retry_receipt_email(self, payment_id, provider, user):
        payment = self._payment(payment_id, provider)
        self.assert_project_owner(payment["projectType"], payment["projectId"], user)
        if payment["status"] != "paid":
            raise NuvlyError("El correo se envía cuando el pago está aprobado.", 409, "PAYMENT_NOT_APPROVED")
        self._send_receipt(payment, enqueue=True)
        return {"receiptEmail": self.receipt_email.status(payment_id)}

    def accepted_terms_payment(self, payment_id, provider, user):
        payment = self._payment(payment_id, provider)
        self.assert_project_owner(payment["projectType"], payment["projectId"], user)
        if not (payment.get("termsAcceptance") or {}).get("document"):
            raise NuvlyError(
                "Este pago no tiene una constancia de condiciones aceptadas.", 404, "ACCEPTED_TERMS_NOT_FOUND"
            )
        return payment

    def handle_return(self, provider, payment_id, params):
        self._assert_mode()
        payment = self._payment(payment_id, provider)
        if payment["status"] == "paid":
            payment = self._complete_test_project(payment)
            self._send_receipt(payment)
            return payment["checkoutUrl"] + "?returned=1"
        if provider == "transbank":
            token = params.get("token_ws")
            if token:
                verified = self._verify_gateway(payment, str(token), commit=True)
                payment = self._record_confirmation(payment, verified)
            else:
                abort_token = str(params.get("TBK_TOKEN") or "")
                if not compare_digest(abort_token, str(payment.get("gatewayToken") or "")) or not abort_token:
                    raise NuvlyError("Retorno de Webpay inválido.", 400, "PAYMENT_TOKEN_MISMATCH")
                payment["status"] = "failed"
                self._save(payment)
        elif provider == "mercadopago":
            resource = params.get("payment_id") or params.get("collection_id")
            if resource and str(resource) != "null":
                payment = self._record_confirmation(payment, self._verify_gateway(payment, str(resource)))
        return payment["checkoutUrl"] + "?returned=1"

    def mercadopago_notification(self, resource_id, signature, request_id):
        gateways.assert_integration_mode()
        configured = get_settings().mercadopago_test_webhook_secret
        if not configured or not resource_id or not str(resource_id).isdigit() or not request_id:
            raise NuvlyError("Notificación de pruebas no configurada o inválida.", 401, "INVALID_WEBHOOK_SIGNATURE")
        parts = dict(part.strip().split("=", 1) for part in (signature or "").split(",") if "=" in part)
        stamp = parts.get("ts", "")
        try:
            seconds = int(stamp) / (1000 if int(stamp) > 10**12 else 1)
        except ValueError:
            raise NuvlyError("Firma inválida.", 401, "INVALID_WEBHOOK_SIGNATURE")
        manifest = f"id:{resource_id};request-id:{request_id};ts:{stamp};"
        expected = hmac_new(configured.get_secret_value().encode(), manifest.encode(), sha256).hexdigest()
        if abs(time() - seconds) > 300 or not compare_digest(expected, parts.get("v1", "")):
            raise NuvlyError("Firma inválida.", 401, "INVALID_WEBHOOK_SIGNATURE")
        remote = gateways._request("GET", gateways.MP_URL + "/v1/payments/" + str(resource_id), gateways._mp_headers())
        payment_id = str(remote.get("external_reference") or "")
        payment = self._payment(payment_id, "mercadopago")
        if payment["status"] != "paid":
            self._record_confirmation(payment, gateways.verify_test_payment(payment, str(resource_id)))
        else:
            self._complete_test_project(payment)
            self._send_receipt(payment)
        return {"received": True}
