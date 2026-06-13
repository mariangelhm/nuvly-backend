from copy import deepcopy
from typing import Any, Dict, List

from app.core.catalog import (
    DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE,
    DEFAULT_TEMPLATE_CATEGORY_BY_PRODUCT_TYPE,
    normalize_plan_tier,
    normalize_product_type,
    normalize_template_category,
    normalize_variant_level,
)
from app.core.errors import NuvlyError
from app.core.utils import slugify
from app.modules.domain.block_registry import BLOCK_REGISTRY
from app.modules.domain.defaults import default_main_page, default_page_source


NON_INDEXABLE_STATUSES = {
    "draft",
    "private_preview",
    "unpublished",
    "archived",
    "temporary",
    "editing",
    "abandoned",
    "pending_payment",
    "payment_failed",
    "paid",
    "cancelled",
}

PRIMARY_PAGE_KIND = "primary"
LINKED_PAGE_KIND = "linked"
SUPPORTED_PAGE_KINDS = {PRIMARY_PAGE_KIND, LINKED_PAGE_KIND}


def validate_block(block: Dict[str, Any]) -> None:
    if not isinstance(block, dict):
        raise NuvlyError("Cada block debe ser un objeto.", 422, "INVALID_BLOCK")

    block_type = block.get("type")
    variant = block.get("variant")
    block_id = block.get("id")
    enabled = block.get("enabled")
    order = block.get("order")
    props = block.get("props")
    settings = block.get("settings")

    if not isinstance(block_id, str) or not block_id.strip():
        raise NuvlyError("Cada block debe tener id no vacio.", 422, "INVALID_BLOCK_ID")
    if not isinstance(block_type, str) or not block_type.strip():
        raise NuvlyError("Cada block debe tener type no vacio.", 422, "INVALID_BLOCK_TYPE")
    if not isinstance(variant, str) or not variant.strip():
        raise NuvlyError("Cada block debe tener variant no vacio.", 422, "INVALID_BLOCK_VARIANT")
    if not isinstance(enabled, bool):
        raise NuvlyError("Cada block debe tener enabled boolean.", 422, "INVALID_BLOCK_ENABLED")
    if not isinstance(order, (int, float)) or isinstance(order, bool):
        raise NuvlyError("Cada block debe tener order numerico.", 422, "INVALID_BLOCK_ORDER")
    if not isinstance(props, dict):
        raise NuvlyError("Cada block debe tener props objeto.", 422, "INVALID_BLOCK_PROPS")
    if not isinstance(settings, dict):
        raise NuvlyError("Cada block debe tener settings objeto.", 422, "INVALID_BLOCK_SETTINGS")

    # TODO: Cuando exista block registry compartido frontend/backend, reactivar validacion estricta de variantes.


def _normalize_blocks(blocks_value: Any) -> List[Dict[str, Any]]:
    if blocks_value is None:
        return []
    if not isinstance(blocks_value, list):
        raise NuvlyError("blocks debe ser una lista.", 422, "INVALID_BLOCKS")

    blocks = blocks_value
    seen_ids: set[str] = set()
    singleton_seen: set[str] = set()

    for block in blocks:
        validate_block(block)
        block_id = block.get("id")
        if block_id in seen_ids:
            raise NuvlyError(f"Bloque duplicado por id: {block_id}", 422, "DUPLICATED_BLOCK_ID")
        seen_ids.add(block_id)
        block_type = block["type"]
        if BLOCK_REGISTRY.get(block_type, {}).get("singleton"):
            if block_type in singleton_seen:
                raise NuvlyError(
                    f"El bloque singleton '{block_type}' no puede estar duplicado.",
                    422,
                    "DUPLICATED_SINGLETON_BLOCK",
                )
            singleton_seen.add(block_type)

    for index, block in enumerate(blocks, start=1):
        block["order"] = index

    return blocks


def _legacy_linked_pages(metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    linked_pages = metadata.get("linkedPages")
    if linked_pages is None:
        return []
    if not isinstance(linked_pages, list):
        raise NuvlyError("metadata.linkedPages debe ser una lista.", 422, "INVALID_LINKED_PAGES")
    normalized_pages: List[Dict[str, Any]] = []
    for index, page in enumerate(linked_pages, start=1):
        if not isinstance(page, dict):
            raise NuvlyError("Cada linkedPage debe ser un objeto.", 422, "INVALID_LINKED_PAGE")
        normalized_page = deepcopy(page)
        normalized_page.setdefault("id", f"linked-{index}")
        normalized_page.setdefault("kind", "linked")
        normalized_page.setdefault("title", f"Subpagina {index}")
        normalized_page.setdefault("slug", slugify(normalized_page.get("title", "")))
        normalized_page.setdefault("path", f"/{normalized_page['slug']}" if normalized_page["slug"] else f"/linked-{index}")
        normalized_page.setdefault("parentPageId", "main")
        normalized_page.setdefault("source", default_page_source())
        normalized_page.setdefault("seo", {})
        normalized_page.setdefault("settings", {})
        normalized_page["blocks"] = _normalize_blocks(normalized_page.get("blocks"))
        normalized_pages.append(normalized_page)
    return normalized_pages


def _has_legacy_page_content(document: Dict[str, Any], metadata: Dict[str, Any]) -> bool:
    return bool(document.get("blocks")) or bool(metadata.get("linkedPages"))


def _normalize_pages(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    metadata = document.get("metadata") or {}
    pages_value = document.get("pages")

    if pages_value is None:
        primary_title = document.get("title") or "Pagina principal"
        legacy_pages = [default_main_page(primary_title, document.get("blocks"))]
        legacy_pages.extend(_legacy_linked_pages(metadata))
        return legacy_pages

    if not isinstance(pages_value, list):
        raise NuvlyError("pages debe ser una lista.", 422, "INVALID_PAGES")

    pages = pages_value
    if not pages and _has_legacy_page_content(document, metadata):
        primary_title = document.get("title") or "Pagina principal"
        legacy_pages = [default_main_page(primary_title, document.get("blocks"))]
        legacy_pages.extend(_legacy_linked_pages(metadata))
        return legacy_pages
    if not pages:
        return [default_main_page(document.get("title") or "Pagina principal")]

    seen_page_ids: set[str] = set()
    seen_page_paths: set[str] = set()
    seen_page_slugs: set[str] = set()
    primary_count = 0
    for page in pages:
        if not isinstance(page, dict):
            raise NuvlyError("Cada page debe ser un objeto.", 422, "INVALID_PAGE")
        page_id = page.get("id")
        if not isinstance(page_id, str) or not page_id.strip():
            raise NuvlyError("Cada page debe tener id no vacio.", 422, "INVALID_PAGE_ID")
        if page_id in seen_page_ids:
            raise NuvlyError(f"Pagina duplicada por id: {page_id}", 422, "DUPLICATED_PAGE_ID")
        seen_page_ids.add(page_id)

        page_kind = page.get("kind")
        if not isinstance(page_kind, str) or not page_kind.strip():
            raise NuvlyError("Cada page debe tener kind no vacio.", 422, "INVALID_PAGE_KIND")
        if page_kind not in SUPPORTED_PAGE_KINDS:
            raise NuvlyError("page.kind debe ser 'primary' o 'linked'.", 422, "INVALID_PAGE_KIND")
        if page_kind == PRIMARY_PAGE_KIND:
            primary_count += 1

        page_title = page.get("title")
        if not isinstance(page_title, str) or not page_title.strip():
            raise NuvlyError("Cada page debe tener title no vacio.", 422, "INVALID_PAGE_TITLE")

        page_slug = page.get("slug", "")
        if not isinstance(page_slug, str):
            raise NuvlyError("Cada page debe tener slug string.", 422, "INVALID_PAGE_SLUG")
        if page_kind != PRIMARY_PAGE_KIND:
            page["slug"] = slugify(page_slug or page_title)
        else:
            page["slug"] = slugify(page_slug) if page_slug else ""

        page_path = page.get("path")
        if not isinstance(page_path, str) or not page_path.strip():
            raise NuvlyError("Cada page debe tener path no vacio.", 422, "INVALID_PAGE_PATH")
        if not page_path.startswith("/"):
            raise NuvlyError("Cada page debe tener path absoluto.", 422, "INVALID_PAGE_PATH")
        if page_path in seen_page_paths:
            raise NuvlyError(f"Pagina duplicada por path: {page_path}", 422, "DUPLICATED_PAGE_PATH")
        seen_page_paths.add(page_path)

        if page["slug"]:
            if page["slug"] in seen_page_slugs:
                raise NuvlyError(f"Pagina duplicada por slug: {page['slug']}", 422, "DUPLICATED_PAGE_SLUG")
            seen_page_slugs.add(page["slug"])

        parent_page_id = page.get("parentPageId")
        if parent_page_id is not None and (not isinstance(parent_page_id, str) or not parent_page_id.strip()):
            raise NuvlyError("parentPageId debe ser string o null.", 422, "INVALID_PARENT_PAGE_ID")
        if page_kind == PRIMARY_PAGE_KIND:
            if page_path != "/":
                raise NuvlyError("La pagina primaria debe usar path '/'.", 422, "INVALID_PRIMARY_PAGE_PATH")
            if parent_page_id is not None:
                raise NuvlyError("La pagina primaria no puede tener parentPageId.", 422, "INVALID_PRIMARY_PARENT")
        else:
            if page_path == "/":
                raise NuvlyError("Las paginas linked no pueden usar path '/'.", 422, "INVALID_LINKED_PAGE_PATH")
            if parent_page_id is None:
                raise NuvlyError("Las paginas linked deben tener parentPageId.", 422, "INVALID_LINKED_PARENT")

        source = page.get("source") or {}
        if not isinstance(source, dict):
            raise NuvlyError("page.source debe ser un objeto.", 422, "INVALID_PAGE_SOURCE")
        page["source"] = {**default_page_source(), **source}

        seo = page.get("seo") or {}
        if not isinstance(seo, dict):
            raise NuvlyError("page.seo debe ser un objeto.", 422, "INVALID_PAGE_SEO")
        page["seo"] = seo

        settings = page.get("settings") or {}
        if not isinstance(settings, dict):
            raise NuvlyError("page.settings debe ser un objeto.", 422, "INVALID_PAGE_SETTINGS")
        page["settings"] = settings
        page["blocks"] = _normalize_blocks(page.get("blocks"))

    if primary_count != 1:
        raise NuvlyError("Debe existir exactamente una page primaria.", 422, "INVALID_PRIMARY_PAGE_COUNT")
    for page in pages:
        parent_page_id = page.get("parentPageId")
        if parent_page_id is not None and parent_page_id not in seen_page_ids:
            raise NuvlyError(f"parentPageId inexistente: {parent_page_id}", 422, "PAGE_PARENT_NOT_FOUND")

    return pages


def _sync_pages_and_legacy_fields(normalized: Dict[str, Any], pages: List[Dict[str, Any]]) -> None:
    primary_page = next((page for page in pages if page.get("kind") == PRIMARY_PAGE_KIND), None)
    if primary_page is None:
        raise NuvlyError("No se encontro la pagina principal.", 422, "PRIMARY_PAGE_NOT_FOUND")

    primary_blocks = primary_page.get("blocks", [])
    normalized["blocks"] = primary_blocks
    normalized["pages"] = pages

    normalized["metadata"] = normalized.get("metadata") or {}
    normalized["metadata"]["linkedPages"] = [deepcopy(page) for page in pages if page.get("kind") != PRIMARY_PAGE_KIND]


def _apply_explicit_root_blocks_to_primary_page(
    normalized: Dict[str, Any],
    pages: List[Dict[str, Any]],
) -> None:
    explicit_blocks_value = normalized.get("blocks")
    if not explicit_blocks_value:
        return
    explicit_blocks = _normalize_blocks(explicit_blocks_value)
    primary_page = next((page for page in pages if page.get("kind") == PRIMARY_PAGE_KIND), None)
    if primary_page is None:
        raise NuvlyError("No se encontro la pagina principal.", 422, "PRIMARY_PAGE_NOT_FOUND")
    primary_page["blocks"] = explicit_blocks


def normalize_document(document: Dict[str, Any], status_field: str) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized["slug"] = slugify(normalized.get("slug") or normalized.get("title", ""))
    default_product_type = "invitation" if normalized.get("experienceType") == "invitation" else "website"
    normalized["productType"] = normalize_product_type(normalized.get("productType"), default=default_product_type)
    normalized["planTier"] = normalize_plan_tier(
        normalized.get("planTier"),
        default=DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE[normalized["productType"]],
    )
    normalized["templateCategory"] = normalize_template_category(
        normalized.get("templateCategory"),
        product_type=normalized["productType"],
    )
    normalized["metadata"] = normalized.get("metadata") or {}
    normalized["metadata"]["level"] = normalize_variant_level(normalized["metadata"].get("level"))
    normalized["selectedComponentExtras"] = normalized.get("selectedComponentExtras") or []
    normalized["metadata"].setdefault("templateCategory", normalized["templateCategory"])
    normalized["metadata"].setdefault("planTier", normalized["planTier"])
    normalized["metadata"].setdefault("productType", normalized["productType"])
    pages = _normalize_pages(normalized)
    _apply_explicit_root_blocks_to_primary_page(normalized, pages)
    _sync_pages_and_legacy_fields(normalized, pages)

    blocks = normalized["blocks"]
    block_ids = [block["id"] for block in blocks]
    layout_value = normalized.get("layout")
    if layout_value is None:
        normalized["layout"] = {}
    elif not isinstance(layout_value, dict):
        raise NuvlyError("layout debe ser un objeto.", 422, "INVALID_LAYOUT")
    provided_order = ((normalized.get("layout") or {}).get("sectionOrder")) or []
    if provided_order and not isinstance(provided_order, list):
        raise NuvlyError("layout.sectionOrder debe ser una lista.", 422, "INVALID_SECTION_ORDER")
    if provided_order and provided_order != block_ids:
        raise NuvlyError(
            "layout.sectionOrder debe coincidir exactamente con el orden actual de blocks.",
            422,
            "INCONSISTENT_SECTION_ORDER",
        )

    normalized["layout"] = normalized.get("layout") or {}
    normalized["layout"]["sectionOrder"] = block_ids
    normalized["seo"] = normalized.get("seo") or {}

    status = normalized.get(status_field)
    normalized["seo"]["noIndex"] = status in NON_INDEXABLE_STATUSES

    normalized["metadata"].setdefault("catalogVisible", False)
    normalized["metadata"].setdefault("tags", [])
    normalized["metadata"].setdefault("linkedPages", [])

    return normalized
