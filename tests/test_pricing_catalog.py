from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from app.core.errors import NuvlyError
from app.modules.pricing.schemas import (
    PricingComponentActiveUpdate,
    PricingComponentCreate,
    PricingComponentUpdate,
    PricingPlanCreate,
    PricingPlanUpdate,
)
from app.modules.pricing.service import (
    COMPONENTS_COLLECTION,
    PLANS_COLLECTION,
    PricingComponentService,
    PricingPlanService,
    PricingSummaryService,
    ensure_pricing_seed,
)


class InMemoryPricingRepository:
    def __init__(self) -> None:
        self.collections: dict[str, list[dict[str, Any]]] = {}

    def database_name(self) -> str:
        return "in-memory"

    def insert_document(
        self,
        collection_name: str,
        document: Dict[str, Any],
        duplicate_message: str,
        duplicate_code: str,
    ) -> Dict[str, Any]:
        code_key = "code" if collection_name == PLANS_COLLECTION else "componentCode"
        for current in self.collections.get(collection_name, []):
            if current.get(code_key) == document.get(code_key):
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
        code_key = "code" if collection_name == PLANS_COLLECTION else "componentCode"
        documents = self.collections.get(collection_name, [])
        for current in documents:
            if current.get(code_key) == document.get(code_key) and current.get("id") != document_id:
                raise NuvlyError(duplicate_message, 409, duplicate_code)
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
        "componentCode": "hero_growth",
        "productType": "website",
        "name": "Hero Growth",
        "description": "Hero de crecimiento.",
        "active": True,
        "variants": [
            {
                "variantCode": "HG-01",
                "name": "Growth One",
                "description": "Variante principal.",
                "active": True,
            }
        ],
        "includedInPlans": ["plus", "pro"],
        "canBeExtraInPlans": ["essential"],
        "extraPrice": 4990,
        "currency": "CLP",
        "unit": "component",
        "sortOrder": 10,
    }


def test_pricing_seed_is_idempotent() -> None:
    repository = InMemoryPricingRepository()

    first = ensure_pricing_seed(repository=repository)
    second = ensure_pricing_seed(repository=repository)

    assert first.insertedPlans == 8
    assert first.insertedComponents == 34
    assert second.skippedPlans == 8
    assert second.skippedComponents == 34


def test_pricing_plan_crud_and_active_toggle() -> None:
    repository = InMemoryPricingRepository()
    service = PricingPlanService(repository=repository)

    created = service.create(PricingPlanCreate.model_validate(_plan_payload()))
    assert created["code"] == "website_growth"

    updated = service.update(
        created["id"],
        PricingPlanUpdate.model_validate({**_plan_payload(), "name": "Growth Updated"}),
    )
    assert updated["name"] == "Growth Updated"

    disabled = service.update_active(created["id"], False)
    assert disabled["active"] is False
    assert service.list(product_type="website", active=False)[0]["id"] == created["id"]


def test_pricing_component_list_can_filter_by_tier() -> None:
    repository = InMemoryPricingRepository()
    service = PricingComponentService(repository=repository)
    ensure_pricing_seed(repository=repository)

    essential = service.list(product_type="website", tier="essential")
    custom = service.list(product_type="invitation", tier="custom")

    assert any(component["componentCode"] == "hero_pro" for component in essential)
    assert any(component["componentCode"] == "ranking_top_5" for component in custom)


def test_pricing_component_crud_and_variant_active_toggle() -> None:
    repository = InMemoryPricingRepository()
    service = PricingComponentService(repository=repository)

    created = service.create(PricingComponentCreate.model_validate(_component_payload()))
    assert created["componentCode"] == "hero_growth"

    updated = service.update(
        created["id"],
        PricingComponentUpdate.model_validate({**_component_payload(), "name": "Hero Growth Updated"}),
    )
    assert updated["name"] == "Hero Growth Updated"

    disabled = service.update_active(created["id"], False)
    assert disabled["active"] is False

    variant_disabled = service.update_variant_active(created["id"], "HG-01", False)
    assert variant_disabled["variants"][0]["active"] is False


def test_pricing_component_rejects_duplicate_variant_codes() -> None:
    repository = InMemoryPricingRepository()
    service = PricingComponentService(repository=repository)
    payload = _component_payload()
    payload["variants"].append(deepcopy(payload["variants"][0]))

    try:
        service.create(PricingComponentCreate.model_validate(payload))
    except NuvlyError as exc:
        assert exc.code == "DUPLICATED_VARIANT_CODE"
    else:
        raise AssertionError("Expected DUPLICATED_VARIANT_CODE")


def test_pricing_component_rejects_invalid_extra_plan_tier() -> None:
    repository = InMemoryPricingRepository()
    service = PricingComponentService(repository=repository)
    payload = _component_payload()
    payload["canBeExtraInPlans"] = ["vip"]

    try:
        service.create(PricingComponentCreate.model_validate(payload))
    except Exception as exc:
        code = getattr(exc, "code", None)
        assert code == "INVALID_EXTRA_PLAN_TIER" or "literal_error" in str(exc)
    else:
        raise AssertionError("Expected invalid extra tier validation")


def test_pricing_summary_builds_commercial_matrix() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = PricingSummaryService(repository=repository)

    summary = service.build_summary(product_type="website")

    assert summary["productType"] == "website"
    assert summary["plans"][0]["tier"] == "essential"
    hero_pro = next(component for component in summary["components"] if component["componentCode"] == "hero_pro")
    assert hero_pro["matrix"]["essential"]["status"] == "extra"
    assert hero_pro["matrix"]["essential"]["label"] == "Extra $9990"
    assert hero_pro["matrix"]["plus"]["status"] == "included"
    assert hero_pro["matrix"]["plus"]["label"] == "Incluido"
    essential_plan = next(plan for plan in summary["plans"] if plan["tier"] == "essential")
    assert essential_plan["includedCount"] > 0
    assert essential_plan["extraCount"] > 0


def test_pricing_summary_excludes_inactive_components_by_default() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    component_service = PricingComponentService(repository=repository)
    summary_service = PricingSummaryService(repository=repository)
    hero_pro = next(component for component in component_service.list(product_type="website") if component["componentCode"] == "hero_pro")
    component_service.update_active(hero_pro["id"], False)

    summary_without_inactive = summary_service.build_summary(product_type="website")
    summary_with_inactive = summary_service.build_summary(product_type="website", include_inactive=True)

    assert all(component["componentCode"] != "hero_pro" for component in summary_without_inactive["components"])
    assert any(component["componentCode"] == "hero_pro" for component in summary_with_inactive["components"])
