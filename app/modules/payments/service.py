from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Dict
from urllib.parse import quote

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.modules.domain.defaults import default_payment
from app.modules.domain.repository import DomainRepository
from app.modules.domain.services import (
    CUSTOMER_INVITATION_CONFIG,
    CUSTOMER_WEBSITE_CONFIG,
    CustomerProjectService,
    append_status_history,
)
from app.modules.experiences.utils import new_id, utc_now_iso

logger = logging.getLogger(__name__)


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

    def _build_checkout_url(self, provider: str, payment_id: str) -> str:
        settings = get_settings()
        base_url = (settings.public_base_url or "http://localhost:8000").rstrip("/")
        return f"{base_url}/checkout/{provider}/{quote(payment_id)}"

    def create_checkout(self, payload) -> Dict[str, Any]:
        project_service = self._project_service(payload.projectType)
        project = project_service.get(payload.projectId)

        amount = float((project.get("metadata") or {}).get("basePrice") or 0)
        if amount <= 0:
            raise NuvlyError("El proyecto no tiene un precio base valido para checkout.", 400, "INVALID_PROJECT_PRICE")

        now = utc_now_iso()
        payment_id = new_id("pay")
        checkout_url = self._build_checkout_url(payload.provider, payment_id)
        payment_document = {
            "id": payment_id,
            "projectType": payload.projectType,
            "projectId": payload.projectId,
            "provider": payload.provider,
            "status": "pending",
            "amount": amount,
            "currency": "CLP",
            "checkoutUrl": checkout_url,
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
        if updated_project["customerStatus"] != "pending_payment":
            updated_project["customerStatus"] = "pending_payment"
            append_status_history(updated_project, "customerStatus", "payments", "checkout_created")
        updated_project["updatedAt"] = now

        logger.info(
            "Creating checkout | projectType=%s projectId=%s provider=%s amount=%s",
            payload.projectType,
            payload.projectId,
            payload.provider,
            amount,
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

        logger.info(
            "Payment webhook processed | provider=%s paymentId=%s projectType=%s projectId=%s status=%s",
            provider,
            updated_payment["id"],
            updated_payment["projectType"],
            updated_payment["projectId"],
            updated_payment["status"],
        )
        return updated_payment
