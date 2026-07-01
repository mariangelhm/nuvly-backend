from __future__ import annotations

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from app.core.catalog import (
    PLAN_TIERS,
    VALID_PLAN_TIERS,
    VALID_PRODUCT_TYPES,
    VALID_TEMPLATE_CATEGORIES,
    VALID_VARIANT_LEVELS,
    infer_variant_level_from_plan_rules,
    normalize_variant_level,
    PlanTier,
    ProductType,
    TemplateCategoryCode,
    VariantLevel,
)
from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.pricing.repository import PricingRepository
from app.modules.pricing.schemas import PricingSeedStats
from app.modules.pricing.seed import COMPONENT_SEEDS, GENERAL_EXTRA_SEEDS, PLAN_SEEDS, TEMPLATE_CATEGORY_SEEDS, empty_seed_stats

logger = logging.getLogger(__name__)

PLANS_COLLECTION = "pricing_plans"
COMPONENTS_COLLECTION = "pricing_components"
TEMPLATE_CATEGORIES_COLLECTION = "template_categories"
GENERAL_EXTRAS = {item["code"]: item for item in GENERAL_EXTRA_SEEDS}

TIER_PRIORITY: dict[VariantLevel, int] = {"core": 0, "advanced": 1, "premium": 2}


def _normalize_plan_response_document(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized.setdefault("description", "")
    normalized.setdefault("currency", "CLP")
    normalized.setdefault("active", True)
    normalized.setdefault("sortOrder", 1)
    normalized.setdefault("basePriceMonthly", None)
    normalized.setdefault("basePriceYearly", None)
    normalized.setdefault("durationMonths", 12)
    return normalized


def _normalize_component_response_document(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized.setdefault("description", "")
    normalized.setdefault("active", True)
    normalized.setdefault("sortOrder", 1)
    normalized["categoryCode"] = (normalized.get("categoryCode") or normalized.get("componentCode") or "").strip()

    normalized_variants: List[Dict[str, Any]] = []
    for variant in normalized.get("variants") or []:
        normalized_variant = deepcopy(variant)
        included_in_plans = [tier for tier in (normalized_variant.get("includedInPlans") or []) if tier in VALID_PLAN_TIERS]
        can_be_extra_in_plans = [tier for tier in (normalized_variant.get("canBeExtraInPlans") or []) if tier in VALID_PLAN_TIERS]
        variant_code = (normalized_variant.get("variantCode") or "").strip()
        variant_name = (normalized_variant.get("name") or "").strip()
        if not variant_code or not variant_name:
            logger.warning(
                "Skipping malformed pricing variant without required identity fields | componentCode=%s | variant=%s",
                normalized.get("componentCode"),
                variant,
            )
            continue
        normalized_variant["variantCode"] = variant_code
        normalized_variant["name"] = variant_name
        normalized_variant.setdefault("description", "")
        normalized_variant.setdefault("active", True)
        normalized_variant["includedInPlans"] = included_in_plans
        normalized_variant["canBeExtraInPlans"] = can_be_extra_in_plans
        normalized_variant["variantTier"] = normalize_variant_level(
            normalized_variant.get("variantTier"),
            default=infer_variant_level_from_plan_rules(included_in_plans, can_be_extra_in_plans),
        )
        normalized_variant.setdefault("extraPrice", 0)
        normalized_variant.setdefault("currency", "CLP")
        normalized_variant.setdefault("sortOrder", 1)
        normalized_variants.append(normalized_variant)
    normalized["variants"] = sorted(normalized_variants, key=lambda item: item.get("sortOrder", 0))
    normalized["componentTier"] = normalize_variant_level(
        normalized.get("componentTier"),
        default=_infer_component_tier(normalized["variants"]),
    )
    return normalized


def _normalize_plan_document(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized["code"] = (normalized.get("code") or "").strip()
    if not normalized["code"]:
        raise NuvlyError("code no puede ser vacio.", 422, "INVALID_PLAN_CODE")
    if normalized.get("productType") not in VALID_PRODUCT_TYPES:
        raise NuvlyError("productType invalido.", 422, "INVALID_PRODUCT_TYPE")
    if normalized.get("tier") not in VALID_PLAN_TIERS:
        raise NuvlyError("tier invalido.", 422, "INVALID_PLAN_TIER")
    return normalized


def _normalize_variant_document(variant: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(variant)
    variant_code = (normalized.get("variantCode") or "").strip()
    if not variant_code:
        raise NuvlyError("variantCode no puede ser vacio.", 422, "INVALID_VARIANT_CODE")
    normalized["variantCode"] = variant_code
    if normalized.get("variantTier") not in VALID_VARIANT_LEVELS:
        raise NuvlyError("variantTier invalido.", 422, "INVALID_VARIANT_TIER")
    for tier in normalized.get("includedInPlans") or []:
        if tier not in VALID_PLAN_TIERS:
            raise NuvlyError(f"includedInPlans contiene tier invalido: {tier}", 422, "INVALID_INCLUDED_PLAN_TIER")
    for tier in normalized.get("canBeExtraInPlans") or []:
        if tier not in VALID_PLAN_TIERS:
            raise NuvlyError(f"canBeExtraInPlans contiene tier invalido: {tier}", 422, "INVALID_EXTRA_PLAN_TIER")
    included = set(normalized.get("includedInPlans") or [])
    extras = set(normalized.get("canBeExtraInPlans") or [])
    overlap = sorted(included & extras)
    if overlap:
        raise NuvlyError(
            f"Un plan no puede estar incluido y ser extra al mismo tiempo: {', '.join(overlap)}",
            422,
            "PLAN_TIER_OVERLAP_IN_VARIANT",
        )
    if extras and int(normalized.get("extraPrice") or 0) <= 0:
        raise NuvlyError(
            "extraPrice debe ser mayor a 0 cuando canBeExtraInPlans no esta vacio.",
            422,
            "EXTRA_PRICE_REQUIRED",
        )
    return normalized


def _normalize_component_document(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized["componentCode"] = (normalized.get("componentCode") or "").strip()
    normalized["categoryCode"] = (normalized.get("categoryCode") or "").strip()
    if not normalized["componentCode"]:
        raise NuvlyError("componentCode no puede ser vacio.", 422, "INVALID_COMPONENT_CODE")
    if not normalized["categoryCode"]:
        raise NuvlyError("categoryCode no puede ser vacio.", 422, "INVALID_COMPONENT_CATEGORY_CODE")
    if normalized.get("productType") not in VALID_PRODUCT_TYPES:
        raise NuvlyError("productType invalido.", 422, "INVALID_PRODUCT_TYPE")
    if normalized.get("componentTier") not in VALID_VARIANT_LEVELS:
        raise NuvlyError("componentTier invalido.", 422, "INVALID_COMPONENT_TIER")

    variants = normalized.get("variants")
    if not isinstance(variants, list) or not variants:
        raise NuvlyError("variants debe ser una lista no vacia.", 422, "INVALID_COMPONENT_VARIANTS")

    seen_variant_codes: set[str] = set()
    normalized_variants: List[Dict[str, Any]] = []
    for variant in variants:
        if not isinstance(variant, dict):
            raise NuvlyError("Cada variant debe ser un objeto.", 422, "INVALID_COMPONENT_VARIANT")
        normalized_variant = _normalize_variant_document(variant)
        if normalized_variant["variantCode"] in seen_variant_codes:
            raise NuvlyError(
                f"variantCode duplicado: {normalized_variant['variantCode']}",
                422,
                "DUPLICATED_VARIANT_CODE",
            )
        seen_variant_codes.add(normalized_variant["variantCode"])
        normalized_variants.append(normalized_variant)
    normalized["variants"] = sorted(normalized_variants, key=lambda item: item.get("sortOrder", 0))
    normalized["componentTier"] = normalize_variant_level(
        normalized.get("componentTier"),
        default=_infer_component_tier(normalized["variants"]),
    )
    return normalized


def _infer_component_tier(variants: List[Dict[str, Any]]) -> VariantLevel:
    if not variants:
        return "core"
    highest = max((variant.get("variantTier", "core") for variant in variants), key=lambda tier: TIER_PRIORITY.get(tier, 0))
    return normalize_variant_level(highest)


def is_tier_allowed_for_plan(tier: VariantLevel, plan_tier: PlanTier) -> bool:
    if plan_tier == "custom":
        return True
    if plan_tier == "essential":
        return tier == "core"
    if plan_tier == "plus":
        return tier in {"core", "advanced"}
    return True


def _normalize_template_category_document(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    if normalized.get("productType") not in VALID_PRODUCT_TYPES:
        raise NuvlyError("productType invalido.", 422, "INVALID_PRODUCT_TYPE")
    category_code = (normalized.get("categoryCode") or "").strip()
    if not category_code:
        raise NuvlyError("categoryCode no puede ser vacio.", 422, "INVALID_TEMPLATE_CATEGORY")
    if category_code not in VALID_TEMPLATE_CATEGORIES:
        raise NuvlyError("templateCategory invalido.", 422, "INVALID_TEMPLATE_CATEGORY")
    normalized["categoryCode"] = category_code
    normalized["allowedComponentCodes"] = sorted({code.strip() for code in normalized.get("allowedComponentCodes") or [] if code and code.strip()})
    return normalized


def _sync_seed_document(
    repository: PricingRepository,
    collection_name: str,
    lookup_filters: List[Dict[str, Any]],
    document: Dict[str, Any],
    duplicate_message: str,
    duplicate_code: str,
    not_found_message: str,
    not_found_code: str,
) -> str:
    existing: Dict[str, Any] | None = None
    for filters in lookup_filters:
        existing = repository.find_document(collection_name, filters)
        if existing:
            break

    if existing:
        synced_document = deepcopy(document)
        synced_document["id"] = existing.get("id", document["id"])
        synced_document["createdAt"] = existing.get("createdAt", document["createdAt"])
        repository.replace_document(
            collection_name,
            synced_document["id"],
            synced_document,
            not_found_message,
            not_found_code,
            duplicate_message,
            duplicate_code,
        )
        return "updated"

    repository.insert_document(
        collection_name,
        document,
        duplicate_message=duplicate_message,
        duplicate_code=duplicate_code,
    )
    return "inserted"


def build_variant_catalog_state(
    *,
    variant: Dict[str, Any],
    plan_tier: PlanTier,
    component_status: str,
) -> Dict[str, Any]:
    if component_status == "inactive":
        raw_status = "inactive"
        status = "inactive"
        lock_label = "Inactivo"
        locked = True
        lock_reason = "El componente padre está inactivo."
    elif component_status == "blocked_by_category":
        raw_status = "blocked_by_category"
        status = "blocked"
        lock_label = "No disponible para esta categoría"
        locked = True
        lock_reason = "El componente padre no está disponible para la categoría seleccionada."
    elif component_status == "blocked_by_plan":
        raw_status = "blocked_by_component_plan"
        status = "blocked"
        lock_label = "Componente no disponible para este plan"
        locked = True
        lock_reason = "El componente padre está bloqueado para este plan."
    elif not variant.get("active", True):
        raw_status = "inactive"
        status = "inactive"
        lock_label = "Inactivo"
        locked = True
        lock_reason = "Esta variante está inactiva."
    elif is_tier_allowed_for_plan(variant["variantTier"], plan_tier):
        raw_status = "included"
        status = "included"
        lock_label = ""
        locked = False
        lock_reason = ""
    else:
        plan_label = str(plan_tier).capitalize()
        raw_status = "blocked_by_plan"
        status = "blocked"
        lock_label = "No disponible para este plan"
        locked = True
        lock_reason = f"Esta variante {variant['variantTier']} no está disponible en {plan_label}."

    return {
        "rawStatus": raw_status,
        "status": status,
        "label": "Incluido" if status == "included" else ("Extra" if status == "extra" else lock_label),
        "lockLabel": lock_label,
        "locked": locked,
        "lockReason": lock_reason,
        "extraPrice": int(variant.get("extraPrice", 0) or 0) if status == "extra" else None,
    }


def build_component_catalog_state(
    *,
    component_tier: VariantLevel,
    plan_tier: PlanTier,
    component_allowed: bool,
    component_active: bool,
) -> Dict[str, Any]:
    if not component_active:
        return {
            "rawStatus": "inactive",
            "status": "inactive",
            "label": "Inactivo",
            "lockLabel": "Inactivo",
            "locked": True,
            "lockReason": "Este componente está inactivo.",
        }
    if not component_allowed:
        return {
            "rawStatus": "blocked_by_category",
            "status": "blocked",
            "label": "No disponible para esta categoría",
            "lockLabel": "No disponible para esta categoría",
            "locked": True,
            "lockReason": "Este componente no está disponible para la categoría seleccionada.",
        }
    if not is_tier_allowed_for_plan(component_tier, plan_tier):
        return {
            "rawStatus": "blocked_by_plan",
            "status": "blocked",
            "label": "No disponible para este plan",
            "lockLabel": "No disponible para este plan",
            "locked": True,
            "lockReason": "Este componente no está disponible para el plan seleccionado.",
        }
    return {
        "rawStatus": "included",
        "status": "included",
        "label": "Disponible",
        "lockLabel": "",
        "locked": False,
        "lockReason": "",
    }


class PricingPlanService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()

    def list(self, product_type: Optional[ProductType] = None, active: Optional[bool] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if product_type:
            filters["productType"] = product_type
        if active is not None:
            filters["active"] = active
        documents = self.repository.find_documents(
            PLANS_COLLECTION,
            filters,
            sort_fields=[("productType", 1), ("sortOrder", 1), ("name", 1)],
        )
        return [_normalize_plan_response_document(document) for document in documents]

    def get(self, plan_id: str) -> Dict[str, Any]:
        document = self.repository.find_document(PLANS_COLLECTION, {"id": plan_id})
        if not document:
            raise NuvlyError("Plan comercial no encontrado.", 404, "PRICING_PLAN_NOT_FOUND")
        return _normalize_plan_response_document(document)

    def find_by_tier(self, product_type: ProductType, tier: PlanTier) -> Dict[str, Any]:
        document = self.repository.find_document(PLANS_COLLECTION, {"productType": product_type, "tier": tier, "active": True})
        if not document:
            raise NuvlyError("Plan comercial no encontrado.", 404, "PRICING_PLAN_NOT_FOUND")
        return document

    def create(self, payload) -> Dict[str, Any]:
        now = utc_now_iso()
        document = _normalize_plan_document(payload.model_dump(mode="json"))
        document["id"] = new_id("plan")
        document["createdAt"] = now
        document["updatedAt"] = now
        return self.repository.insert_document(
            PLANS_COLLECTION,
            document,
            duplicate_message="Ya existe un plan comercial con ese code.",
            duplicate_code="DUPLICATED_PLAN_CODE",
        )

    def update(self, plan_id: str, payload) -> Dict[str, Any]:
        current = self.get(plan_id)
        document = _normalize_plan_document(payload.model_dump(mode="json"))
        document.update({"id": current["id"], "createdAt": current["createdAt"], "updatedAt": utc_now_iso()})
        return self.repository.replace_document(
            PLANS_COLLECTION,
            plan_id,
            document,
            "Plan comercial no encontrado.",
            "PRICING_PLAN_NOT_FOUND",
            "Ya existe un plan comercial con ese code.",
            "DUPLICATED_PLAN_CODE",
        )

    def update_active(self, plan_id: str, active: bool) -> Dict[str, Any]:
        return self.repository.update_document_fields(
            PLANS_COLLECTION,
            plan_id,
            {"active": active, "updatedAt": utc_now_iso()},
            "Plan comercial no encontrado.",
            "PRICING_PLAN_NOT_FOUND",
        )

    def ensure_seed(self) -> PricingSeedStats:
        stats = empty_seed_stats()
        now = utc_now_iso()
        for seed in PLAN_SEEDS:
            document = _normalize_plan_document(deepcopy(seed))
            document["createdAt"] = now
            document["updatedAt"] = now
            try:
                result = _sync_seed_document(
                    repository=self.repository,
                    collection_name=PLANS_COLLECTION,
                    lookup_filters=[{"id": seed["id"]}, {"code": seed["code"]}, {"productType": seed["productType"], "tier": seed["tier"]}],
                    document=document,
                    duplicate_message="Ya existe un plan comercial con ese code.",
                    duplicate_code="DUPLICATED_PLAN_CODE",
                    not_found_message="Plan comercial no encontrado.",
                    not_found_code="PRICING_PLAN_NOT_FOUND",
                )
                if result == "inserted":
                    stats.insertedPlans += 1
                else:
                    stats.skippedPlans += 1
            except NuvlyError as exc:
                if exc.code != "DUPLICATED_PLAN_CODE":
                    raise
                logger.warning("Skipping legacy duplicate pricing plan seed | id=%s code=%s", seed["id"], seed["code"])
                stats.skippedPlans += 1
        return stats


class TemplateCategoryService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()

    def list(self, product_type: Optional[ProductType] = None, active: Optional[bool] = None) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if product_type:
            filters["productType"] = product_type
        if active is not None:
            filters["active"] = active
        documents = self.repository.find_documents(
            TEMPLATE_CATEGORIES_COLLECTION,
            filters,
            sort_fields=[("productType", 1), ("sortOrder", 1), ("name", 1)],
        )
        return documents

    def get_by_code(self, product_type: ProductType, category_code: TemplateCategoryCode) -> Dict[str, Any]:
        document = self.repository.find_document(
            TEMPLATE_CATEGORIES_COLLECTION,
            {"productType": product_type, "categoryCode": category_code},
        )
        if not document:
            raise NuvlyError("Categoria de template no encontrada.", 404, "TEMPLATE_CATEGORY_NOT_FOUND")
        return document

    def create(self, payload) -> Dict[str, Any]:
        now = utc_now_iso()
        document = _normalize_template_category_document(payload.model_dump(mode="json"))
        document["id"] = new_id("cat")
        document["createdAt"] = now
        document["updatedAt"] = now
        return self.repository.insert_document(
            TEMPLATE_CATEGORIES_COLLECTION,
            document,
            duplicate_message="Ya existe una categoria con ese productType y categoryCode.",
            duplicate_code="DUPLICATED_TEMPLATE_CATEGORY",
        )

    def update(self, category_id: str, payload) -> Dict[str, Any]:
        current = self.repository.find_document(TEMPLATE_CATEGORIES_COLLECTION, {"id": category_id})
        if not current:
            raise NuvlyError("Categoria de template no encontrada.", 404, "TEMPLATE_CATEGORY_NOT_FOUND")
        document = _normalize_template_category_document(payload.model_dump(mode="json"))
        document.update({"id": current["id"], "createdAt": current["createdAt"], "updatedAt": utc_now_iso()})
        return self.repository.replace_document(
            TEMPLATE_CATEGORIES_COLLECTION,
            category_id,
            document,
            "Categoria de template no encontrada.",
            "TEMPLATE_CATEGORY_NOT_FOUND",
            "Ya existe una categoria con ese productType y categoryCode.",
            "DUPLICATED_TEMPLATE_CATEGORY",
        )

    def update_active(self, category_id: str, active: bool) -> Dict[str, Any]:
        return self.repository.update_document_fields(
            TEMPLATE_CATEGORIES_COLLECTION,
            category_id,
            {"active": active, "updatedAt": utc_now_iso()},
            "Categoria de template no encontrada.",
            "TEMPLATE_CATEGORY_NOT_FOUND",
        )

    def ensure_seed(self) -> PricingSeedStats:
        stats = empty_seed_stats()
        now = utc_now_iso()
        for seed in TEMPLATE_CATEGORY_SEEDS:
            document = _normalize_template_category_document(deepcopy(seed))
            document["createdAt"] = now
            document["updatedAt"] = now
            try:
                result = _sync_seed_document(
                    repository=self.repository,
                    collection_name=TEMPLATE_CATEGORIES_COLLECTION,
                    lookup_filters=[
                        {"id": seed["id"]},
                        {"productType": seed["productType"], "categoryCode": seed["categoryCode"]},
                    ],
                    document=document,
                    duplicate_message="Ya existe una categoria con ese productType y categoryCode.",
                    duplicate_code="DUPLICATED_TEMPLATE_CATEGORY",
                    not_found_message="Categoria de template no encontrada.",
                    not_found_code="TEMPLATE_CATEGORY_NOT_FOUND",
                )
                if result == "inserted":
                    stats.insertedTemplateCategories += 1
                else:
                    stats.skippedTemplateCategories += 1
            except NuvlyError as exc:
                if exc.code != "DUPLICATED_TEMPLATE_CATEGORY":
                    raise
                logger.warning(
                    "Skipping legacy duplicate template category seed | id=%s productType=%s categoryCode=%s",
                    seed["id"],
                    seed["productType"],
                    seed["categoryCode"],
                )
                stats.skippedTemplateCategories += 1
        return stats


class PricingComponentService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()

    def list(
        self,
        product_type: Optional[ProductType] = None,
        active: Optional[bool] = None,
        tier: Optional[PlanTier] = None,
        variant_level: Optional[VariantLevel] = None,
    ) -> List[Dict[str, Any]]:
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
        documents = [_normalize_component_response_document(document) for document in documents]
        if tier:
            documents = [
                document
                for document in documents
                if any(tier in variant.get("includedInPlans", []) or tier in variant.get("canBeExtraInPlans", []) for variant in document.get("variants", []))
            ]
        if variant_level:
            documents = [
                {
                    **document,
                    "variants": [variant for variant in document.get("variants", []) if variant.get("variantTier") == variant_level],
                }
                for document in documents
            ]
            documents = [document for document in documents if document["variants"]]
        return documents

    def get(self, component_id: str) -> Dict[str, Any]:
        document = self.repository.find_document(COMPONENTS_COLLECTION, {"id": component_id})
        if not document:
            raise NuvlyError("Componente comercial no encontrado.", 404, "PRICING_COMPONENT_NOT_FOUND")
        return _normalize_component_response_document(document)

    def get_by_component_code(self, product_type: ProductType, component_code: str) -> Dict[str, Any]:
        document = self.repository.find_document(COMPONENTS_COLLECTION, {"productType": product_type, "componentCode": component_code})
        if not document:
            raise NuvlyError("Componente comercial no encontrado.", 404, "PRICING_COMPONENT_NOT_FOUND")
        return _normalize_component_response_document(document)

    def find_variant(self, product_type: ProductType, component_code: str, variant_code: str) -> Dict[str, Any]:
        component = self.get_by_component_code(product_type, component_code)
        for variant in component.get("variants", []):
            if variant.get("variantCode") == variant_code:
                return {"component": component, "variant": variant}
        if isinstance(variant_code, str) and "-" in variant_code:
            fallback_code = variant_code.split("-", 1)[0].strip()
            if fallback_code:
                for variant in component.get("variants", []):
                    if variant.get("variantCode") == fallback_code:
                        return {"component": component, "variant": variant}
        raise NuvlyError("Variante comercial no encontrada.", 404, "PRICING_VARIANT_NOT_FOUND")

    def create(self, payload) -> Dict[str, Any]:
        now = utc_now_iso()
        document = _normalize_component_document(payload.model_dump(mode="json"))
        document["id"] = new_id("comp")
        document["createdAt"] = now
        document["updatedAt"] = now
        return self.repository.insert_document(
            COMPONENTS_COLLECTION,
            document,
            duplicate_message="Ya existe un componente comercial con ese componentCode.",
            duplicate_code="DUPLICATED_COMPONENT_CODE",
        )

    def update(self, component_id: str, payload) -> Dict[str, Any]:
        current = self.get(component_id)
        document = _normalize_component_document(payload.model_dump(mode="json"))
        document.update({"id": current["id"], "createdAt": current["createdAt"], "updatedAt": utc_now_iso()})
        return self.repository.replace_document(
            COMPONENTS_COLLECTION,
            component_id,
            document,
            "Componente comercial no encontrado.",
            "PRICING_COMPONENT_NOT_FOUND",
            "Ya existe un componente comercial con ese componentCode.",
            "DUPLICATED_COMPONENT_CODE",
        )

    def update_active(self, component_id: str, active: bool) -> Dict[str, Any]:
        return self.repository.update_document_fields(
            COMPONENTS_COLLECTION,
            component_id,
            {"active": active, "updatedAt": utc_now_iso()},
            "Componente comercial no encontrado.",
            "PRICING_COMPONENT_NOT_FOUND",
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
        return self.repository.replace_document(
            COMPONENTS_COLLECTION,
            component_id,
            updated,
            "Componente comercial no encontrado.",
            "PRICING_COMPONENT_NOT_FOUND",
            "Ya existe un componente comercial con ese componentCode.",
            "DUPLICATED_COMPONENT_CODE",
        )

    def update_variant(self, component_id: str, variant_code: str, payload) -> Dict[str, Any]:
        current = self.get(component_id)
        updated = deepcopy(current)
        normalized_variant = _normalize_variant_document(payload.model_dump(mode="json"))
        found = False
        for index, variant in enumerate(updated.get("variants", [])):
            if variant.get("variantCode") == variant_code:
                updated["variants"][index] = normalized_variant
                found = True
                break
        if not found:
            raise NuvlyError("Variante comercial no encontrada.", 404, "PRICING_VARIANT_NOT_FOUND")
        updated["updatedAt"] = utc_now_iso()
        updated = _normalize_component_document(updated)
        return self.repository.replace_document(
            COMPONENTS_COLLECTION,
            component_id,
            updated,
            "Componente comercial no encontrado.",
            "PRICING_COMPONENT_NOT_FOUND",
            "Ya existe un componente comercial con ese componentCode.",
            "DUPLICATED_COMPONENT_CODE",
        )

    def ensure_seed(self) -> PricingSeedStats:
        stats = empty_seed_stats()
        now = utc_now_iso()
        for seed in COMPONENT_SEEDS:
            document = _normalize_component_document(deepcopy(seed))
            document["createdAt"] = now
            document["updatedAt"] = now
            try:
                result = _sync_seed_document(
                    repository=self.repository,
                    collection_name=COMPONENTS_COLLECTION,
                    lookup_filters=[
                        {"id": seed["id"]},
                        {"productType": seed["productType"], "componentCode": seed["componentCode"]},
                    ],
                    document=document,
                    duplicate_message="Ya existe un componente comercial con ese componentCode.",
                    duplicate_code="DUPLICATED_COMPONENT_CODE",
                    not_found_message="Componente comercial no encontrado.",
                    not_found_code="PRICING_COMPONENT_NOT_FOUND",
                )
                if result == "inserted":
                    stats.insertedComponents += 1
                else:
                    stats.skippedComponents += 1
            except NuvlyError as exc:
                if exc.code != "DUPLICATED_COMPONENT_CODE":
                    raise
                logger.warning(
                    "Skipping legacy duplicate pricing component seed | id=%s productType=%s componentCode=%s",
                    seed["id"],
                    seed["productType"],
                    seed["componentCode"],
                )
                stats.skippedComponents += 1
        return stats


class CatalogService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()
        self.category_service = TemplateCategoryService(repository=self.repository)
        self.component_service = PricingComponentService(repository=self.repository)

    def list_template_categories(self, product_type: ProductType) -> List[Dict[str, Any]]:
        return self.category_service.list(product_type=product_type, active=True)

    def list_components_for_catalog(
        self,
        product_type: ProductType,
        template_category: TemplateCategoryCode,
        plan_tier: PlanTier,
    ) -> Dict[str, Any]:
        category = self.category_service.get_by_code(product_type, template_category)
        components = self.component_service.list(product_type=product_type)
        category_label = category.get("name", template_category)
        response_components: List[Dict[str, Any]] = []

        for component in components:
            component_allowed = True
            component_availability = build_component_catalog_state(
                component_tier=component["componentTier"],
                plan_tier=plan_tier,
                component_allowed=component_allowed,
                component_active=component.get("active", True),
            )
            variants = []
            for variant in component.get("variants", []):
                availability = build_variant_catalog_state(
                    variant=variant,
                    plan_tier=plan_tier,
                    component_status=component_availability["rawStatus"],
                )
                variants.append(
                    {
                        "variantCode": variant["variantCode"],
                        "name": variant["name"],
                        "description": variant.get("description", ""),
                        "variantTier": variant["variantTier"],
                        "sortOrder": int(variant.get("sortOrder", 1) or 1),
                        "status": availability["status"],
                        "lockLabel": availability["lockLabel"],
                        "label": availability["label"],
                        "active": variant.get("active", True),
                        "extraPrice": availability["extraPrice"],
                        "currency": variant.get("currency", "CLP"),
                        "locked": availability["locked"],
                        "lockReason": availability["lockReason"],
                    }
                )
            response_components.append(
                {
                    "componentCode": component["componentCode"],
                    "categoryCode": component.get("categoryCode", component["componentCode"]),
                    "categoryLabel": category_label,
                    "componentTier": component["componentTier"],
                    "name": component["name"],
                    "description": component.get("description", ""),
                    "active": component.get("active", True),
                    "sortOrder": int(component.get("sortOrder", 1) or 1),
                    "allowedByCategory": component_allowed,
                    "status": component_availability["status"],
                    "lockLabel": component_availability["lockLabel"],
                    "label": component_availability["label"],
                    "locked": component_availability["locked"],
                    "lockReason": component_availability["lockReason"],
                    "variants": variants,
                }
            )

        return {
            "productType": product_type,
            "templateCategory": template_category,
            "planTier": plan_tier,
            "components": response_components,
        }


class PricingSummaryService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()
        self.plan_service = PricingPlanService(repository=self.repository)
        self.component_service = PricingComponentService(repository=self.repository)

    @staticmethod
    def _build_matrix_cell(component: Dict[str, Any], variant: Dict[str, Any], tier: PlanTier) -> Dict[str, Any]:
        if not component.get("active", True) or not variant.get("active", True):
            return {"status": "blocked", "label": "Inactivo", "extraPrice": None}
        if not is_tier_allowed_for_plan(component["componentTier"], tier):
            return {"status": "blocked", "label": "No disponible", "extraPrice": None}
        if tier == "custom":
            return {"status": "included", "label": "Incluido", "extraPrice": None}
        if is_tier_allowed_for_plan(variant["variantTier"], tier):
            return {"status": "included", "label": "Incluido", "extraPrice": None}
        return {"status": "blocked", "label": "No disponible", "extraPrice": None}

    def build_summary(self, product_type: ProductType, include_inactive: bool = False, variant_level: Optional[VariantLevel] = None) -> Dict[str, Any]:
        plans = self.plan_service.list(product_type=product_type)
        components = self.component_service.list(product_type=product_type, active=None if include_inactive else True, variant_level=variant_level)

        tier_counters: Dict[str, Dict[str, int]] = {plan["tier"]: {"included": 0, "extra": 0, "blocked": 0} for plan in plans}
        summary_components: List[Dict[str, Any]] = []

        for component in components:
            summary_variants: List[Dict[str, Any]] = []
            for variant in component.get("variants", []):
                if not include_inactive and not variant.get("active", True):
                    continue
                matrix: Dict[str, Dict[str, Any]] = {}
                for plan in plans:
                    cell = self._build_matrix_cell(component, variant, plan["tier"])
                    matrix[plan["tier"]] = cell
                    tier_counters[plan["tier"]][cell["status"]] += 1
                summary_variants.append(
                    {
                        "variantCode": variant["variantCode"],
                        "name": variant["name"],
                        "description": variant.get("description", ""),
                        "variantTier": variant["variantTier"],
                        "active": variant.get("active", True),
                        "extraPrice": variant.get("extraPrice", 0),
                        "currency": variant.get("currency", "CLP"),
                        "matrix": {tier: matrix[tier] for tier in PLAN_TIERS if tier in matrix},
                    }
                )
            if not summary_variants:
                continue
            summary_components.append(
                {
                    "id": component["id"],
                    "componentCode": component["componentCode"],
                    "categoryCode": component["categoryCode"],
                    "name": component["name"],
                    "description": component.get("description", ""),
                    "active": component.get("active", True),
                    "variants": summary_variants,
                }
            )

        summary_plans = [
            {
                "id": plan["id"],
                "code": plan["code"],
                "tier": plan["tier"],
                "name": plan["name"],
                "basePrice": plan["basePrice"],
                "basePriceMonthly": plan.get("basePriceMonthly"),
                "basePriceYearly": plan.get("basePriceYearly"),
                "currency": plan["currency"],
                "includedCount": tier_counters[plan["tier"]]["included"],
                "extraCount": tier_counters[plan["tier"]]["extra"],
                "blockedCount": tier_counters[plan["tier"]]["blocked"],
            }
            for plan in plans
        ]
        return {"productType": product_type, "plans": summary_plans, "components": summary_components}


class PricingCalculatorService:
    def __init__(self, repository: PricingRepository | None = None):
        self.repository = repository or PricingRepository()
        self.plan_service = PricingPlanService(repository=self.repository)
        self.catalog_service = CatalogService(repository=self.repository)
        self.component_service = PricingComponentService(repository=self.repository)

    def calculate(self, payload) -> Dict[str, Any]:
        plan = self.plan_service.find_by_tier(payload.productType, payload.planTier)
        catalog = self.catalog_service.list_components_for_catalog(payload.productType, payload.templateCategory, payload.planTier)
        status_by_variant: Dict[tuple[str, str], Dict[str, Any]] = {}
        for component in catalog["components"]:
            for variant in component["variants"]:
                status_by_variant[(component["componentCode"], variant["variantCode"])] = variant

        component_extras_total = 0
        breakdown = [
            {
                "code": plan["code"],
                "label": plan["name"],
                "type": "plan",
                "amount": plan["basePrice"],
            }
        ]

        for selected in payload.selectedComponentExtras:
            variant = status_by_variant.get((selected.componentCode, selected.variantCode))
            if not variant:
                raise NuvlyError("Variante comercial no encontrada.", 404, "PRICING_VARIANT_NOT_FOUND")
            if variant["status"] != "extra":
                raise NuvlyError("La variante seleccionada no corresponde a un extra permitido.", 400, "VARIANT_NOT_ALLOWED_FOR_PLAN")
            extra_price = int(variant.get("extraPrice", 0))
            component_extras_total += extra_price
            breakdown.append(
                {
                    "code": f"{selected.componentCode}:{selected.variantCode}",
                    "label": f"{selected.componentCode} / {selected.variantCode}",
                    "type": "component_extra",
                    "amount": extra_price,
                }
            )

        extras_total = 0
        for extra_code in payload.selectedExtras:
            extra = GENERAL_EXTRAS.get(extra_code)
            if not extra:
                raise NuvlyError("Extra general no soportado.", 400, "INVALID_GENERAL_EXTRA")
            if extra.get("productType") and extra["productType"] != payload.productType:
                raise NuvlyError("Extra general no soportado para ese tipo de producto.", 400, "INVALID_GENERAL_EXTRA")
            extras_total += int(extra["price"])
            breakdown.append(
                {
                    "code": extra["code"],
                    "label": extra["name"],
                    "type": "general_extra",
                    "amount": int(extra["price"]),
                }
            )

        total = int(plan["basePrice"]) + component_extras_total + extras_total
        return {
            "currency": plan.get("currency", "CLP"),
            "basePrice": int(plan["basePrice"]),
            "componentExtrasTotal": component_extras_total,
            "extrasTotal": extras_total,
            "total": total,
            "breakdown": breakdown,
        }


def ensure_pricing_seed(repository: PricingRepository | None = None) -> PricingSeedStats:
    shared_repository = repository or PricingRepository()
    plan_stats = PricingPlanService(repository=shared_repository).ensure_seed()
    component_stats = PricingComponentService(repository=shared_repository).ensure_seed()
    category_stats = TemplateCategoryService(repository=shared_repository).ensure_seed()
    return PricingSeedStats(
        insertedPlans=plan_stats.insertedPlans,
        insertedComponents=component_stats.insertedComponents,
        insertedTemplateCategories=category_stats.insertedTemplateCategories,
        skippedPlans=plan_stats.skippedPlans,
        skippedComponents=component_stats.skippedComponents,
        skippedTemplateCategories=category_stats.skippedTemplateCategories,
    )
