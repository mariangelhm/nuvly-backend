from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Dict

from app.core.errors import NuvlyError
from app.modules.domain.schemas import InvitationTemplateCreate, WebsiteTemplateCreate
from app.modules.domain.services import (
    INVITATION_TEMPLATE_CONFIG,
    WEBSITE_TEMPLATE_CONFIG,
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


def _website_payload(catalog_visible: bool = False) -> Dict[str, Any]:
    return {
        "title": "Public Website Template",
        "slug": "public-website-template",
        "experienceType": "web",
        "styles": {"themeId": "sunrise"},
        "layout": {"sectionOrder": ["blk_hero"]},
        "blocks": [{"id": "blk_hero", "type": "hero", "variant": "H1", "enabled": True, "order": 1, "props": {}, "settings": {}}],
        "seo": {"title": "SEO title", "description": "SEO description", "noIndex": False},
        "metadata": {
            "category": "landing",
            "style": "editorial",
            "purpose": "lead-generation",
            "coverImage": "/assets/cover.jpg",
            "badge": "Nuevo",
            "featured": True,
            "level": "premium",
            "basePrice": 99,
            "tags": ["agency"],
            "catalogVisible": catalog_visible,
            "previewVariant": "desktop",
            "previewStyle": {"frame": "browser"},
        },
        "websiteData": {"industry": "creative-services"},
    }


def _invitation_payload(catalog_visible: bool = False) -> Dict[str, Any]:
    return {
        "title": "Public Invitation Template",
        "slug": "public-invitation-template",
        "styles": {"themeId": "garden"},
        "layout": {"sectionOrder": ["blk_intro"]},
        "blocks": [{"id": "blk_intro", "type": "intro", "variant": "intro-a", "enabled": True, "order": 1, "props": {}, "settings": {}}],
        "seo": {"title": "Invitation SEO", "description": "Invitation desc", "noIndex": False},
        "metadata": {
            "category": "wedding",
            "style": "romantic",
            "purpose": "invitation",
            "eventType": "wedding",
            "coverImage": "/assets/invitation-cover.jpg",
            "badge": "Top",
            "featured": True,
            "level": "premium",
            "basePrice": 49,
            "tags": ["gold"],
            "catalogVisible": catalog_visible,
            "previewVariant": "mobile",
            "previewStyle": {"frame": "phone"},
        },
        "invitationData": {"eventType": "wedding"},
    }


def test_publish_updates_template_status_and_public_list_ignores_catalog_visible() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)

    created = service.create(WebsiteTemplateCreate.model_validate(_website_payload(catalog_visible=False)))
    service.publish(created["id"], changed_by="tester", reason="manual_publish")

    stored = repository.find_document(WEBSITE_TEMPLATE_CONFIG.collection, {"id": created["id"]})
    assert stored is not None
    assert stored["templateStatus"] == "published"
    assert stored["lastPublishedAt"] is not None
    assert stored["publishedSnapshotId"] is not None
    assert stored["statusHistory"][-1]["status"] == "published"

    public_items = service.list_public()
    assert len(public_items) == 1
    assert public_items[0]["id"] == created["id"]
    assert public_items[0]["slug"] == created["slug"]
    assert public_items[0]["templateStatus"] == "published"
    assert public_items[0]["publishedSnapshotId"] is not None
    assert public_items[0]["updatedAt"] is not None
    assert public_items[0]["metadata"]["catalogVisible"] is False
    assert public_items[0]["metadata"]["coverImage"] == "/assets/cover.jpg"


def test_public_get_by_slug_reads_current_published_snapshot_without_catalog_visible() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    service = TemplateService(INVITATION_TEMPLATE_CONFIG, repository=repository)

    created = service.create(InvitationTemplateCreate.model_validate(_invitation_payload(catalog_visible=False)))
    published_snapshot = service.publish(created["id"])

    response = service.get_public_by_slug(created["slug"])

    assert response["id"] == published_snapshot["id"]
    assert response["snapshot"]["id"] == created["id"]
    assert response["snapshot"]["metadata"]["coverImage"] == "/assets/invitation-cover.jpg"


def test_invitation_legacy_linked_pages_are_preserved_in_pages_snapshot() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    service = TemplateService(INVITATION_TEMPLATE_CONFIG, repository=repository)
    payload = _invitation_payload(catalog_visible=False)
    payload["metadata"]["linkedPages"] = [
        {
            "id": "schedule-details",
            "kind": "linked",
            "title": "Schedule details",
            "slug": "schedule-details",
            "path": "/schedule-details",
            "parentPageId": "main",
            "source": {
                "blockId": "blk_intro",
                "blockType": "intro",
                "sourceItemIndex": None,
                "sourceChildKey": "details",
            },
            "seo": {},
            "settings": {"enabled": True},
            "blocks": [],
        }
    ]

    created = service.create(InvitationTemplateCreate.model_validate(payload))
    published_snapshot = service.publish(created["id"])
    public_response = service.get_public_by_slug(created["slug"])

    assert created["pages"][1]["id"] == "schedule-details"
    assert published_snapshot["snapshot"]["pages"][1]["path"] == "/schedule-details"
    assert public_response["snapshot"]["metadata"]["linkedPages"][0]["id"] == "schedule-details"


def test_public_list_includes_published_template_without_snapshot_and_logs(caplog) -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)
    caplog.set_level(logging.INFO)

    created = service.create(WebsiteTemplateCreate.model_validate(_website_payload(catalog_visible=False)))
    stored = repository.find_document(WEBSITE_TEMPLATE_CONFIG.collection, {"id": created["id"]})
    assert stored is not None
    stored["templateStatus"] = "published"
    stored["lastPublishedAt"] = "2026-05-21T10:00:00Z"
    repository.replace_document(
        WEBSITE_TEMPLATE_CONFIG.collection,
        created["id"],
        stored,
        WEBSITE_TEMPLATE_CONFIG.not_found_message,
        WEBSITE_TEMPLATE_CONFIG.not_found_code,
        WEBSITE_TEMPLATE_CONFIG.duplicate_message,
    )

    public_items = service.list_public()

    assert len(public_items) == 1
    assert public_items[0]["id"] == created["id"]
    assert public_items[0]["publishedSnapshotId"] is None
    assert "filter={'templateStatus': 'published'}" in caplog.text
    assert "totalPublishedFound=1" in caplog.text
    assert created["id"] in caplog.text


def test_public_list_filters_by_template_status_not_status_field() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)

    created = service.create(WebsiteTemplateCreate.model_validate(_website_payload(catalog_visible=False)))
    stored = repository.find_document(WEBSITE_TEMPLATE_CONFIG.collection, {"id": created["id"]})
    assert stored is not None
    stored["status"] = "published"
    repository.replace_document(
        WEBSITE_TEMPLATE_CONFIG.collection,
        created["id"],
        stored,
        WEBSITE_TEMPLATE_CONFIG.not_found_message,
        WEBSITE_TEMPLATE_CONFIG.not_found_code,
        WEBSITE_TEMPLATE_CONFIG.duplicate_message,
    )

    public_items = service.list_public()

    assert public_items == []


def test_unpublished_template_is_hidden_from_public_catalog_and_detail() -> None:
    repository = InMemoryDomainRepository()
    ensure_pricing_seed(repository=repository)
    service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=repository)

    created = service.create(WebsiteTemplateCreate.model_validate(_website_payload(catalog_visible=False)))
    service.publish(created["id"])
    unpublished = service.unpublish(created["id"], changed_by="studio", reason="unpublish_template")

    assert unpublished["templateStatus"] == "unpublished"
    assert unpublished["lastPublishedAt"] is not None
    assert unpublished["publishedSnapshotId"] is not None
    assert unpublished["statusHistory"][-1]["status"] == "unpublished"
    assert service.list_public() == []

    try:
        service.get_public_by_slug(created["slug"])
    except NuvlyError as exc:
        assert exc.status_code == 404
        assert exc.code == "PUBLIC_TEMPLATE_NOT_FOUND"
    else:
        raise AssertionError("Expected unpublished template to be unavailable publicly")
