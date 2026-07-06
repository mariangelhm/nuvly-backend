from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

import app.main as main_module
import pytest
from app.core.errors import NuvlyError
from app.modules.domain.schemas import (
    CustomerProjectCreate,
    CustomerData,
    CustomerWebsiteResponse,
    CustomerWebsiteUpdate,
    PublishRequest,
    WebsiteTemplateCreate,
    WebsiteTemplateUpdate,
)
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
        if "$or" in filters:
            clauses = filters["$or"] or []
            remaining_filters = {key: value for key, value in filters.items() if key != "$or"}
            if not any(InMemoryDomainRepository._matches(document, clause) for clause in clauses):
                return False
            return InMemoryDomainRepository._matches(document, remaining_filters)
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


def _website_payload_with_uploaded_images() -> Dict[str, Any]:
    payload = _website_payload()
    payload["pages"][0]["blocks"][0]["props"]["mediaImage"] = "/static/uploads/website_template/asset_hero.png"
    payload["metadata"]["coverImage"] = "/static/uploads/website_template/asset_cover.png"
    return payload


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
    assert project["ownerId"] is None
    assert project["ownerEmail"] == "lara@test.dev"
    assert project["selectionSource"] == "catalog"
    assert project["selectedAt"]
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


def test_create_customer_project_can_link_authenticated_user_context() -> None:
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
            externalAuthProvider="nuvly",
            externalAuthSubject="usr_123",
        ),
        current_user={"id": "usr_123", "email": "lara@test.dev", "name": "Lara"},
    )

    assert project["ownerId"] == "usr_123"
    assert project["ownerEmail"] == "lara@test.dev"
    assert project["externalAuthProvider"] == "nuvly"
    assert project["externalAuthSubject"] == "usr_123"


def test_list_customer_projects_by_owner_matches_owner_id_and_owner_email() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)

    created = template_service.create(WebsiteTemplateCreate.model_validate(_website_payload()))
    template_service.publish(created["id"])

    by_id = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
            externalAuthProvider="nuvly",
            externalAuthSubject="usr_123",
        ),
        current_user={"id": "usr_123", "email": "lara@test.dev", "name": "Lara"},
    )
    by_email = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )
    other = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Otro", email="otro@test.dev", phone="999"),
        )
    )

    projects = customer_service.list_by_owner(owner_id="usr_123", owner_email="lara@test.dev")

    assert [project["id"] for project in projects] == [by_email["id"], by_id["id"]]
    assert all(project["ownerEmail"] == "lara@test.dev" for project in projects)
    assert other["id"] not in {project["id"] for project in projects}


def test_customer_project_summary_uses_shared_listing_shape() -> None:
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

    summary = customer_service.to_product_summary(project)

    assert summary["id"] == project["id"]
    assert summary["productType"] == "website"
    assert summary["templateId"] == project["templateId"]
    assert summary["payment"]["status"] == "unpaid"
    assert summary["metadata"]["coverImage"] == project["metadata"]["coverImage"]


def test_get_customer_project_for_owner_allows_owner_email_match() -> None:
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

    loaded = customer_service.get_for_owner(project["id"], owner_email="lara@test.dev")

    assert loaded["id"] == project["id"]


def test_get_customer_project_for_owner_rejects_other_customer() -> None:
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

    with pytest.raises(NuvlyError) as exc:
        customer_service.get_for_owner(project["id"], owner_id="usr_other", owner_email="otro@test.dev")

    assert exc.value.status_code == 403
    assert exc.value.code == "CUSTOMER_PROJECT_FORBIDDEN"


def test_update_customer_project_for_owner_rejects_other_customer() -> None:
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

    with pytest.raises(NuvlyError) as exc:
        customer_service.update_for_owner(
            project["id"],
            CustomerWebsiteUpdate.model_validate(
                {
                    "title": project["title"],
                    "slug": project["slug"],
                    "planTier": project["planTier"],
                    "templateCategory": project["templateCategory"],
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
            ),
            owner_id="usr_other",
            owner_email="otro@test.dev",
        )

    assert exc.value.status_code == 403
    assert exc.value.code == "CUSTOMER_PROJECT_FORBIDDEN"


def test_customer_listing_routes_are_registered_in_openapi() -> None:
    paths = main_module.app.openapi()["paths"]

    assert "/api/customer/products" in paths
    assert "get" in paths["/api/customer/products"]
    assert "/api/customer/invitations" in paths
    assert "get" in paths["/api/customer/invitations"]
    assert "/api/customer/websites" in paths
    assert "get" in paths["/api/customer/websites"]


def test_create_customer_project_absolutizes_uploaded_image_urls_in_response_only() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)

    created = template_service.create(WebsiteTemplateCreate.model_validate(_website_payload_with_uploaded_images()))
    template_service.publish(created["id"])

    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        ),
        base_url="http://localhost:8000",
    )

    stored = repository.find_document(CUSTOMER_WEBSITE_CONFIG.collection, {"id": project["id"]})

    assert project["blocks"][0]["props"]["mediaImage"] == "http://localhost:8000/static/uploads/website_template/asset_hero.png"
    assert project["pages"][0]["blocks"][0]["props"]["mediaImage"] == "http://localhost:8000/static/uploads/website_template/asset_hero.png"
    assert project["metadata"]["coverImage"] == "http://localhost:8000/static/uploads/website_template/asset_cover.png"
    assert stored is not None
    assert stored["blocks"][0]["props"]["mediaImage"] == "/static/uploads/website_template/asset_hero.png"
    assert stored["metadata"]["coverImage"] == "/static/uploads/website_template/asset_cover.png"


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


def test_get_customer_project_absolutizes_uploaded_image_urls() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)

    created = template_service.create(WebsiteTemplateCreate.model_validate(_website_payload_with_uploaded_images()))
    template_service.publish(created["id"])
    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )

    loaded = customer_service.get(project["id"], base_url="http://localhost:8000")

    assert loaded["blocks"][0]["props"]["mediaImage"] == "http://localhost:8000/static/uploads/website_template/asset_hero.png"
    assert loaded["pages"][0]["blocks"][0]["props"]["mediaImage"] == "http://localhost:8000/static/uploads/website_template/asset_hero.png"
    assert loaded["metadata"]["coverImage"] == "http://localhost:8000/static/uploads/website_template/asset_cover.png"


def test_update_customer_project_preserves_existing_pages_when_root_blocks_are_empty() -> None:
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
        CustomerWebsiteUpdate.model_validate(
            {
                "title": project["title"],
                "slug": project["slug"],
                "planTier": project["planTier"],
                "templateCategory": project["templateCategory"],
                "styles": project["styles"],
                "layout": project["layout"],
                "blocks": [],
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

    assert updated["pages"][0]["blocks"] == project["pages"][0]["blocks"]
    assert updated["blocks"] == project["blocks"]


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
        assert "productType='website'" in exc.message
        assert "planTier='essential'" in exc.message
        assert "componentCode='hero'" in exc.message
        assert "variantCode='H8'" in exc.message
    else:
        raise AssertionError("Expected VARIANT_NOT_ALLOWED_FOR_PLAN")


def test_template_create_accepts_editor_variant_labels_and_component_code_aliases() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "pro"
    payload["templateCategory"] = "beauty"
    payload["pages"][0]["blocks"] = [
        {
            "id": "blk_navigation",
            "type": "navigation",
            "componentCode": "navigation",
            "variant": "M7-Organic-Premium-Frame",
            "variantCode": "M7-Organic-Premium-Frame",
            "enabled": True,
            "order": 1,
            "props": {},
            "settings": {},
        },
        {
            "id": "blk_whatsapp",
            "type": "whatsappFloating",
            "componentCode": "whatsapp_floating",
            "variant": "WA2-Floating-With-Label",
            "variantCode": "WA2-Floating-With-Label",
            "enabled": True,
            "order": 2,
            "props": {},
            "settings": {},
        },
    ]
    payload["layout"]["sectionOrder"] = ["blk_navigation", "blk_whatsapp"]

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))

    assert created["pages"][0]["blocks"][0]["variant"] == "M7-Organic-Premium-Frame"
    assert created["pages"][0]["blocks"][1]["type"] == "whatsappFloating"


def test_template_create_accepts_modern_studio_variant_codes() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "pro"
    payload["templateCategory"] = "beauty"
    payload["pages"][0]["blocks"] = [
        {
            "id": "blk_navigation",
            "type": "navigation",
            "componentCode": "navigation",
            "variant": "MP1-Organic-Premium-Frame",
            "variantCode": "MP1-Organic-Premium-Frame",
            "enabled": True,
            "order": 1,
            "props": {},
            "settings": {},
        },
        {
            "id": "blk_hero",
            "type": "hero",
            "componentCode": "hero",
            "variant": "HE1-Modern-Impact",
            "variantCode": "HE1-Modern-Impact",
            "enabled": True,
            "order": 2,
            "props": {},
            "settings": {},
        },
        {
            "id": "blk_services",
            "type": "services",
            "componentCode": "services",
            "variant": "SE1-Glass-Card",
            "variantCode": "SE1-Glass-Card",
            "enabled": True,
            "order": 3,
            "props": {},
            "settings": {},
        },
        {
            "id": "blk_lead_form",
            "type": "leadForm",
            "componentCode": "leadForm",
            "variant": "LFP5-Step-by-Step-Modal-Reveal",
            "variantCode": "LFP5-Step-by-Step-Modal-Reveal",
            "enabled": True,
            "order": 4,
            "props": {},
            "settings": {},
        },
    ]
    payload["layout"]["sectionOrder"] = ["blk_navigation", "blk_hero", "blk_services", "blk_lead_form"]

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))

    assert created["pages"][0]["blocks"][0]["variant"] == "MP1-Organic-Premium-Frame"
    assert created["pages"][0]["blocks"][1]["variant"] == "HE1-Modern-Impact"
    assert created["pages"][0]["blocks"][2]["variant"] == "SE1-Glass-Card"
    assert created["pages"][0]["blocks"][3]["variant"] == "LFP5-Step-by-Step-Modal-Reveal"


def test_template_create_accepts_musicians_right_drawer_navigation_variant() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "pro"
    payload["templateCategory"] = "portfolio"
    payload["pages"][0]["blocks"] = [
        {
            "id": "blk_navigation",
            "type": "navigation",
            "componentCode": "navigation",
            "variant": "MP4-Musicians-Right-Drawer",
            "variantCode": "MP4-Musicians-Right-Drawer",
            "enabled": True,
            "order": 1,
            "props": {
                "menuPosition": "right",
                "mobileMenuMode": "right-drawer",
            },
            "settings": {},
        },
        {
            "id": "blk_hero",
            "type": "hero",
            "componentCode": "hero",
            "variant": "HE1-Modern-Impact",
            "variantCode": "HE1-Modern-Impact",
            "enabled": True,
            "order": 2,
            "props": {},
            "settings": {},
        },
    ]
    payload["layout"]["sectionOrder"] = ["blk_navigation", "blk_hero"]

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))

    assert created["pages"][0]["blocks"][0]["variant"] == "MP4-Musicians-Right-Drawer"
    assert created["pages"][0]["blocks"][0]["props"]["menuPosition"] == "right"
    assert created["pages"][0]["blocks"][0]["props"]["mobileMenuMode"] == "right-drawer"


def test_template_create_rejects_unknown_variant_as_bad_request() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "pro"
    payload["templateCategory"] = "beauty"
    payload["pages"][0]["blocks"][0]["variant"] = "ZZ9-Unknown-Editor-Label"
    payload["pages"][0]["blocks"][0]["variantCode"] = "ZZ9-Unknown-Editor-Label-Does-Not-Exist"

    try:
        template_service.create(WebsiteTemplateCreate.model_validate(payload))
    except NuvlyError as exc:
        assert exc.code == "PRICING_VARIANT_NOT_FOUND"
        assert exc.status_code == 400
        assert "productType='website'" in exc.message
        assert "componentCode='hero'" in exc.message
        assert "variantCode='ZZ9-Unknown-Editor-Label-Does-Not-Exist'" in exc.message
    else:
        raise AssertionError("Expected PRICING_VARIANT_NOT_FOUND")


def test_template_create_rejects_unknown_component_as_bad_request_with_context() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "pro"
    payload["templateCategory"] = "beauty"
    payload["pages"][0]["blocks"][0]["type"] = "whatsappFloating"
    payload["pages"][0]["blocks"][0]["componentCode"] = "whatsapp_floating_missing"
    payload["pages"][0]["blocks"][0]["variant"] = "WA2-Floating-With-Label"
    payload["pages"][0]["blocks"][0]["variantCode"] = "WA2-Floating-With-Label"

    try:
        template_service.create(WebsiteTemplateCreate.model_validate(payload))
    except NuvlyError as exc:
        assert exc.code == "PRICING_COMPONENT_NOT_FOUND"
        assert exc.status_code == 400
        assert "productType='website'" in exc.message
        assert "componentCode='whatsapp_floating_missing'" in exc.message
    else:
        raise AssertionError("Expected PRICING_COMPONENT_NOT_FOUND")


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
        assert "productType='website'" in exc.message
        assert "planTier='essential'" in exc.message
        assert "componentCode='leadForm'" in exc.message
    else:
        raise AssertionError("Expected COMPONENT_NOT_ALLOWED_FOR_PLAN")


def test_template_create_allows_component_previously_blocked_by_category() -> None:
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

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))

    assert created["templateCategory"] == "beauty"
    assert created["pages"][0]["blocks"][0]["type"] == "projects"


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


def test_create_customer_project_from_custom_template_defaults_to_plan_base_price_when_snapshot_has_no_manual_price() -> None:
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
    assert project["metadata"]["basePrice"] == 250000


def test_create_customer_project_from_custom_template_preserves_manual_zero_base_price() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
    payload = _website_payload()
    payload["planTier"] = "custom"
    payload["templateCategory"] = "beauty"
    payload["metadata"]["basePrice"] = 0

    created = template_service.create(WebsiteTemplateCreate.model_validate(payload))
    template_service.publish(created["id"], publish_request=PublishRequest(priceMode="manual", basePrice=0))
    project = customer_service.create_from_template(
        CustomerProjectCreate(
            templateId=created["id"],
            customerData=CustomerData(name="Lara", email="lara@test.dev", phone="123"),
        )
    )

    assert project["planTier"] == "custom"
    assert project["metadata"]["basePrice"] == 0
    assert project["metadata"]["basePriceSource"] == "manual"


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


def test_update_customer_website_preserves_custom_design_payloads_for_custom_sites() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    template_service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    customer_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)

    payload = _website_payload()
    payload["title"] = "Nails Studio"
    payload["slug"] = "nails-studio-template"
    payload["planTier"] = "custom"
    payload["templateCategory"] = "beauty"
    payload["styles"] = {
        "themeId": "nails-studio",
        "colors": {"accent": "#e88cae"},
        "effects": {"glass": {"blur": 24}, "cardShadow": "0 24px 60px rgba(120, 47, 86, 0.18)"},
    }
    payload["layout"] = {
        "sectionOrder": ["blk_hero"],
        "canvas": {"maxWidth": 1320, "gutter": 28},
    }
    payload["seo"] = {
        "title": "Nails Studio",
        "description": "Custom studio website",
        "noIndex": False,
        "openGraph": {"image": "/assets/nails/cover.png"},
    }
    payload["metadata"] = {
        "category": "landing",
        "coverImage": "/assets/nails/cover.png",
        "tags": ["beauty"],
        "previewVariant": "desktop",
        "previewStyle": {"frame": "browser", "accent": "#e88cae"},
        "customFlag": "nails-custom",
    }
    payload["websiteData"] = {
        "businessName": "Nails Studio",
        "industry": "beauty",
        "contactEmail": "hello@nails.test",
        "booking": {"provider": "fresha", "url": "https://booking.nails.test"},
    }

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
                "styles": {
                    **project["styles"],
                    "effects": {
                        **project["styles"]["effects"],
                        "buttonGlow": "0 0 0 1px rgba(232,140,174,0.4)",
                    },
                },
                "layout": {
                    **project["layout"],
                    "canvas": {"maxWidth": 1440, "gutter": 32},
                },
                "pages": project["pages"],
                "seo": {
                    **project["seo"],
                    "openGraph": {"image": "/assets/nails/social-share.png"},
                },
                "metadata": {
                    **project["metadata"],
                    "previewStyle": {"frame": "browser", "accent": "#f4b6cc"},
                    "customFlag": "nails-studio-live",
                },
                "websiteData": {
                    **project["websiteData"],
                    "booking": {"provider": "booksy", "url": "https://book.nails.test"},
                },
                "customerData": {
                    **project["customerData"],
                    "preferences": {"language": "es-CL"},
                },
                "leadForms": project["leadForms"],
                "formSubmissions": project["formSubmissions"],
                "customDomain": project["customDomain"],
            }
        ),
    )

    response = CustomerWebsiteResponse.model_validate(updated).model_dump(mode="json")

    assert response["styles"]["effects"]["glass"]["blur"] == 24
    assert response["styles"]["effects"]["buttonGlow"] == "0 0 0 1px rgba(232,140,174,0.4)"
    assert response["layout"]["canvas"]["maxWidth"] == 1440
    assert response["seo"]["openGraph"]["image"] == "/assets/nails/social-share.png"
    assert response["metadata"]["previewStyle"]["accent"] == "#f4b6cc"
    assert response["metadata"]["customFlag"] == "nails-studio-live"
    assert response["websiteData"]["booking"]["provider"] == "booksy"
    assert response["customerData"]["preferences"]["language"] == "es-CL"
