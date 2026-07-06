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
        "componentTier": "core",
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
    h1 = next(variant for variant in hero["variants"] if variant["variantCode"] == "H1")
    h8 = next(variant for variant in hero["variants"] if variant["variantCode"] == "H8")

    assert response["templateCategory"] == "construction"
    assert hero["name"] == "Hero Dinámico"
    assert hero["description"] == "Sección principal de alto impacto."
    assert hero["categoryCode"] == "hero"
    assert hero["categoryLabel"] == "Construcción"
    assert hero["componentTier"] == "core"
    assert hero["active"] is True
    assert hero["allowedByCategory"] is True
    assert hero["status"] == "included"
    assert hero["label"] == "Disponible"
    assert hero["lockLabel"] == ""
    assert hero["locked"] is False
    assert hero["sortOrder"] == 2
    assert h1["status"] == "included"
    assert h1["label"] == "Incluido"
    assert h1["lockLabel"] == ""
    assert h1["locked"] is False
    assert h1["sortOrder"] == 1
    assert h8["status"] == "blocked"
    assert h8["label"] == "No disponible para este plan"
    assert h8["lockLabel"] == "No disponible para este plan"
    assert h8["locked"] is True


def test_catalog_components_includes_modern_navigation_premium_variants() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = CatalogService(repository=repository)

    response = service.list_components_for_catalog("website", "construction", "pro")

    navigation = next(component for component in response["components"] if component["componentCode"] == "navigation")
    variants_by_code = {variant["variantCode"]: variant for variant in navigation["variants"]}

    expected = {
        "MP1-Organic-Premium-Frame": (
            "Marco orgánico premium",
            "Navegación premium superpuesta con frame orgánico.",
        ),
        "MP2-Breadcrumb-Multipage": (
            "Menú multipágina con breadcrumb",
            "Navegación premium con breadcrumb para sitios multipágina.",
        ),
        "MP3-Organic-Login": (
            "Menú orgánico con inicio de sesión",
            "Navegación premium orgánica con acceso de usuario.",
        ),
        "MP4-Musicians-Right-Drawer": (
            "Menú plus lateral derecho",
            "Navegación premium para músicos con menú fijo a la derecha y drawer lateral derecho en mobile.",
        ),
    }

    for variant_code, (name, description) in expected.items():
        variant = variants_by_code[variant_code]
        assert variant["name"] == name
        assert variant["description"] == description
        assert variant["variantTier"] == "premium"
        assert variant["status"] == "included"
        assert variant["locked"] is False
        assert variant["lockLabel"] == ""
        assert variant["lockReason"] == ""
        assert variant["extraPrice"] is None
        assert variant["currency"] == "CLP"
        assert variant["active"] is True


def test_catalog_components_includes_modern_website_template_variants() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = CatalogService(repository=repository)

    response = service.list_components_for_catalog("website", "beauty", "pro")
    components_by_code = {component["componentCode"]: component for component in response["components"]}

    expected_variants = {
        "navigation": ["ME1-Overlay-Nav", "ME2-Split-Nav", "ME3-Minimal-Sticky", "MA1-Kinetic-Typography-Reveal", "MA2-Neomorphic-Inverted", "MA3-Distorted-Mesh-Gradient", "MP1-Organic-Premium-Frame", "MP2-Breadcrumb-Multipage", "MP3-Organic-Login", "MP4-Musicians-Right-Drawer"],
        "hero": ["HE1-Modern-Impact", "HE2-Split-Screen", "HE3-Parallax-Layered", "HA1-Multi-Layer-Kinetic-Parallax", "HA2-Zoom-On-Scroll-Reveal", "HA3-Immersion-Typography-Tunnel", "HP1-Editorial-Video-Upload", "HP2-Editorial-Video-Youtube", "HP3-Cinematic-Image-Frame"],
        "services": ["SE1-Glass-Card", "SE2-Blueprint-Style", "SE3-Number-Focus", "SA1-Neomorphic-Hover-Depth", "SA2-Kinetic-Icon-Animation", "SA3-Floating-3D-Layers", "SA4-Bento-Kinetic-Stack", "SP1-Dynamic-Path-Cards", "SP2-Premium-Circle-Link-Canvas"],
        "leadForm": ["LFP1-Multi-Step", "LFP2-Map-Lead", "LFP3-Conversational", "LFP4-Gamified-Cost-Calculator", "LFP5-Step-by-Step-Modal-Reveal"],
        "content": ["COE1-Focus-Reveal", "COA1-Data-Wall", "COA2-Interactive-Blueprint-Glossary"],
        "projects": ["PE1-Masonry-Grid", "PE2-Parallax-Tiles-Reveal", "PE3-Interactive-Tabs", "PA1-Infinite-Draggable-Grid", "PA2-Full-Width-Slider", "PA3-Liquid-Distortion-Hover", "PP1-Smart-Sync-Reader"],
        "beforeAfter": ["BAE1-Slider-Classic", "BAE2-Fade-Interaction", "BAE3-Diagonal-Split", "BAA1-Lens-Magnifier-Effect", "BAA2-3D-Card-Flip", "BAP1-Curtain-Reveal-Parallax"],
        "process": ["TE1-Vertical-Snake", "TE2-Horizontal-Steps", "TA1-Circular-Orbit", "TP1-Blueprint-Scanner"],
        "socialProof": ["PSE1-Infinite-Marquee", "PSE2-Quote-Bubble", "PSA1-Editorial-Float", "PSP1-Auto-Scroll-Rating-Marquee", "PSP2-Video-Grid"],
        "footer": ["FTE1-Industrial-Dark", "FTE2-Minimal-Clean", "FTE3-Column-Big-Text", "FTA1-Particle-Background-Shader", "FTA2-Kinetic-Typo-Marquee", "FTA3-Reveal-on-Scroll-Total", "FTP1-Corporate-Network-Hub"],
        "whatsapp_floating": ["WAE1-Floating-Button", "WAE2-Floating-With-Label", "WAA1-Footer-Docked-Help"],
        "branches": ["SUP1-Interactive-Location-Grid"],
        "immersiveVideo": ["VIP1-Cinematic-Theater-Modal"],
        "youtubeVideo": ["YTE1-Embedded-Youtube"],
        "blankCanvas": ["BCE1-Blank-Canvas"],
        "maintainer": ["MTP1-Configurable-Maintainer"],
    }

    for component_code, variant_codes in expected_variants.items():
        component = components_by_code[component_code]
        variants_by_code = {variant["variantCode"]: variant for variant in component["variants"]}
        for variant_code in variant_codes:
            assert variant_code in variants_by_code
            variant = variants_by_code[variant_code]
            assert variant["status"] == "included"
            assert variant["locked"] is False
            assert variant["active"] is True
            assert variant["extraPrice"] is None


def test_catalog_components_marks_inactive_variants_as_inactive() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    component_service = PricingComponentService(repository=repository)
    catalog_service = CatalogService(repository=repository)

    hero = next(component for component in component_service.list(product_type="website") if component["componentCode"] == "hero")
    component_service.update_variant_active(hero["id"], "H8", False)

    response = catalog_service.list_components_for_catalog("website", "construction", "plus")
    hero_response = next(component for component in response["components"] if component["componentCode"] == "hero")
    premium_variant = next(variant for variant in hero_response["variants"] if variant["variantCode"] == "H8")

    assert premium_variant["status"] == "inactive"
    assert premium_variant["label"] == "Inactivo"
    assert premium_variant["lockLabel"] == "Inactivo"
    assert premium_variant["locked"] is True


def test_catalog_components_marks_blocked_variants_by_plan() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = CatalogService(repository=repository)

    by_plan = service.list_components_for_catalog("website", "construction", "essential")
    hero = next(component for component in by_plan["components"] if component["componentCode"] == "hero")
    premium = next(variant for variant in hero["variants"] if variant["variantCode"] == "H8")
    lead_form = next(component for component in by_plan["components"] if component["componentCode"] == "leadForm")
    lead_form_variant = lead_form["variants"][0]

    by_category = service.list_components_for_catalog("website", "beauty", "plus")
    projects = next(component for component in by_category["components"] if component["componentCode"] == "projects")
    project_variant = projects["variants"][0]
    branches = next(component for component in by_plan["components"] if component["componentCode"] == "branches")
    branches_variant = branches["variants"][0]

    assert premium["status"] == "blocked"
    assert premium["label"] == "No disponible para este plan"
    assert premium["lockLabel"] == "No disponible para este plan"
    assert premium["locked"] is True
    assert premium["lockReason"] == "Esta variante premium no está disponible en Essential."
    assert lead_form["status"] == "blocked"
    assert lead_form["locked"] is True
    assert lead_form_variant["status"] == "blocked"
    assert lead_form_variant["label"] == "Componente no disponible para este plan"
    assert lead_form_variant["lockLabel"] == "Componente no disponible para este plan"
    assert branches["status"] == "blocked"
    assert branches["label"] == "No disponible para este plan"
    assert branches["lockLabel"] == "No disponible para este plan"
    assert branches["locked"] is True
    assert branches["lockReason"] == "Este componente no está disponible para el plan seleccionado."
    assert branches_variant["status"] == "blocked"
    assert projects["allowedByCategory"] is True
    assert projects["status"] == "included"
    assert project_variant["status"] == "included"
    assert project_variant["locked"] is False


def test_catalog_components_includes_whatsapp_floating_for_all_website_plans() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = CatalogService(repository=repository)

    for plan_tier in ("essential", "plus", "pro", "custom"):
        response = service.list_components_for_catalog("website", "construction", plan_tier)
        whatsapp = next(component for component in response["components"] if component["componentCode"] == "whatsapp_floating")

        assert whatsapp["name"] == "WhatsApp flotante"
        assert whatsapp["componentTier"] == "core"
        assert whatsapp["status"] == "included"
        assert whatsapp["locked"] is False
        assert whatsapp["label"] == "Disponible"
        variants_by_code = {variant["variantCode"]: variant for variant in whatsapp["variants"]}
        for code in ["WA1", "WA2", "WA3"]:
            assert code in variants_by_code
            assert variants_by_code[code]["status"] == "included"
            assert variants_by_code[code]["locked"] is False
            assert variants_by_code[code]["extraPrice"] is None


def test_catalog_components_blank_canvas_is_available_from_plus() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = CatalogService(repository=repository)

    essential = service.list_components_for_catalog("website", "construction", "essential")
    essential_canvas = next(component for component in essential["components"] if component["componentCode"] == "blankCanvas")
    essential_variant = essential_canvas["variants"][0]

    plus = service.list_components_for_catalog("website", "construction", "plus")
    plus_canvas = next(component for component in plus["components"] if component["componentCode"] == "blankCanvas")
    plus_variant = plus_canvas["variants"][0]

    pro = service.list_components_for_catalog("website", "construction", "pro")
    pro_canvas = next(component for component in pro["components"] if component["componentCode"] == "blankCanvas")
    pro_variant = pro_canvas["variants"][0]

    assert essential_canvas["componentTier"] == "advanced"
    assert essential_canvas["status"] == "blocked"
    assert essential_canvas["locked"] is True
    assert essential_canvas["label"] == "No disponible para este plan"
    assert essential_variant["status"] == "blocked"
    assert essential_variant["locked"] is True

    assert plus_canvas["status"] == "included"
    assert plus_canvas["locked"] is False
    assert plus_canvas["label"] == "Disponible"
    assert plus_variant["variantTier"] == "advanced"
    assert plus_variant["status"] == "included"
    assert plus_variant["locked"] is False
    assert plus_variant["label"] == "Incluido"

    assert pro_canvas["status"] == "included"
    assert pro_canvas["locked"] is False
    assert pro_variant["status"] == "included"
    assert pro_variant["locked"] is False


def test_catalog_components_pro_ignores_category_block_for_active_components() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = CatalogService(repository=repository)

    response = service.list_components_for_catalog("website", "corporate", "pro")
    branches = next(component for component in response["components"] if component["componentCode"] == "branches")
    immersive_video = next(component for component in response["components"] if component["componentCode"] == "immersiveVideo")
    blank_canvas = next(component for component in response["components"] if component["componentCode"] == "blankCanvas")

    for component in (branches, immersive_video, blank_canvas):
        assert component["allowedByCategory"] is True
        assert component["status"] == "included"
        assert component["locked"] is False
        assert component["label"] == "Disponible"
        assert component["lockLabel"] == ""
        assert all(variant["status"] == "included" for variant in component["variants"])
        assert all(variant["locked"] is False for variant in component["variants"])


def test_pricing_summary_builds_matrix_per_variant() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = PricingSummaryService(repository=repository)

    summary = service.build_summary(product_type="website")
    hero = next(component for component in summary["components"] if component["componentCode"] == "hero")
    premium_variant = next(variant for variant in hero["variants"] if variant["variantCode"] == "H8")

    assert premium_variant["variantTier"] == "premium"
    assert premium_variant["matrix"]["essential"]["status"] == "blocked"
    assert premium_variant["matrix"]["plus"]["status"] == "blocked"
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
    assert validated.componentTier == "core"
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
                    "variantCode": "H8",
                    "name": "Editorial con video subido",
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


def test_pricing_seed_updates_component_when_legacy_id_already_exists() -> None:
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
    assert repository.collections[COMPONENTS_COLLECTION][0]["componentCode"] == "navigation"
    assert repository.collections[COMPONENTS_COLLECTION][0]["variants"][0]["variantCode"] == "N1"


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


def test_pricing_seed_uses_updated_website_plan_prices() -> None:
    repository = InMemoryPricingRepository()

    ensure_pricing_seed(repository=repository)
    plus_web = PricingPlanService(repository=repository).find_by_tier("website", "plus")

    assert plus_web["code"] == "plus_web"
    assert plus_web["basePrice"] == 19990
    assert plus_web["basePriceMonthly"] == 19990
    assert plus_web["basePriceYearly"] == 199990


def test_pricing_calculate_sums_plan_and_general_extras() -> None:
    repository = InMemoryPricingRepository()
    ensure_pricing_seed(repository=repository)
    service = PricingCalculatorService(repository=repository)

    response = service.calculate(
        PricingCalculateRequest(
            productType="website",
            planTier="plus",
            templateCategory="construction",
            selectedComponentExtras=[],
            selectedExtras=["custom_domain"],
            durationMonths=12,
        )
    )

    assert response["currency"] == "CLP"
    assert response["componentExtrasTotal"] == 0
    assert response["extrasTotal"] == 1990
    assert response["total"] == response["basePrice"] + 1990


def test_admin_pricing_discounts_route_is_registered_in_openapi() -> None:
    from app import main as main_module

    paths = main_module.app.openapi()["paths"]

    assert "/api/admin/pricing/discounts" in paths


def test_admin_discount_management_routes_are_registered_in_openapi() -> None:
    from app import main as main_module

    paths = main_module.app.openapi()["paths"]

    assert "/api/admin/studio/discount-codes" in paths
    assert "/api/admin/studio/discount-codes/{discount_code_id}" in paths
    assert "/api/admin/studio/discount-codes/{discount_code_id}/active" in paths
    assert "/api/payments/preview" in paths
