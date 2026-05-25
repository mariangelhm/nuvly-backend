from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.modules.domain.schemas import CustomerData, CustomerProjectCreate, WebsiteTemplateCreate
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService, WEBSITE_TEMPLATE_CONFIG, TemplateService
from app.modules.payments.schemas import CreateCheckoutRequest, PaymentWebhookPayload
from app.modules.payments.service import PaymentService
from app.modules.pricing.service import ensure_pricing_seed


def _get_nested(document: Dict[str, Any], dotted_key: str) -> Any:
    value: Any = document
    for part in dotted_key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


class InMemoryDomainRepository:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}

    def database_name(self) -> str:
        return "in-memory"

    def insert_document(
        self,
        collection_name: str,
        document: Dict[str, Any],
        duplicate_message: str,
        duplicate_code: str = "DUPLICATED_SLUG",
    ) -> Dict[str, Any]:
        self.collections.setdefault(collection_name, []).append(deepcopy(document))
        return deepcopy(document)

    def find_documents(
        self,
        collection_name: str,
        filters: Dict[str, Any],
        limit: int = 20,
        skip: int = 0,
        sort_field: str = "updatedAt",
        sort_direction: int = -1,
    ) -> list[Dict[str, Any]]:
        documents = [deepcopy(document) for document in self.collections.get(collection_name, []) if self._matches(document, filters)]
        documents.sort(key=lambda document: _get_nested(document, sort_field), reverse=sort_direction == -1)
        documents = documents[skip:]
        if limit > 0:
            documents = documents[:limit]
        return documents

    def find_document(self, collection_name: str, filters: Dict[str, Any]) -> Dict[str, Any] | None:
        for document in self.collections.get(collection_name, []):
            if self._matches(document, filters):
                return deepcopy(document)
        return None

    def find_document_by_slug(self, collection_name: str, slug: str) -> Dict[str, Any] | None:
        return self.find_document(collection_name, {"slug": slug})

    def replace_document(
        self,
        collection_name: str,
        document_id: str,
        document: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
        duplicate_message: str,
        duplicate_code: str = "DUPLICATED_SLUG",
    ) -> Dict[str, Any]:
        documents = self.collections.get(collection_name, [])
        for index, current in enumerate(documents):
            if current.get("id") == document_id:
                documents[index] = deepcopy(document)
                return deepcopy(document)
        raise AssertionError(f"Document not found in test repository: {collection_name}/{document_id}")

    def count_documents(self, collection_name: str, filters: Dict[str, Any]) -> int:
        return len([document for document in self.collections.get(collection_name, []) if self._matches(document, filters)])

    @staticmethod
    def _matches(document: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for key, expected in filters.items():
            value = _get_nested(document, key)
            if isinstance(expected, dict) and "$in" in expected:
                if not isinstance(value, list) or not any(item in expected["$in"] for item in value):
                    return False
                continue
            if value != expected:
                return False
        return True


def _website_payload() -> Dict[str, Any]:
    return {
        "title": "Buildframe",
        "slug": "buildframe",
        "experienceType": "web",
        "styles": {"themeId": "sunrise"},
        "layout": {"sectionOrder": ["blk_hero"]},
        "blocks": [{"id": "blk_hero", "type": "hero", "variant": "hero-a", "enabled": True, "order": 1, "props": {}, "settings": {}}],
        "seo": {"title": "SEO title", "description": "SEO description", "noIndex": False},
        "metadata": {"category": "landing", "coverImage": "/assets/cover.jpg", "tags": ["agency"], "basePrice": 149},
        "websiteData": {"industry": "creative-services", "businessName": "Buildframe"},
    }


def _create_customer_project(repository: InMemoryDomainRepository) -> Dict[str, Any]:
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
    created = template_service.create(WebsiteTemplateCreate.model_validate(_website_payload()))
    template_service.publish(created["id"])
    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )
    project["publicSlug"] = "buildframe-lara"
    return repository.replace_document(
        CUSTOMER_WEBSITE_CONFIG.collection,
        project["id"],
        project,
        CUSTOMER_WEBSITE_CONFIG.not_found_message,
        CUSTOMER_WEBSITE_CONFIG.not_found_code,
        CUSTOMER_WEBSITE_CONFIG.duplicate_message,
    )


def test_create_checkout_sets_project_to_pending_payment_and_creates_payment() -> None:
    repository = InMemoryDomainRepository()
    project = _create_customer_project(repository)
    service = PaymentService(repository=repository)

    payment = service.create_checkout(
        CreateCheckoutRequest(projectType="website", projectId=project["id"], provider="mercadopago")
    )

    stored_project = repository.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert payment["status"] == "pending"
    assert payment["projectId"] == project["id"]
    assert payment["checkoutUrl"]
    assert stored_project is not None
    assert stored_project["customerStatus"] == "pending_payment"
    assert stored_project["payment"]["status"] == "pending"
    assert stored_project["payment"]["provider"] == "mercadopago"
    assert stored_project["statusHistory"][-1]["status"] == "pending_payment"


def test_approved_webhook_marks_payment_paid_and_project_paid() -> None:
    repository = InMemoryDomainRepository()
    project = _create_customer_project(repository)
    service = PaymentService(repository=repository)
    payment = service.create_checkout(
        CreateCheckoutRequest(projectType="website", projectId=project["id"], provider="transbank")
    )

    updated_payment = service.process_webhook(
        "transbank",
        PaymentWebhookPayload(paymentId=payment["id"], status="approved", providerPaymentId="tbk_123"),
    )

    stored_project = repository.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert updated_payment["status"] == "paid"
    assert stored_project is not None
    assert stored_project["customerStatus"] == "paid"
    assert stored_project["payment"]["status"] == "paid"
    assert stored_project["payment"]["paidAt"] is not None
    assert stored_project["statusHistory"][-1]["status"] == "paid"


def test_failed_webhook_marks_payment_failed_and_project_payment_failed() -> None:
    repository = InMemoryDomainRepository()
    project = _create_customer_project(repository)
    service = PaymentService(repository=repository)
    payment = service.create_checkout(
        CreateCheckoutRequest(projectType="website", projectId=project["id"], provider="mercadopago")
    )

    updated_payment = service.process_webhook(
        "mercadopago",
        PaymentWebhookPayload(paymentId=payment["id"], status="failed", providerPaymentId="mp_123"),
    )

    stored_project = repository.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})
    assert updated_payment["status"] == "failed"
    assert stored_project is not None
    assert stored_project["customerStatus"] == "payment_failed"
    assert stored_project["payment"]["status"] == "failed"
    assert stored_project["statusHistory"][-1]["status"] == "payment_failed"
