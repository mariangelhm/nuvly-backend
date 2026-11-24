"""Shared document response and status helpers."""

import logging
import re
from copy import deepcopy
from typing import Any, Dict, Optional

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.core.utils import utc_now_iso
from app.modules.domain.normalizer import normalize_document
from app.modules.domain.public_projection import public_experience

logger = logging.getLogger(__name__)


PUBLIC_SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")


def append_status_history(
    document: Dict[str, Any], status_field: str, changed_by: Optional[str], reason: Optional[str]
) -> None:
    status = document[status_field]
    document.setdefault("statusHistory", []).append(
        {
            "status": status,
            "changedAt": utc_now_iso(),
            "changedBy": changed_by,
            "reason": reason,
        }
    )


def ensure_snapshot(document: Optional[Dict[str, Any]], error_message: str, error_code: str) -> Dict[str, Any]:
    if not document:
        raise NuvlyError(error_message, 404, error_code)
    return document


SERVER_MANAGED_TEMPLATE_FIELDS = {
    "schemaVersion",
    "id",
    "templateStatus",
    "status",
    "statusHistory",
    "publishedSnapshotId",
    "lastPublishedAt",
    "createdAt",
    "updatedAt",
}


COMMON_EXPERIENCE_FIELDS = {
    "templateComponent",
    "content",
    "title",
    "slug",
    "productType",
    "planTier",
    "templateCategory",
    "styles",
    "layout",
    "blocks",
    "pages",
    "seo",
    "metadata",
    "selectedComponentExtras",
}


SERVER_MANAGED_CUSTOMER_METADATA = {
    "basePrice",
    "basePriceSource",
    "basePriceMonthly",
    "basePriceYearly",
    "pricingManaged",
    "productType",
    "planTier",
    "templateCategory",
}


STATIC_UPLOAD_PREFIX = "/static/uploads/"


def _resolve_public_asset_base_url(base_url: str | None = None) -> str | None:
    settings = get_settings()
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    if base_url:
        return base_url.rstrip("/")
    return None


def _absolutize_uploaded_media_urls(value: Any, resolved_base_url: str | None) -> Any:
    if resolved_base_url is None:
        return value
    if isinstance(value, dict):
        return {key: _absolutize_uploaded_media_urls(item, resolved_base_url) for key, item in value.items()}
    if isinstance(value, list):
        return [_absolutize_uploaded_media_urls(item, resolved_base_url) for item in value]
    if isinstance(value, str) and value.startswith(STATIC_UPLOAD_PREFIX):
        return f"{resolved_base_url}{value}"
    return value


def _prepare_snapshot_response(
    snapshot: Dict[str, Any], status_field: str, base_url: str | None = None
) -> Dict[str, Any]:
    prepared = deepcopy(snapshot)
    prepared["snapshot"] = _absolutize_uploaded_media_urls(
        public_experience(normalize_document(prepared["snapshot"], status_field)),
        _resolve_public_asset_base_url(base_url),
    )
    return prepared


def _decorate_public_media(document: Dict[str, Any], base_url: str | None = None) -> Dict[str, Any]:
    return _absolutize_uploaded_media_urls(deepcopy(document), _resolve_public_asset_base_url(base_url))
