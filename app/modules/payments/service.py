from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Dict
from urllib.parse import quote

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.domain.defaults import default_payment
from app.modules.domain.repository import DomainRepository
from app.modules.domain.services import (
    CUSTOMER_INVITATION_CONFIG,
    CUSTOMER_WEBSITE_CONFIG,
    CustomerProjectService,
    append_status_history,
)

logger = logging.getLogger(__name__)

CUSTOM_DOMAIN_SURCHARGE_CLP = 15000
CUSTOM_DOMAIN_EXPLANATION = (
    "Un dominio propio permite publicar tu sitio con una direccion personalizada "
    "como www.tumarca.cl. Si no lo eliges, publicaremos tu web en una URL de Nuvly."
)


@dataclass(frozen=True)
class PaymentProjectConfig:
    project_type: str
    customer_config: Any


PROJECT_CONFIGS: dict[str, PaymentProjectConfig] = {
    "invitation": PaymentProjectConfig(project_type="invitation", customer_config=CUSTOMER_INVITATION_CONFIG),
    "website": PaymentProjectConfig(project_type="website", customer_config=CUSTOMER_WEBSITE_CONFIG),
}


class PaymentService:
    def __init__(self, repository=None):
        self.repository = repository or DomainRepository()

    def _project_service(self, project_type: str) -> CustomerProjectService:
        config = PROJECT_CONFIGS.get(project_type)
        if config is None:
            raise NuvlyError("Tipo de proyecto de pago no soportado.", 400, "INVALID_PROJECT_TYPE")
        return CustomerProjectService(config.customer_config, repository=self.repository)

    def _payments_collection_name(self) -> str:
        return "payments"

    def _resolve_public_base_url(self, override_base_url: str | None = None) -> str:
        settings = get_settings()
        if settings.public_base_url:
            return settings.public_base_url.rstrip("/")
        if override_base_url:
            return override_base_url.rstrip("/")
        return "http://localhost:8000"

    def _build_checkout_url(self, provider: str, payment_id: str, base_url: str | None = None) -> str:
        effective_base_url = self._resolve_public_base_url(base_url)
        return f"{effective_base_url}/checkout/{provider}/{quote(payment_id)}"

    def _build_public_website_url(self, public_slug: str, base_url: str | None = None) -> str:
        effective_base_url = self._resolve_public_base_url(base_url)
        return f"{effective_base_url}/w/{quote(public_slug)}"

    def _build_public_invitation_url(self, public_slug: str, base_url: str | None = None) -> str:
        effective_base_url = self._resolve_public_base_url(base_url)
        return f"{effective_base_url}/i/{quote(public_slug)}"

    def create_checkout(self, payload, base_url: str | None = None) -> Dict[str, Any]:
        project_service = self._project_service(payload.projectType)
        project = project_service.get(payload.projectId)
        project_service._validate_ready_for_pending_payment(project)

        base_amount = float((project.get("metadata") or {}).get("basePrice") or 0)
        if base_amount <= 0:
            raise NuvlyError("El proyecto no tiene un precio base valido para checkout.", 400, "INVALID_PROJECT_PRICE")
        if payload.withCustomDomain and payload.projectType != "website":
            raise NuvlyError("El dominio propio solo esta disponible para websites.", 400, "CUSTOM_DOMAIN_NOT_SUPPORTED")

        custom_domain = (payload.customDomain or "").strip() or None
        custom_domain_surcharge = CUSTOM_DOMAIN_SURCHARGE_CLP if payload.withCustomDomain else 0
        amount = base_amount + custom_domain_surcharge

        now = utc_now_iso()
        payment_id = new_id("pay")
        checkout_url = self._build_checkout_url(payload.provider, payment_id, base_url)
        payment_document = {
            "id": payment_id,
            "paymentId": payment_id,
            "projectType": payload.projectType,
            "projectId": payload.projectId,
            "provider": payload.provider,
            "status": "pending",
            "amount": amount,
            "currency": "CLP",
            "checkoutUrl": checkout_url,
            "checkoutBaseUrl": self._resolve_public_base_url(base_url),
            "withCustomDomain": payload.withCustomDomain,
            "customDomain": custom_domain,
            "customDomainSurcharge": custom_domain_surcharge,
            "domainOptionExplanation": CUSTOM_DOMAIN_EXPLANATION if payload.projectType == "website" else None,
            "providerPaymentId": None,
            "createdAt": now,
            "updatedAt": now,
        }

        payment_info = default_payment()
        payment_info.update(
            {
                "status": "pending",
                "provider": payload.provider,
                "amount": amount,
                "currency": "CLP",
                "paidAt": None,
            }
        )

        updated_project = dict(project)
        updated_project["payment"] = payment_info
        if payload.projectType == "website":
            updated_project["customDomain"] = custom_domain if payload.withCustomDomain else None
        if updated_project["customerStatus"] != "pending_payment":
            updated_project["customerStatus"] = "pending_payment"
            append_status_history(updated_project, "customerStatus", "payments", "checkout_created")
        updated_project["updatedAt"] = now

        logger.info(
            "Creating checkout | projectType=%s projectId=%s provider=%s amount=%s withCustomDomain=%s",
            payload.projectType,
            payload.projectId,
            payload.provider,
            amount,
            payload.withCustomDomain,
        )

        self.repository.insert_document(
            self._payments_collection_name(),
            payment_document,
            duplicate_message="Ya existe un pago con ese id.",
            duplicate_code="DUPLICATED_PAYMENT_ID",
        )
        project_service.repository.replace_document(
            project_service.config.collection,
            payload.projectId,
            updated_project,
            project_service.config.not_found_message,
            project_service.config.not_found_code,
            project_service.config.duplicate_message,
        )

        return payment_document

    def _build_manual_confirmation_response(
        self,
        payment_id: str,
        provider: str,
        payment: Dict[str, Any] | None,
        message: str,
    ) -> Dict[str, Any]:
        if payment is None:
            return {
                "ok": False,
                "message": message,
                "paymentId": payment_id,
                "provider": provider,
                "status": "failed",
            }

        final_url = payment.get("websiteUrl") or payment.get("invitationUrl")
        return {
            "ok": True,
            "message": message,
            "paymentId": payment["id"],
            "provider": payment["provider"],
            "status": payment["status"],
            "projectType": payment.get("projectType"),
            "projectId": payment.get("projectId"),
            "amount": payment.get("amount"),
            "currency": payment.get("currency"),
            "finalUrl": final_url,
            "websiteUrl": payment.get("websiteUrl"),
            "invitationUrl": payment.get("invitationUrl"),
        }

    def confirm_payment_manually(self, payment_id: str, provider: str) -> Dict[str, Any]:
        payment = self.repository.find_document(
            self._payments_collection_name(),
            {"id": payment_id, "provider": provider},
        )
        if not payment:
            return self._build_manual_confirmation_response(
                payment_id,
                provider,
                None,
                "Pago no encontrado para confirmacion manual.",
            )

        if payment.get("status") != "paid":
            payment = self.process_webhook(
                provider,
                type(
                    "ManualWebhookPayload",
                    (),
                    {
                        "paymentId": payment_id,
                        "status": "approved",
                        "providerPaymentId": f"manual_{payment_id}",
                    },
                )(),
            )

        return self._build_manual_confirmation_response(
            payment_id,
            provider,
            payment,
            "Pago confirmado manualmente.",
        )

    def process_webhook(self, provider: str, payload) -> Dict[str, Any]:
        payment = self.repository.find_document(self._payments_collection_name(), {"id": payload.paymentId, "provider": provider})
        if not payment:
            raise NuvlyError("Pago no encontrado para el webhook recibido.", 404, "PAYMENT_NOT_FOUND")

        project_service = self._project_service(payment["projectType"])
        project = project_service.get(payment["projectId"])
        now = utc_now_iso()

        updated_payment = dict(payment)
        updated_project = dict(project)
        payment_info = dict(updated_project.get("payment") or default_payment())
        payment_info["provider"] = provider
        payment_info["providerPaymentId"] = payload.providerPaymentId
        payment_info["amount"] = updated_payment.get("amount")
        payment_info["currency"] = updated_payment.get("currency")
        public_website_url: str | None = None
        public_invitation_url: str | None = None

        if payload.status == "approved":
            updated_payment["status"] = "paid"
            updated_project["customerStatus"] = "paid"
            payment_info["status"] = "paid"
            payment_info["paidAt"] = now
            append_status_history(updated_project, "customerStatus", provider, "payment_approved")
        else:
            updated_payment["status"] = "failed"
            updated_project["customerStatus"] = "payment_failed"
            payment_info["status"] = "failed"
            payment_info["paidAt"] = None
            append_status_history(updated_project, "customerStatus", provider, "payment_failed")

        updated_payment["providerPaymentId"] = payload.providerPaymentId
        updated_payment["updatedAt"] = now
        updated_project["payment"] = payment_info
        updated_project["updatedAt"] = now
        # If payment failed and the project was previously waiting for payment, free reserved publicSlug
        try:
            previous_status = project.get("customerStatus")
        except Exception:
            previous_status = None
        if payload.status == "failed" and previous_status == "pending_payment":
            # Clear publicSlug to allow reuse and avoid leaving a reserved URL when payment didn't complete
            updated_project["publicSlug"] = None
            # Also clear any published snapshot references just in case
            updated_project["publishedSnapshotId"] = None
            updated_project["lastPublishedAt"] = None
        self.repository.replace_document(
            self._payments_collection_name(),
            updated_payment["id"],
            updated_payment,
            "Pago no encontrado.",
            "PAYMENT_NOT_FOUND",
            "Ya existe un pago duplicado.",
            duplicate_code="DUPLICATED_PAYMENT_ID",
        )
        project_service.repository.replace_document(
            project_service.config.collection,
            project["id"],
            updated_project,
            project_service.config.not_found_message,
            project_service.config.not_found_code,
            project_service.config.duplicate_message,
        )

        if payload.status == "approved" and updated_project.get("publicSlug"):
            should_publish = False
            final_url: str | None = None
            url_field: str | None = None

            if payment["projectType"] == "website" and not payment.get("withCustomDomain"):
                should_publish = True
                final_url = self._build_public_website_url(
                    updated_project["publicSlug"],
                    payment.get("checkoutBaseUrl"),
                )
                url_field = "websiteUrl"
            elif payment["projectType"] == "invitation":
                should_publish = True
                final_url = self._build_public_invitation_url(
                    updated_project["publicSlug"],
                    payment.get("checkoutBaseUrl"),
                )
                url_field = "invitationUrl"

            if should_publish and final_url and url_field:
                published_snapshot = project_service.publish(
                    project["id"],
                    changed_by=provider,
                    reason="payment_approved_auto_publish",
                )
                updated_project = project_service.get(project["id"])
                if url_field == "websiteUrl":
                    public_website_url = final_url
                else:
                    public_invitation_url = final_url
                updated_payment[url_field] = final_url
                updated_payment["publishedSnapshotId"] = published_snapshot["id"]
                self.repository.replace_document(
                    self._payments_collection_name(),
                    updated_payment["id"],
                    updated_payment,
                    "Pago no encontrado.",
                    "PAYMENT_NOT_FOUND",
                    "Ya existe un pago duplicado.",
                    duplicate_code="DUPLICATED_PAYMENT_ID",
                )

        logger.info(
            "Payment webhook processed | provider=%s paymentId=%s projectType=%s projectId=%s status=%s",
            provider,
            updated_payment["id"],
            updated_payment["projectType"],
            updated_payment["projectId"],
            updated_payment["status"],
        )
        if public_website_url:
            updated_payment["websiteUrl"] = public_website_url
        if public_invitation_url:
            updated_payment["invitationUrl"] = public_invitation_url
        return updated_payment
