from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from app.modules.domain.schemas import WebsiteTemplateCreate, WebsiteTemplateResponse, WebsiteTemplateUpdate
from app.modules.domain.services import TemplateService, WEBSITE_TEMPLATE_CONFIG


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


def _build_full_website_payload() -> Dict[str, Any]:
    block_types = [
        "navigation",
        "hero",
        "services",
        "projects",
        "beforeAfter",
        "process",
        "socialProof",
        "content",
        "leadForm",
        "footer",
    ]
    blocks = []
    for index, block_type in enumerate(block_types, start=1):
        blocks.append(
            {
                "id": f"blk_{block_type}",
                "type": block_type,
                "label": block_type.title(),
                "category": "marketing",
                "description": f"Block {block_type} description",
                "variant": f"{block_type}-variant-a",
                "enabled": True,
                "order": index,
                "props": {
                    "headline": f"Headline for {block_type}",
                    "image": f"/assets/web-pages/image-{index}.png",
                    "items": [{"title": f"Item {index}", "image": f"/assets/web-pages/image-{index}.png"}],
                },
                "settings": {
                    "spacing": {"top": 24 + index, "bottom": 24 + index},
                    "visibility": {"mobile": True, "desktop": True},
                },
            }
        )

    return {
        "title": "Studio Contract Template",
        "slug": "studio-contract-template",
        "experienceType": "web",
        "styles": {
            "themeId": "solarized-studio",
            "colors": {
                "background": "#f5efe6",
                "surface": "#fffdf9",
                "text": "#1e1b18",
                "accent": "#d97706",
            },
            "typography": {
                "headingFont": "Fraunces",
                "bodyFont": "Source Sans 3",
            },
            "effects": {
                "borderRadius": {"card": 20, "button": 999},
                "shadows": {"hero": "0 24px 60px rgba(30,27,24,0.12)"},
            },
        },
        "layout": {
            "sectionOrder": [block["id"] for block in blocks],
            "canvas": {"maxWidth": 1280, "gutter": 24},
        },
        "blocks": blocks,
        "seo": {
            "title": "Studio Contract Template",
            "description": "Website template round-trip contract.",
            "noIndex": True,
            "openGraph": {
                "image": "/assets/web-pages/image-1.png",
            },
        },
        "metadata": {
            "category": "landing",
            "style": "editorial",
            "purpose": "lead-generation",
            "coverImage": "/assets/web-pages/image-1.png",
            "badge": "Nuevo",
            "featured": True,
            "level": "premium",
            "basePrice": 149,
            "tags": ["agency", "portfolio", "services"],
            "catalogVisible": True,
            "previewVariant": "desktop",
            "previewStyle": {"frame": "browser", "accent": "#d97706"},
            "customFlag": "preserve-me",
        },
    }


def _response_json(document: Dict[str, Any]) -> Dict[str, Any]:
    return WebsiteTemplateResponse.model_validate(document).model_dump(mode="json")


def _assert_contract_subset(document: Dict[str, Any]) -> None:
    assert document["experienceType"] == "web"
    assert document["templateStatus"] == "draft"
    assert document["status"] == "draft"
    assert document["layout"]["sectionOrder"] == [block["id"] for block in document["blocks"]]
    assert document["metadata"]["previewVariant"] == "desktop"
    assert document["blocks"][0]["label"] == "Navigation"
    assert document["blocks"][0]["category"] == "marketing"
    assert document["blocks"][0]["description"] == "Block navigation description"
    assert document["blocks"][0]["props"]["image"] == "/assets/web-pages/image-1.png"


def test_website_template_contract_preserves_complete_shape() -> None:
    service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=InMemoryDomainRepository())

    created = service.create(WebsiteTemplateCreate.model_validate(_build_full_website_payload()))
    response = _response_json(created)

    _assert_contract_subset(response)
    assert response["styles"]["effects"]["borderRadius"]["card"] == 20
    assert response["metadata"]["customFlag"] == "preserve-me"
    assert "websiteData" not in response


def test_website_template_get_put_round_trip_is_lossless_for_editor_contract() -> None:
    service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=InMemoryDomainRepository())

    created = service.create(WebsiteTemplateCreate.model_validate(_build_full_website_payload()))
    first_read = _response_json(service.get(created["id"]))

    update_payload = WebsiteTemplateUpdate.model_validate(first_read)
    service.update(created["id"], update_payload)
    second_read = _response_json(service.get(created["id"]))

    first_without_updated_at = deepcopy(first_read)
    second_without_updated_at = deepcopy(second_read)
    first_without_updated_at.pop("updatedAt", None)
    second_without_updated_at.pop("updatedAt", None)

    assert second_without_updated_at == first_without_updated_at


def test_website_template_preserves_website_data_when_front_persists_it() -> None:
    service = TemplateService(WEBSITE_TEMPLATE_CONFIG, repository=InMemoryDomainRepository())
    payload = _build_full_website_payload()
    payload["websiteData"] = {
        "businessName": "Nuvly Studio",
        "industry": "creative-services",
        "contactEmail": "studio@nuvly.test",
        "customAnalytics": {"provider": "ga4"},
    }

    created = service.create(WebsiteTemplateCreate.model_validate(payload))
    response = _response_json(service.get(created["id"]))

    assert response["websiteData"] == payload["websiteData"]
