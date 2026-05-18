from copy import deepcopy
from typing import Any, Dict, List
from app.core.errors import NuvlyError
from app.modules.experiences.registry import BLOCK_REGISTRY
from app.modules.experiences.utils import slugify

NON_INDEXABLE_STATUSES = {"draft", "private_preview", "archived"}

def validate_block(block: Dict[str, Any]) -> None:
    block_type = block.get("type")
    variant = block.get("variant")
    if block_type not in BLOCK_REGISTRY:
        raise NuvlyError(f"Tipo de bloque inválido: {block_type}", 422, "INVALID_BLOCK_TYPE")
    valid_variants = BLOCK_REGISTRY[block_type]["variants"]
    if variant not in valid_variants:
        raise NuvlyError(
            f"Variante inválida '{variant}' para el bloque '{block_type}'. Variantes válidas: {valid_variants}",
            422,
            "INVALID_BLOCK_VARIANT",
        )

def normalize_experience(document: Dict[str, Any]) -> Dict[str, Any]:
    normalized = deepcopy(document)
    normalized["slug"] = slugify(normalized.get("slug") or normalized.get("title", ""))
    blocks: List[Dict[str, Any]] = normalized.get("blocks") or []
    seen_ids: set[str] = set()
    singleton_seen: set[str] = set()
    for block in blocks:
        validate_block(block)
        block_id = block.get("id")
        if block_id in seen_ids:
            raise NuvlyError(f"Bloque duplicado por id: {block_id}", 422, "DUPLICATED_BLOCK_ID")
        seen_ids.add(block_id)
        block_type = block["type"]
        if BLOCK_REGISTRY[block_type].get("singleton"):
            if block_type in singleton_seen:
                raise NuvlyError(f"El bloque singleton '{block_type}' no puede estar duplicado.", 422, "DUPLICATED_SINGLETON_BLOCK")
            singleton_seen.add(block_type)
    for index, block in enumerate(blocks, start=1):
        block["order"] = index
    normalized["blocks"] = blocks
    normalized["layout"] = normalized.get("layout") or {}
    normalized["layout"]["sectionOrder"] = [block["id"] for block in blocks]
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
