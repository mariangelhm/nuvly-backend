"""Commercial availability validation, independent of project persistence."""

from typing import Any, Dict, List

from app.core.errors import NuvlyError
from app.modules.domain.repository import DomainRepository
from app.modules.pricing.service import (
    PricingComponentService,
    TemplateCategoryService,
    build_catalog_component_state,
    build_variant_catalog_state,
    is_paid_immersive_video,
)


def _collect_document_blocks(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    pages = document.get("pages") or []
    if pages:
        collected: List[Dict[str, Any]] = []
        for page in pages:
            collected.extend(block for block in page.get("blocks") or [] if block.get("enabled") is not False)
        return collected
    return [block for block in document.get("blocks") or [] if block.get("enabled") is not False]


def _resolve_block_component_code(block: Dict[str, Any]) -> str:
    component_code = (block.get("componentCode") or "").strip()
    if component_code:
        return component_code
    return (block.get("type") or "").strip()


def _resolve_block_variant_code(block: Dict[str, Any]) -> str:
    variant_code = (block.get("variantCode") or "").strip()
    if variant_code:
        return variant_code
    return (block.get("variant") or "").strip()


def _raise_invalid_commercial_selection(
    exc: NuvlyError,
    *,
    product_type: str,
    component_code: str,
    variant_code: str,
) -> None:
    if exc.code == "PRICING_COMPONENT_NOT_FOUND":
        raise NuvlyError(
            f"Componente comercial no encontrado. productType='{product_type}', componentCode='{component_code}'.",
            400,
            exc.code,
        ) from exc
    if exc.code == "PRICING_VARIANT_NOT_FOUND":
        raise NuvlyError(
            f"Variante comercial no encontrada. productType='{product_type}', componentCode='{component_code}', variantCode='{variant_code}'.",
            400,
            exc.code,
        ) from exc
    raise exc


def _normalize_selected_component_extras(extras: List[Dict[str, Any]] | None) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for extra in extras or []:
        component_code = (extra.get("componentCode") or "").strip()
        variant_code = (extra.get("variantCode") or "").strip()
        if not component_code or not variant_code:
            continue
        normalized.append(
            {
                "componentCode": component_code,
                "variantCode": variant_code,
                "extraPrice": int(extra.get("extraPrice") or 0),
            }
        )
    return normalized


class CommercialRulesService:
    def __init__(self, repository: DomainRepository):
        self.component_service = PricingComponentService(repository=repository)  # type: ignore[arg-type]
        self.category_service = TemplateCategoryService(repository=repository)  # type: ignore[arg-type]

    def validate_document(self, document: Dict[str, Any]) -> Dict[str, Any]:
        product_type = document.get("productType")
        plan_tier = document.get("planTier")
        template_category = document.get("templateCategory")

        if not product_type:
            raise NuvlyError("productType es obligatorio.", 422, "PRODUCT_TYPE_REQUIRED")
        if not plan_tier:
            raise NuvlyError("planTier es obligatorio.", 422, "PLAN_TIER_REQUIRED")
        if not template_category:
            raise NuvlyError("templateCategory es obligatorio.", 422, "TEMPLATE_CATEGORY_REQUIRED")

        if plan_tier == "custom":
            return self._validate_custom_document(document, product_type)

        self.category_service.get_by_code(product_type, template_category)
        selected_component_extras = {
            (item["componentCode"], item["variantCode"])
            for item in _normalize_selected_component_extras(document.get("selectedComponentExtras"))
        }

        for block in _collect_document_blocks(document):
            component_code = _resolve_block_component_code(block)
            variant_code = _resolve_block_variant_code(block)
            try:
                component_with_variant = self.component_service.find_variant(product_type, component_code, variant_code)
            except NuvlyError as exc:
                _raise_invalid_commercial_selection(
                    exc,
                    product_type=product_type,
                    component_code=component_code,
                    variant_code=variant_code,
                )
            component = component_with_variant["component"]
            variant = component_with_variant["variant"]
            component_availability = build_catalog_component_state(component, plan_tier)
            component_status = component_availability["rawStatus"]
            if component_status == "inactive":
                raise NuvlyError("El componente seleccionado está inactivo.", 422, "COMPONENT_INACTIVE")
            if component_status == "blocked_by_plan":
                raise NuvlyError(
                    f"El componente no esta permitido para el plan. productType='{product_type}', planTier='{plan_tier}', componentCode='{component_code}'.",
                    422,
                    "COMPONENT_NOT_ALLOWED_FOR_PLAN",
                )

            availability = build_variant_catalog_state(
                variant=variant,
                plan_tier=plan_tier,
                component_status=component_status,
                force_extra=is_paid_immersive_video(component_code, plan_tier, variant),
            )
            status = availability["rawStatus"]

            if status == "inactive":
                raise NuvlyError("La variante seleccionada esta inactiva.", 422, "VARIANT_INACTIVE")
            if status == "blocked_by_plan":
                raise NuvlyError(
                    f"La variante no esta permitida por el plan. productType='{product_type}', planTier='{plan_tier}', componentCode='{component_code}', variantCode='{variant_code}'.",
                    422,
                    "VARIANT_NOT_ALLOWED_FOR_PLAN",
                )
            if status == "extra" and (component_code, variant_code) not in selected_component_extras:
                raise NuvlyError(
                    f"La variante premium requiere ser seleccionada como extra. productType='{product_type}', planTier='{plan_tier}', componentCode='{component_code}', variantCode='{variant_code}'.",
                    422,
                    "PREMIUM_VARIANT_REQUIRES_EXTRA",
                )

        document.pop("commercialValidationSkipped", None)
        return document

    def _validate_custom_document(self, document: Dict[str, Any], product_type: str) -> Dict[str, Any]:
        commercial_validation_skipped = False
        for block in _collect_document_blocks(document):
            component_code = _resolve_block_component_code(block)
            variant_code = _resolve_block_variant_code(block)
            try:
                self.component_service.find_variant(product_type, component_code, variant_code)
                block.pop("customVariant", None)
            except NuvlyError as exc:
                if exc.code not in {"PRICING_VARIANT_NOT_FOUND", "PRICING_COMPONENT_NOT_FOUND"}:
                    raise
                block["customVariant"] = True
                commercial_validation_skipped = True

        if commercial_validation_skipped:
            document["commercialValidationSkipped"] = True
        else:
            document.pop("commercialValidationSkipped", None)
        return document
