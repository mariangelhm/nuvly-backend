from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from app.core.errors import NuvlyError
from app.modules.pricing.schemas import (
    PricingCalculateRequest,
    PricingComponentResponse,
    PricingComponentCreate,
    PricingComponentUpdate,
    PricingPlanCreate,
    PricingPlanResponse,
    PricingPlanUpdate,
    PricingVariantUpdate,
    TemplateCategoryCreate,
)
from app.modules.pricing.service import (
    COMPONENTS_COLLECTION,
    PLANS_COLLECTION,
    TEMPLATE_CATEGORIES_COLLECTION,
    CatalogService,
    PricingCalculatorService,
    PricingComponentService,
    PricingPlanService,
    PricingSummaryService,
    TemplateCategoryService,
    ensure_pricing_seed,
)


class InMemoryPricingRepository:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}

    def collection(self, collection_name: str):
        return self.collections.setdefault(collection_name, [])

    def database_name(self) -> str:
        return "in-memory"

    def insert_document(
        self,
        collection_name: str,
        document: Dict[str, Any],
        duplicate_message: str,
        duplicate_code: str,
    ) -> Dict[str, Any]:
        if collection_name == PLANS_COLLECTION:
            for current in self.collections.get(collection_name, []):
                if current.get("code") == document.get("code"):
                    raise NuvlyError(duplicate_message, 409, duplicate_code)
        elif collection_name == COMPONENTS_COLLECTION:
            for current in self.collections.get(collection_name, []):
                if current.get("productType") == document.get("productType") and current.get("componentCode") == document.get("componentCode"):
                    raise NuvlyError(duplicate_message, 409, duplicate_code)
        elif collection_name == TEMPLATE_CATEGORIES_COLLECTION:
            for current in self.collections.get(collection_name, []):
                if current.get("productType") == document.get("productType") and current.get("categoryCode") == document.get("categoryCode"):
                    raise NuvlyError(duplicate_message, 409, duplicate_code)
        self.collections.setdefault(collection_name, []).append(deepcopy(document))
        return deepcopy(document)

    def replace_document(
        self,
        collection_name: str,
        document_id: str,
        document: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
        duplicate_message: str,
        duplicate_code: str,
    ) -> Dict[str, Any]:
        documents = self.collections.get(collection_name, [])
        for index, current in enumerate(documents):
            if current.get("id") == document_id:
                documents[index] = deepcopy(document)
                return deepcopy(document)
        raise NuvlyError(not_found_message, 404, not_found_code)

    def find_document(self, collection_name: str, filters: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for document in self.collections.get(collection_name, []):
            if self._matches(document, filters):
                return deepcopy(document)
        return None

    def find_documents(
        self,
        collection_name: str,
        filters: Dict[str, Any],
        limit: int = 100,
        skip: int = 0,
        sort_fields: Optional[List[tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        documents = [deepcopy(document) for document in self.collections.get(collection_name, []) if self._matches(document, filters)]
        if sort_fields:
            for field, direction in reversed(sort_fields):
                documents.sort(key=lambda item: item.get(field), reverse=direction == -1)
        documents = documents[skip:]
        if limit > 0:
            documents = documents[:limit]
        return documents

    def update_document_fields(
        self,
        collection_name: str,
        document_id: str,
        updates: Dict[str, Any],
        not_found_message: str,
        not_found_code: str,
    ) -> Dict[str, Any]:
        documents = self.collections.get(collection_name, [])
        for index, current in enumerate(documents):
            if current.get("id") == document_id:
                updated = deepcopy(current)
                updated.update(deepcopy(updates))
                documents[index] = updated
                return deepcopy(updated)
        raise NuvlyError(not_found_message, 404, not_found_code)

    @staticmethod
    def _matches(document: Dict[str, Any], filters: Dict[str, Any]) -> bool:
        for key, expected in filters.items():
            if document.get(key) != expected:
                return False
        return True


def _plan_payload() -> Dict[str, Any]:
    return {
        "code": "website_growth",
        "productType": "website",
        "tier": "plus",
        "name": "Growth",
        "description": "Plan de crecimiento.",
        "basePrice": 29990,
        "durationMonths": 6,
        "currency": "CLP",
        "active": True,
        "sortOrder": 10,
    }


def _component_payload() -> Dict[str, Any]:
    return {
        "componentCode": "hero",
        "productType": "website",
        "categoryCode": "hero",
        "name": "Hero",
        "description": "Hero comercial.",
        "active": True,
        "variants": [
            {
                "variantCode": "H1",
                "name": "Hero core",
                "description": "Core",
                "variantTier": "core",
                "active": True,
                "includedInPlans": ["essential", "plus", "pro"],
                "canBeExtraInPlans": [],
                "extraPrice": 0,
                "currency": "CLP",
                "sortOrder": 1,
            },
            {
                "variantCode": "H8",
                "name": "Hero premium",
                "description": "Premium",
                "variantTier": "premium",
                "active": True,
                "includedInPlans": ["pro"],
                "canBeExtraInPlans": ["plus"],
                "extraPrice": 3990,
                "currency": "CLP",
                "sortOrder": 8,
            },
        ],
        "sortOrder": 10,
    }


def _template_category_payload() -> Dict[str, Any]:
    return {
        "productType": "website",
        "categoryCode": "construction",
        "name": "Construcción",
        "description": "Templates para constructoras.",
        "active": True,
        "sortOrder": 1,
        "allowedComponentCodes": ["hero", "navigation", "content"],
    }


def test_pricing_seed_is_idempotent() -> None:
    repository = InMemoryPricingRepository()

    first = ensure_pricing_seed(repository=repository)
    second = ensure_pricing_seed(repository=repository)

    assert first.insertedPlans == 8
    assert first.insertedComponents > 0
    assert first.insertedTemplateCategories == 14
    assert second.skippedPlans == 8
    assert second.skippedComponents == first.insertedComponents
    assert second.skippedTemplateCategories == 14


def test_pricing_plan_crud_and_active_toggle() -> None:
    repository = InMemoryPricingRepository()
    service = PricingPlanService(repository=repository)

    created = service.create(PricingPlanCreate.model_validate(_plan_payload()))
    updated = service.update(created["id"], PricingPlanUpdate.model_validate({**_plan_payload(), "name": "Growth Updated"}))
    disabled = service.update_active(created["id"], False)

    assert created["code"] == "website_growth"
    assert updated["name"] == "Growth Updated"
    assert disabled["active"] is False


def test_template_category_crud_and_active_toggle() -> None:
    repository = InMemoryPricingRepository()
    service = TemplateCategoryService(repository=repository)

    created = service.create(TemplateCategoryCreate.model_validate(_template_category_payload()))
    updated = service.update(created["id"], TemplateCategoryCreate.model_validate({**_template_category_payload(), "name": "Construcción Pro"}))
    disabled = service.update_active(created["id"], False)

    assert created["categoryCode"] == "construction"
    assert updated["name"] == "Construcción Pro"
    assert disabled["active"] is False


def test_pricing_component_crud_and_variant_active_toggle() -> None:
    repository = InMemoryPricingRepository()
    service = PricingComponentService(repository=repository)

    created = service.create(PricingComponentCreate.model_validate(_component_payload()))
    updated = service.update(created["id"], PricingComponentUpdate.model_validate({**_component_payload(), "name": "Hero Updated"}))
    variant_disabled = service.update_variant_active(created["id"], "H8", False)

    assert created["componentCode"] == "hero"
    assert updated["name"] == "Hero Updated"
    assert variant_disabled["variants"][1]["active"] is False


def test_pricing_component_updates_single_variant() -> None:
    repository = InMemoryPricingRepository()
    service = PricingComponentService(repository=repository)

    created = service.create(PricingComponentCreate.model_validate(_component_payload()))
    updated = service.update_variant(
        created["id"],
        "H8",
        PricingVariantUpdate.model_validate(
            {
                "variantCode": "H8",
                "name": "Hero premium updated",
                "description": "Premium updated",
                "variantTier": "premium",
                "active": True,
                "includedInPlans": ["pro"],
                "canBeExtraInPlans": ["plus"],
                "extraPrice": 4990,
                "currency": "CLP",
                "sortOrder": 9,
            }
        ),
    )

    variant = next(item for item in updated["variants"] if item["variantCode"] == "H8")
    assert variant["name"] == "Hero premium updated"
    assert variant["extraPrice"] == 4990


def test_pricing_component_rejects_variant_plan_overlap() -> None:
    repository = InMemoryPricingRepository()
    service = PricingComponentService(repository=repository)
    payload = _component_payload()
    payload["variants"][1]["includedInPlans"] = ["plus", "pro"]
    payload["variants"][1]["canBeExtraInPlans"] = ["plus"]

    try:
        service.create(PricingComponentCreate.model_validate(payload))
    except NuvlyError as exc:
        assert exc.code == "PLAN_TIER_OVERLAP_IN_VARIANT"
    else:
        raise AssertionError("Expected PLAN_TIER_OVERLAP_IN_VARIANT")


def test_pricing_component_rejects_extra_without_price() -> None:
    repository = InMemoryPricingRepository()
    service = PricingComponentService(repository=repository)
    payload = _component_payload()
    payload["variants"][1]["extraPrice"] = 0

    try:
        service.create(PricingComponentCreate.model_validate(payload))
    except NuvlyError as exc:
        assert exc.code == "EXTRA_PRICE_REQUIRED"
    else:
        raise AssertionError("Expected EXTRA_PRICE_REQUIRED")


def test_catalog_components_calculates_variant_statuses() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = CatalogService(repository=repository)

    response = service.list_components_for_catalog("website", "construction", "plus")

    hero = next(component for component in response["components"] if component["componentCode"] == "hero")
    h1 = next(variant for variant in hero["variants"] if variant["variantCode"] == "hero-a")
    h8 = next(variant for variant in hero["variants"] if variant["variantCode"] == "hero-premium-video")

    assert response["templateCategory"] == "construction"
    assert h1["status"] == "included"
    assert h8["status"] == "extra"


def test_catalog_components_hides_inactive_variants() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    component_service = PricingComponentService(repository=repository)
    catalog_service = CatalogService(repository=repository)

    hero = next(component for component in component_service.list(product_type="website") if component["componentCode"] == "hero")
    component_service.update_variant_active(hero["id"], "hero-premium-video", False)

    response = catalog_service.list_components_for_catalog("website", "construction", "plus")
    hero_response = next(component for component in response["components"] if component["componentCode"] == "hero")

    assert all(variant["variantCode"] != "hero-premium-video" for variant in hero_response["variants"])


def test_pricing_summary_builds_matrix_per_variant() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = PricingSummaryService(repository=repository)

    summary = service.build_summary(product_type="website")
    hero = next(component for component in summary["components"] if component["componentCode"] == "hero")
    premium_variant = next(variant for variant in hero["variants"] if variant["variantCode"] == "hero-premium-video")

    assert premium_variant["variantTier"] == "premium"
    assert premium_variant["matrix"]["essential"]["status"] == "blocked"
    assert premium_variant["matrix"]["plus"]["status"] == "extra"
    assert premium_variant["matrix"]["pro"]["status"] == "included"


def test_pricing_component_list_normalizes_legacy_documents() -> None:
    repository = InMemoryPricingRepository()
    repository.collections[COMPONENTS_COLLECTION] = [
        {
            "id": "comp_legacy",
            "componentCode": "hero",
            "productType": "website",
            "name": "Hero",
            "variants": [
                {
                    "variantCode": "hero-basic",
                    "name": "Hero basic",
                    "variantTier": "core",
                }
            ],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    ]
    service = PricingComponentService(repository=repository)

    component = service.list(product_type="website")[0]
    validated = PricingComponentResponse.model_validate(component)

    assert validated.categoryCode == "hero"
    assert validated.sortOrder == 1
    assert validated.variants[0].currency == "CLP"
    assert validated.variants[0].sortOrder == 1


def test_pricing_component_list_infers_missing_variant_tier_from_legacy_rules() -> None:
    repository = InMemoryPricingRepository()
    repository.collections[COMPONENTS_COLLECTION] = [
        {
            "id": "comp_legacy",
            "componentCode": "hero",
            "productType": "website",
            "categoryCode": "hero",
            "name": "Hero",
            "variants": [
                {
                    "variantCode": "hero-premium-video",
                    "name": "Hero Premium Video",
                    "includedInPlans": ["pro"],
                    "canBeExtraInPlans": ["plus"],
                }
            ],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    ]
    service = PricingComponentService(repository=repository)

    component = service.list(product_type="website")[0]
    validated = PricingComponentResponse.model_validate(component)

    assert validated.variants[0].variantTier == "premium"


def test_pricing_summary_supports_legacy_component_documents() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    repository.collections[COMPONENTS_COLLECTION].append(
        {
            "id": "comp_legacy",
            "componentCode": "legacy-gallery",
            "productType": "website",
            "name": "Legacy Gallery",
            "active": True,
            "sortOrder": 999,
            "variants": [
                {
                    "variantCode": "legacy-gallery-basic",
                    "name": "Legacy Gallery Basic",
                    "variantTier": "core",
                    "includedInPlans": ["essential", "plus", "pro"],
                }
            ],
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    )
    service = PricingSummaryService(repository=repository)

    summary = service.build_summary(product_type="website")
    legacy = next(component for component in summary["components"] if component["componentCode"] == "legacy-gallery")

    assert legacy["categoryCode"] == "legacy-gallery"
    assert legacy["variants"][0]["matrix"]["plus"]["status"] == "included"


def test_pricing_seed_skips_component_when_legacy_id_already_exists() -> None:
    repository = InMemoryPricingRepository()
    repository.collections[COMPONENTS_COLLECTION] = [
        {
            "id": "comp_001",
            "componentCode": "legacy_navigation",
            "productType": "website",
            "categoryCode": "legacy_navigation",
            "name": "Legacy Navigation",
            "description": "",
            "active": True,
            "variants": [
                {
                    "variantCode": "legacy-navigation-a",
                    "name": "Legacy Navigation A",
                    "variantTier": "core",
                    "includedInPlans": ["essential", "plus", "pro"],
                    "canBeExtraInPlans": [],
                    "extraPrice": 0,
                    "currency": "CLP",
                    "sortOrder": 1,
                }
            ],
            "sortOrder": 1,
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    ]

    stats = PricingComponentService(repository=repository).ensure_seed()

    assert stats.skippedComponents >= 1
    assert repository.collections[COMPONENTS_COLLECTION][0]["componentCode"] == "legacy_navigation"


def test_pricing_plan_list_normalizes_legacy_documents() -> None:
    repository = InMemoryPricingRepository()
    repository.collections[PLANS_COLLECTION] = [
        {
            "id": "plan_legacy",
            "code": "website_legacy",
            "productType": "website",
            "tier": "plus",
            "name": "Legacy plan",
            "basePrice": 10000,
            "createdAt": "2026-01-01T00:00:00Z",
            "updatedAt": "2026-01-01T00:00:00Z",
        }
    ]
    service = PricingPlanService(repository=repository)

    plan = service.list(product_type="website")[0]
    validated = PricingPlanResponse.model_validate(plan)

    assert validated.currency == "CLP"
    assert validated.durationMonths == 12
    assert validated.sortOrder == 1


def test_pricing_calculate_sums_plan_component_extras_and_general_extras() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = PricingCalculatorService(repository=repository)

    response = service.calculate(
        PricingCalculateRequest(
            productType="website",
            planTier="plus",
            templateCategory="construction",
            selectedComponentExtras=[{"componentCode": "hero", "variantCode": "hero-premium-video"}],
            selectedExtras=["custom_domain"],
            durationMonths=12,
        )
    )

    assert response["currency"] == "CLP"
    assert response["componentExtrasTotal"] == 3990
    assert response["extrasTotal"] == 1990
    assert response["total"] == response["basePrice"] + 3990 + 1990
