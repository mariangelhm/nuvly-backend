from copy import deepcopy
from typing import Any, Dict, List
from app.core.errors import NuvlyError
from app.modules.experiences.registry import BLOCK_REGISTRY
from app.modules.experiences.utils import slugify

NON_INDEXABLE_STATUSES = {"draft", "private_preview", "archived"}

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

def normalize_experience(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized["slug"] = slugify(normalized.get("slug") or normalized.get("title", ""))
    blocks_value = normalized.get("blocks")
    if blocks_value is None:
        blocks: List[Dict[str, Any]] = []
    elif not isinstance(blocks_value, list):
        raise NuvlyError("blocks debe ser una lista.", 422, "INVALID_BLOCKS")
    else:
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
                raise NuvlyError(f"El bloque singleton '{block_type}' no puede estar duplicado.", 422, "DUPLICATED_SINGLETON_BLOCK")
            singleton_seen.add(block_type)
    layout_value = normalized.get("layout")
    if layout_value is None:
        normalized["layout"] = {}
    elif not isinstance(layout_value, dict):
        raise NuvlyError("layout debe ser un objeto.", 422, "INVALID_LAYOUT")
    provided_order = ((normalized.get("layout") or {}).get("sectionOrder")) or []
    if provided_order and not isinstance(provided_order, list):
        raise NuvlyError("layout.sectionOrder debe ser una lista.", 422, "INVALID_SECTION_ORDER")
    block_ids = [block["id"] for block in blocks]
    if provided_order and provided_order != block_ids:
        raise NuvlyError("layout.sectionOrder debe coincidir exactamente con el orden actual de blocks.", 422, "INCONSISTENT_SECTION_ORDER")
    for index, block in enumerate(blocks, start=1):
        block["order"] = index
    normalized["blocks"] = blocks
    normalized["layout"] = normalized.get("layout") or {}
    normalized["layout"]["sectionOrder"] = block_ids
    normalized["seo"] = normalized.get("seo") or {}
    status = normalized.get("status", "draft")
    if status in NON_INDEXABLE_STATUSES:
        normalized["seo"]["noIndex"] = True
    elif status == "published":
        normalized["seo"]["noIndex"] = False
    normalized["metadata"] = normalized.get("metadata") or {}
    normalized["metadata"].setdefault("catalogVisible", False)
    normalized["metadata"].setdefault("tags", [])
    return normalized
