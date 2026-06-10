from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.core.errors import NuvlyError
from app.modules.domain.schemas import CustomerProjectCreate, CustomerData, CustomerWebsiteUpdate, WebsiteTemplateCreate, WebsiteTemplateUpdate
from app.modules.domain.services import (
    CUSTOMER_WEBSITE_CONFIG,
    WEBSITE_TEMPLATE_CONFIG,
    CustomerProjectService,
    TemplateService,
)
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
    root_blocks = [{"id": "blk_hero", "type": "hero", "variant": "H1", "enabled": True, "order": 1, "props": {"headline": "Hola"}, "settings": {}}]
    return {
        "title": "Buildframe",
        "slug": "buildframe",
        "experienceType": "web",
        "styles": {"themeId": "sunrise", "colors": {"accent": "#4a6cf7"}},
        "layout": {"sectionOrder": ["blk_hero"]},
        "pages": [
            {
                "id": "main",
                "kind": "primary",
                "title": "Web principal",
                "slug": "",
                "path": "/",
                "parentPageId": None,
                "source": {
                    "blockId": None,
                    "blockType": None,
                    "sourceItemIndex": None,
                    "sourceChildKey": None,
                },
                "seo": {},
                "settings": {},
                "blocks": root_blocks,
            },
            {
                "id": "blk_hero::details",
                "kind": "linked",
                "title": "Hero details",
                "slug": "hero-details",
                "path": "/hero-details",
                "parentPageId": "main",
                "source": {
                    "blockId": "blk_hero",
                    "blockType": "hero",
                    "sourceItemIndex": None,
                    "sourceChildKey": "details",
                },
                "seo": {},
                "settings": {"enabled": True},
                "blocks": [],
            },
        ],
        "seo": {"title": "SEO title", "description": "SEO description", "noIndex": False},
        "metadata": {"category": "landing", "coverImage": "/assets/cover.jpg", "tags": ["agency"]},
        "websiteData": {"industry": "creative-services", "businessName": "Buildframe"},
    }


def test_public_template_read_does_not_create_customer_project() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)

    created = template_service.create(WebsiteTemplateCreate.model_validate(_website_payload()))
    template_service.publish(created["id"])

    response = template_service.get_public_by_slug(created["slug"])

    assert response["snapshot"]["id"] == created["id"]
    assert repository.collections.get(CUSTOMER_WEBSITE_CONFIG.collection, []) == []


def test_create_customer_project_uses_published_snapshot_and_starts_as_draft() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)

    created = template_service.create(WebsiteTemplateCreate.model_validate(_website_payload()))
    published_snapshot = template_service.publish(created["id"])

    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )

    assert project["templateId"] == created["id"]
    assert project["templateSnapshotId"] == published_snapshot["id"]
    assert project["productType"] == "website"
    assert project["planTier"] == "plus"
    assert project["templateCategory"] == "corporate"
    assert project["customerStatus"] == "draft"
    assert project["payment"]["status"] == "unpaid"
    assert project["statusHistory"][0]["status"] == "draft"
    assert project["publicSlug"] is None
    assert project["styles"] == published_snapshot["snapshot"]["styles"]
    assert project["layout"] == published_snapshot["snapshot"]["layout"]
    assert project["blocks"] == published_snapshot["snapshot"]["blocks"]
    assert project["pages"] == published_snapshot["snapshot"]["pages"]
    assert project["seo"] == published_snapshot["snapshot"]["seo"]
    assert project["metadata"] == published_snapshot["snapshot"]["metadata"]


def test_update_customer_project_generates_public_slug_from_title() -> None:
    repository = InMemoryDomainRepository()
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

    updated = customer_service.update(
        project["id"],
        type(
            "Payload",
            (),
            {
                "model_dump": lambda self, mode="json", exclude_none=True: {
                    "title": "Mi Sitio Final",
                    "styles": project["styles"],
                    "layout": project["layout"],
                    "blocks": project["blocks"],
                    "seo": project["seo"],
                    "metadata": project["metadata"],
                    "websiteData": project["websiteData"],
                    "customerData": project["customerData"],
                    "leadForms": project["leadForms"],
                    "formSubmissions": project["formSubmissions"],
                    "customDomain": project["customDomain"],
                }
            },
        )(),
    )

    assert updated["publicSlug"] == "mi-sitio-final"
    assert updated["pages"][0]["blocks"] == project["blocks"]
    assert updated["pages"][1]["id"] == "blk_hero::details"


def test_pending_payment_requires_title_and_public_slug() -> None:
    repository = InMemoryDomainRepository()
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

    try:
        customer_service.update_status(project["id"], "pending_payment", None, None)
    except Exception as exc:
        assert getattr(exc, "code", None) == "PUBLIC_SLUG_REQUIRED"
    else:
        raise AssertionError("Expected PUBLIC_SLUG_REQUIRED")


def test_template_create_rejects_variant_blocked_by_plan() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "essential"
    payload["templateCategory"] = "construction"
    payload["pages"][0]["blocks"][0]["variant"] = "H8"

    try:
        template_service.create(WebsiteTemplateCreate.model_validate(payload))
    except NuvlyError as exc:
        assert exc.code == "VARIANT_NOT_ALLOWED_FOR_PLAN"
    else:
        raise AssertionError("Expected VARIANT_NOT_ALLOWED_FOR_PLAN")


def test_template_create_rejects_component_blocked_by_plan_before_variant() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "essential"
    payload["templateCategory"] = "construction"
    payload["blocks"] = [
        {"id": "blk_lead_form", "type": "leadForm", "variant": "Q1", "enabled": True, "order": 1, "props": {}, "settings": {}}
    ]
    payload["pages"][0]["blocks"] = deepcopy(payload["blocks"])
    payload["layout"]["sectionOrder"] = ["blk_lead_form"]

    try:
        template_service.create(WebsiteTemplateCreate.model_validate(payload))
    except NuvlyError as exc:
        assert exc.code == "COMPONENT_NOT_ALLOWED_FOR_PLAN"
    else:
        raise AssertionError("Expected COMPONENT_NOT_ALLOWED_FOR_PLAN")


def test_template_create_rejects_component_blocked_by_category() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "plus"
    payload["templateCategory"] = "beauty"
    payload["blocks"] = [
        {"id": "blk_projects", "type": "projects", "variant": "G1", "enabled": True, "order": 1, "props": {}, "settings": {}}
    ]
    payload["pages"][0]["blocks"] = deepcopy(payload["blocks"])
    payload["layout"]["sectionOrder"] = ["blk_projects"]

    try:
        template_service.create(WebsiteTemplateCreate.model_validate(payload))
    except NuvlyError as exc:
        assert exc.code == "COMPONENT_NOT_ALLOWED_FOR_CATEGORY"
    else:
        raise AssertionError("Expected COMPONENT_NOT_ALLOWED_FOR_CATEGORY")


def test_template_create_allows_custom_plan_with_unknown_variant_and_marks_flags() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "custom"
    payload["templateCategory"] = "beauty"
    payload["pages"][0]["blocks"][0]["type"] = "dashboard"
    payload["pages"][0]["blocks"][0]["variant"] = "analytics-v99"

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))

    assert created["planTier"] == "custom"
    assert created["commercialValidationSkipped"] is True
    assert created["pages"][0]["blocks"][0]["customVariant"] is True
    assert created["blocks"][0]["customVariant"] is True


def test_template_update_allows_custom_plan_with_unknown_variant_and_marks_flags() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    created = template_service.create(WebsiteTemplateCreate.model_validate(_website_payload()))

    payload = _website_payload()
    payload["title"] = "Buildframe Custom"
    payload["slug"] = created["slug"]
    payload["planTier"] = "custom"
    payload["templateCategory"] = "beauty"
    payload["pages"][0]["blocks"][0]["type"] = "wizard"
    payload["pages"][0]["blocks"][0]["variant"] = "stepper-enterprise"

    updated = template_service.update(created["id"], WebsiteTemplateUpdate.model_validate(payload))

    assert updated["planTier"] == "custom"
    assert updated["commercialValidationSkipped"] is True
    assert updated["pages"][0]["blocks"][0]["customVariant"] is True


def test_create_customer_project_from_custom_template_keeps_unknown_blocks() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "custom"
    payload["templateCategory"] = "beauty"
    payload["pages"][0]["blocks"][0]["type"] = "dashboard"
    payload["pages"][0]["blocks"][0]["variant"] = "owner-kpis"

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))
    template_service.publish(created["id"])
    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )

    assert project["planTier"] == "custom"
    assert project["commercialValidationSkipped"] is True
    assert project["pages"][0]["blocks"][0]["type"] == "dashboard"
    assert project["pages"][0]["blocks"][0]["variant"] == "owner-kpis"
    assert project["pages"][0]["blocks"][0]["customVariant"] is True


def test_create_customer_project_from_custom_template_preserves_manual_base_price() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "custom"
    payload["templateCategory"] = "beauty"
    payload["metadata"]["basePrice"] = 99000

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))
    template_service.publish(created["id"])
    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )

    assert project["planTier"] == "custom"
    assert project["metadata"]["basePrice"] == 99000


def test_create_customer_project_from_custom_template_preserves_zero_base_price() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "custom"
    payload["templateCategory"] = "beauty"
    payload["metadata"]["basePrice"] = 0

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))
    template_service.publish(created["id"])
    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )

    assert project["planTier"] == "custom"
    assert project["metadata"]["basePrice"] == 0


def test_update_customer_project_allows_custom_plan_with_unknown_variant() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "custom"
    payload["templateCategory"] = "beauty"
    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))
    template_service.publish(created["id"])
    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )

    updated = customer_service.update(
        project["id"],
        CustomerWebsiteUpdate.model_validate(
            {
                "title": "Nails Studio",
                "slug": project["slug"],
                "publicSlug": "nails-studio",
                "planTier": "custom",
                "templateCategory": "beauty",
                "styles": project["styles"],
                "layout": {"sectionOrder": ["blk_dashboard"]},
                "pages": [
                    {
                        **project["pages"][0],
                        "blocks": [
                            {
                                "id": "blk_dashboard",
                                "type": "dashboard",
                                "variant": "nails-admin-v1",
                                "enabled": True,
                                "order": 1,
                                "props": {"title": "Admin"},
                                "settings": {},
                            }
                        ],
                    },
                    project["pages"][1],
                ],
                "seo": project["seo"],
                "metadata": project["metadata"],
                "websiteData": project["websiteData"],
                "customerData": project["customerData"],
                "leadForms": project["leadForms"],
                "formSubmissions": project["formSubmissions"],
                "customDomain": project["customDomain"],
            }
        ),
    )

    assert updated["planTier"] == "custom"
    assert updated["commercialValidationSkipped"] is True
    assert updated["pages"][0]["blocks"][0]["type"] == "dashboard"
    assert updated["pages"][0]["blocks"][0]["customVariant"] is True
