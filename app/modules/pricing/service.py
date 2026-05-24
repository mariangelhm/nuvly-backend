from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from app.core.errors import NuvlyError
from app.modules.experiences.utils import new_id, utc_now_iso
from app.modules.pricing.repository import PricingRepository
from app.modules.pricing.schemas import PricingSeedStats
from app.modules.pricing.seed import COMPONENT_SEEDS, PLAN_SEEDS, empty_seed_stats

logger = logging.getLogger(__name__)

PLANS_COLLECTION = "pricing_plans"
COMPONENTS_COLLECTION = "pricing_components"
VALID_PLAN_TIERS = {"essential", "plus", "pro", "custom"}
VALID_PRODUCT_TYPES = {"website", "invitation"}
SUMMARY_PLAN_TIERS = ("essential", "plus", "pro", "custom")


def _normalize_plan_document(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized["code"] = (normalized.get("code") or "").strip()
    if not normalized["code"]:
        raise NuvlyError("code no puede ser vacio.", 422, "INVALID_PLAN_CODE")
    return normalized


def _normalize_component_document(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized["componentCode"] = (normalized.get("componentCode") or "").strip()
    if not normalized["componentCode"]:
        raise NuvlyError("componentCode no puede ser vacio.", 422, "INVALID_COMPONENT_CODE")

    variants = normalized.get("variants")
    if not isinstance(variants, list):
        raise NuvlyError("variants debe ser una lista.", 422, "INVALID_COMPONENT_VARIANTS")

    seen_variant_codes: set[str] = set()
    for variant in variants:
        if not isinstance(variant, dict):
            raise NuvlyError("Cada variant debe ser un objeto.", 422, "INVALID_COMPONENT_VARIANT")
        variant_code = (variant.get("variantCode") or "").strip()
        if not variant_code:
            raise NuvlyError("variantCode no puede ser vacio.", 422, "INVALID_VARIANT_CODE")
        if variant_code in seen_variant_codes:
            raise NuvlyError(f"variantCode duplicado: {variant_code}", 422, "DUPLICATED_VARIANT_CODE")
        seen_variant_codes.add(variant_code)
        variant["variantCode"] = variant_code

    included_in_plans = normalized.get("includedInPlans") or []
    can_be_extra_in_plans = normalized.get("canBeExtraInPlans") or []
    for tier in included_in_plans:
        if tier not in VALID_PLAN_TIERS:
            raise NuvlyError(f"includedInPlans contiene tier invalido: {tier}", 422, "INVALID_INCLUDED_PLAN_TIER")
    for tier in can_be_extra_in_plans:
        if tier not in VALID_PLAN_TIERS:
            raise NuvlyError(f"canBeExtraInPlans contiene tier invalido: {tier}", 422, "INVALID_EXTRA_PLAN_TIER")

    return normalized


class PricingPlanService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()

    def list(self, product_type: Optional[str] = None, active: Optional[bool] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if product_type:
            filters["productType"] = product_type
        if active is not None:
            filters["active"] = active
        return self.repository.find_documents(
            PLANS_COLLECTION,
            filters,
            sort_fields=[("productType", 1), ("sortOrder", 1), ("name", 1)],
        )

    def get(self, plan_id: str) -> Dict[str, Any]:
        document = self.repository.find_document(PLANS_COLLECTION, {"id": plan_id})
        if not document:
            raise NuvlyError("Plan comercial no encontrado.", 404, "PRICING_PLAN_NOT_FOUND")
        return document

    def create(self, payload) -> Dict[str, Any]:
        now = utc_now_iso()
        document = payload.model_dump(mode="json")
        document["id"] = new_id("plan")
        document["createdAt"] = now
        document["updatedAt"] = now
        document = _normalize_plan_document(document)
        logger.info("Pricing plan created | id=%s code=%s", document["id"], document["code"])
        return self.repository.insert_document(
            PLANS_COLLECTION,
            document,
            duplicate_message="Ya existe un plan comercial con ese code.",
            duplicate_code="DUPLICATED_PLAN_CODE",
        )

    def update(self, plan_id: str, payload) -> Dict[str, Any]:
        current = self.get(plan_id)
        document = payload.model_dump(mode="json")
        document.update(
            {
                "id": current["id"],
                "createdAt": current["createdAt"],
                "updatedAt": utc_now_iso(),
            }
        )
        document = _normalize_plan_document(document)
        logger.info("Pricing plan updated | id=%s code=%s", plan_id, document["code"])
        return self.repository.replace_document(
            PLANS_COLLECTION,
            plan_id,
            document,
            not_found_message="Plan comercial no encontrado.",
            not_found_code="PRICING_PLAN_NOT_FOUND",
            duplicate_message="Ya existe un plan comercial con ese code.",
            duplicate_code="DUPLICATED_PLAN_CODE",
        )

    def update_active(self, plan_id: str, active: bool) -> Dict[str, Any]:
        logger.info("Pricing plan active changed | id=%s active=%s", plan_id, active)
        return self.repository.update_document_fields(
            PLANS_COLLECTION,
            plan_id,
            {"active": active, "updatedAt": utc_now_iso()},
            not_found_message="Plan comercial no encontrado.",
            not_found_code="PRICING_PLAN_NOT_FOUND",
        )

    def ensure_seed(self) -> PricingSeedStats:
        stats = empty_seed_stats()
        now = utc_now_iso()
        for seed in PLAN_SEEDS:
            existing = self.repository.find_document(PLANS_COLLECTION, {"code": seed["code"]})
            if existing:
                stats.skippedPlans += 1
                continue
            document = deepcopy(seed)
            document["createdAt"] = now
            document["updatedAt"] = now
            self.repository.insert_document(
                PLANS_COLLECTION,
                document,
                duplicate_message="Ya existe un plan comercial con ese code.",
                duplicate_code="DUPLICATED_PLAN_CODE",
            )
            stats.insertedPlans += 1
        return stats


class PricingComponentService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()

    def list(self, product_type: Optional[str] = None, active: Optional[bool] = None, tier: Optional[str] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if product_type:
            filters["productType"] = product_type
        if active is not None:
            filters["active"] = active
        documents = self.repository.find_documents(
            COMPONENTS_COLLECTION,
            filters,
            sort_fields=[("productType", 1), ("sortOrder", 1), ("name", 1)],
        )
        if tier:
            documents = [
                document
                for document in documents
                if tier in document.get("includedInPlans", []) or tier in document.get("canBeExtraInPlans", [])
            ]
        return documents

    def get(self, component_id: str) -> Dict[str, Any]:
        document = self.repository.find_document(COMPONENTS_COLLECTION, {"id": component_id})
        if not document:
            raise NuvlyError("Componente comercial no encontrado.", 404, "PRICING_COMPONENT_NOT_FOUND")
        return document

    def create(self, payload) -> Dict[str, Any]:
        now = utc_now_iso()
        document = payload.model_dump(mode="json")
        document["id"] = new_id("comp")
        document["createdAt"] = now
        document["updatedAt"] = now
        document = _normalize_component_document(document)
        logger.info("Pricing component created | id=%s code=%s", document["id"], document["componentCode"])
        return self.repository.insert_document(
            COMPONENTS_COLLECTION,
            document,
            duplicate_message="Ya existe un componente comercial con ese componentCode.",
            duplicate_code="DUPLICATED_COMPONENT_CODE",
        )

    def update(self, component_id: str, payload) -> Dict[str, Any]:
        current = self.get(component_id)
        document = payload.model_dump(mode="json")
        document.update(
            {
                "id": current["id"],
                "createdAt": current["createdAt"],
                "updatedAt": utc_now_iso(),
            }
        )
        document = _normalize_component_document(document)
        logger.info("Pricing component updated | id=%s code=%s", component_id, document["componentCode"])
        return self.repository.replace_document(
            COMPONENTS_COLLECTION,
            component_id,
            document,
            not_found_message="Componente comercial no encontrado.",
            not_found_code="PRICING_COMPONENT_NOT_FOUND",
            duplicate_message="Ya existe un componente comercial con ese componentCode.",
            duplicate_code="DUPLICATED_COMPONENT_CODE",
        )

    def update_active(self, component_id: str, active: bool) -> Dict[str, Any]:
        logger.info("Pricing component active changed | id=%s active=%s", component_id, active)
        return self.repository.update_document_fields(
            COMPONENTS_COLLECTION,
            component_id,
            {"active": active, "updatedAt": utc_now_iso()},
            not_found_message="Componente comercial no encontrado.",
            not_found_code="PRICING_COMPONENT_NOT_FOUND",
        )

    def update_variant_active(self, component_id: str, variant_code: str, active: bool) -> Dict[str, Any]:
        current = self.get(component_id)
        updated = deepcopy(current)
        found = False
        for variant in updated.get("variants", []):
            if variant.get("variantCode") == variant_code:
                variant["active"] = active
                found = True
                break
        if not found:
            raise NuvlyError("Variante comercial no encontrada.", 404, "PRICING_VARIANT_NOT_FOUND")
        updated["updatedAt"] = utc_now_iso()
        updated = _normalize_component_document(updated)
        logger.info("Pricing variant active changed | id=%s variant=%s active=%s", component_id, variant_code, active)
        return self.repository.replace_document(
            COMPONENTS_COLLECTION,
            component_id,
            updated,
            not_found_message="Componente comercial no encontrado.",
            not_found_code="PRICING_COMPONENT_NOT_FOUND",
            duplicate_message="Ya existe un componente comercial con ese componentCode.",
            duplicate_code="DUPLICATED_COMPONENT_CODE",
        )

    def ensure_seed(self) -> PricingSeedStats:
        stats = empty_seed_stats()
        now = utc_now_iso()
        for seed in COMPONENT_SEEDS:
            existing = self.repository.find_document(COMPONENTS_COLLECTION, {"componentCode": seed["componentCode"]})
            if existing:
                stats.skippedComponents += 1
                continue
            document = deepcopy(seed)
            document["createdAt"] = now
            document["updatedAt"] = now
            document = _normalize_component_document(document)
            self.repository.insert_document(
                COMPONENTS_COLLECTION,
                document,
                duplicate_message="Ya existe un componente comercial con ese componentCode.",
                duplicate_code="DUPLICATED_COMPONENT_CODE",
            )
            stats.insertedComponents += 1
        return stats


class PricingSummaryService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()
        self.plan_service = PricingPlanService(repository=self.repository)
        self.component_service = PricingComponentService(repository=self.repository)

    @staticmethod
    def _build_matrix_cell(component: Dict[str, Any], tier: str) -> Dict[str, Any]:
        if tier in component.get("includedInPlans", []):
            return {"status": "included", "label": "Incluido", "extraPrice": None}
        if tier in component.get("canBeExtraInPlans", []):
            extra_price = component.get("extraPrice", 0)
            return {"status": "extra", "label": f"Extra ${extra_price}", "extraPrice": extra_price}
        return {"status": "blocked", "label": "No disponible", "extraPrice": None}

    def build_summary(self, product_type: str, include_inactive: bool = False) -> Dict[str, Any]:
        plans = self.plan_service.list(product_type=product_type)
        components = self.component_service.list(product_type=product_type, active=None if include_inactive else True)

        tier_counters: Dict[str, Dict[str, int]] = {
            plan["tier"]: {"included": 0, "extra": 0, "blocked": 0}
            for plan in plans
        }
        summary_components: List[Dict[str, Any]] = []

        for component in components:
            variants = component.get("variants", [])
            matrix: Dict[str, Dict[str, Any]] = {}
            for plan in plans:
                cell = self._build_matrix_cell(component, plan["tier"])
                matrix[plan["tier"]] = cell
                tier_counters[plan["tier"]][cell["status"]] += 1

            summary_components.append(
                {
                    "id": component["id"],
                    "componentCode": component["componentCode"],
                    "name": component.get("name", ""),
                    "description": component.get("description", ""),
                    "active": component.get("active", True),
                    "variantsCount": len(variants),
                    "activeVariantsCount": len([variant for variant in variants if variant.get("active") is True]),
                    "matrix": {tier: matrix[tier] for tier in SUMMARY_PLAN_TIERS if tier in matrix},
                }
            )

        summary_plans = [
            {
                "id": plan["id"],
                "code": plan["code"],
                "tier": plan["tier"],
                "name": plan["name"],
                "basePrice": plan["basePrice"],
                "currency": plan["currency"],
                "includedCount": tier_counters[plan["tier"]]["included"],
                "extraCount": tier_counters[plan["tier"]]["extra"],
                "blockedCount": tier_counters[plan["tier"]]["blocked"],
            }
            for plan in plans
        ]

        return {
            "productType": product_type,
            "plans": summary_plans,
            "components": summary_components,
        }


def ensure_pricing_seed(repository: PricingRepository | None = None) -> PricingSeedStats:
    shared_repository = repository or PricingRepository()
    plan_stats = PricingPlanService(repository=shared_repository).ensure_seed()
    component_stats = PricingComponentService(repository=shared_repository).ensure_seed()
    return PricingSeedStats(
        insertedPlans=plan_stats.insertedPlans,
        insertedComponents=component_stats.insertedComponents,
        skippedPlans=plan_stats.skippedPlans,
        skippedComponents=component_stats.skippedComponents,
    )
