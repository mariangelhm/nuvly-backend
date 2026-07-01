import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.catalog import (
    DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE,
    DEFAULT_TEMPLATE_CATEGORY_BY_PRODUCT_TYPE,
    PlanTier,
    ProductType,
    TemplateCategoryCode,
    VariantLevel,
    normalize_plan_tier,
    normalize_product_type,
    normalize_template_category,
)
from app.core.config import get_settings
from app.core.utils import new_id, slugify, utc_now_iso
from app.core.errors import NuvlyError
from app.modules.domain.defaults import (
    default_customer_data,
    default_invitation_customer_fields,
    default_payment,
    default_template_document,
    default_website_customer_fields,
)
from app.modules.domain.normalizer import normalize_document
from app.modules.domain.repository import DomainRepository
from app.modules.domain.schemas import PublishRequest
from app.modules.pricing.service import (
    PricingComponentService,
    PricingPlanService,
    TemplateCategoryService,
    build_component_catalog_state,
    build_variant_catalog_state,
)

logger = logging.getLogger(__name__)
PUBLIC_SLUG_PATTERN = re.compile(r"^[a-z0-9-]+$")


@dataclass(frozen=True)
class TemplateConfig:
    collection: str
    snapshot_collection: str
    source_type: str
    entity_kind: str
    experience_type: str
    id_prefix: str
    not_found_message: str
    not_found_code: str
    duplicate_message: str
    data_field: str


@dataclass(frozen=True)
class CustomerConfig:
    collection: str
    snapshot_collection: str
    source_type: str
    entity_kind: str
    id_prefix: str
    not_found_message: str
    not_found_code: str
    duplicate_message: str
    data_field: str
    template_config: TemplateConfig


INVITATION_TEMPLATE_CONFIG = TemplateConfig(
    collection="invitation_templates",
    snapshot_collection="invitation_template_snapshots",
    source_type="invitation_template",
    entity_kind="invitation",
    experience_type="invitation",
    id_prefix="itpl",
    not_found_message="Template de invitacion no encontrado.",
    not_found_code="INVITATION_TEMPLATE_NOT_FOUND",
    duplicate_message="Ya existe un template de invitacion con ese slug.",
    data_field="invitationData",
)

WEBSITE_TEMPLATE_CONFIG = TemplateConfig(
    collection="website_templates",
    snapshot_collection="website_template_snapshots",
    source_type="website_template",
    entity_kind="website",
    experience_type="web",
    id_prefix="wtpl",
    not_found_message="Template de website no encontrado.",
    not_found_code="WEBSITE_TEMPLATE_NOT_FOUND",
    duplicate_message="Ya existe un template de website con ese slug.",
    data_field="websiteData",
)

CUSTOMER_INVITATION_CONFIG = CustomerConfig(
    collection="customer_invitations",
    snapshot_collection="customer_invitation_snapshots",
    source_type="customer_invitation",
    entity_kind="invitation",
    id_prefix="cinv",
    not_found_message="Invitacion del cliente no encontrada.",
    not_found_code="CUSTOMER_INVITATION_NOT_FOUND",
    duplicate_message="Ya existe una invitacion del cliente con ese slug.",
    data_field="invitationData",
    template_config=INVITATION_TEMPLATE_CONFIG,
)

CUSTOMER_WEBSITE_CONFIG = CustomerConfig(
    collection="customer_websites",
    snapshot_collection="customer_website_snapshots",
    source_type="customer_website",
    entity_kind="website",
    id_prefix="cweb",
    not_found_message="Website del cliente no encontrado.",
    not_found_code="CUSTOMER_WEBSITE_NOT_FOUND",
    duplicate_message="Ya existe un website del cliente con ese slug.",
    data_field="websiteData",
    template_config=WEBSITE_TEMPLATE_CONFIG,
)


def append_status_history(document: Dict[str, Any], status_field: str, changed_by: Optional[str], reason: Optional[str]) -> None:
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

STATIC_UPLOAD_PREFIX = "/static/uploads/"


def _collect_document_blocks(document: Dict[str, Any]) -> List[Dict[str, Any]]:
    pages = document.get("pages") or []
    if pages:
        collected: List[Dict[str, Any]] = []
        for page in pages:
            collected.extend(page.get("blocks") or [])
        return collected
    return document.get("blocks") or []


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


def _prepare_snapshot_response(snapshot: Dict[str, Any], status_field: str, base_url: str | None = None) -> Dict[str, Any]:
    prepared = deepcopy(snapshot)
    prepared["snapshot"] = _absolutize_uploaded_media_urls(
        normalize_document(prepared["snapshot"], status_field),
        _resolve_public_asset_base_url(base_url),
    )
    return prepared


def _decorate_public_media(document: Dict[str, Any], base_url: str | None = None) -> Dict[str, Any]:
    return _absolutize_uploaded_media_urls(deepcopy(document), _resolve_public_asset_base_url(base_url))


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

        category_document = self.category_service.get_by_code(product_type, template_category)
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
            component_availability = build_component_catalog_state(
                component_tier=component["componentTier"],
                plan_tier=plan_tier,
                component_allowed=True,
                component_active=component.get("active", True),
            )
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


class TemplateService:
    def __init__(self, config: TemplateConfig, repository: DomainRepository | None = None):
        self.config = config
        self.repository = repository or DomainRepository()
        self.commercial_rules = CommercialRulesService(self.repository)

    def _ensure_slug_available(self, slug: str, current_id: Optional[str] = None) -> None:
        existing = self.repository.find_document_by_slug(self.config.collection, slug)
        logger.info(
            "Slug validation | database=%s collection=%s slug=%s found=%s foundId=%s currentId=%s",
            self.repository.database_name(),
            self.config.collection,
            slug,
            existing is not None,
            existing.get("id") if existing else None,
            current_id,
        )
        if existing and existing.get("id") != current_id:
            raise NuvlyError(self.config.duplicate_message, 409, "DUPLICATED_SLUG")

    def _get_template_document(self, template_id: str) -> Dict[str, Any]:
        document = self.repository.find_document(self.config.collection, {"id": template_id})
        if not document:
            raise NuvlyError(self.config.not_found_message, 404, self.config.not_found_code)
        return document

    @staticmethod
    def _ensure_not_published_for_deprecation(document: Dict[str, Any]) -> None:
        if document.get("templateStatus") == "published":
            raise NuvlyError(
                "No se puede deprecar un template publicado. Primero debes despublicarlo.",
                409,
                "PUBLISHED_TEMPLATE_CANNOT_BE_DEPRECATED",
            )

    def _resolve_plan_base_price(self, product_type: ProductType, plan_tier: PlanTier) -> float:
        pricing_plan_service = PricingPlanService(repository=self.repository)  # type: ignore[arg-type]
        try:
            plan = pricing_plan_service.find_by_tier(product_type, plan_tier)
            return float(plan.get("basePrice", 0) or 0)
        except NuvlyError:
            logger.warning(
                "Pricing plan not found while resolving basePrice | productType=%s planTier=%s",
                product_type,
                plan_tier,
            )
            return 0

    def _apply_template_base_price_defaults(self, document: Dict[str, Any], publish_request: PublishRequest | None = None) -> Dict[str, Any]:
        metadata = document.get("metadata") or {}
        base_price_source = metadata.get("basePriceSource")
        current_base_price = metadata.get("basePrice")
        plan_base_price = self._resolve_plan_base_price(document["productType"], document["planTier"])

        if publish_request is not None:
            if publish_request.priceMode == "manual":
                metadata["basePrice"] = float(publish_request.basePrice or 0)
                metadata["basePriceSource"] = "manual"
            else:
                metadata["basePrice"] = plan_base_price
                metadata["basePriceSource"] = "plan_base"
            document["metadata"] = metadata
            return document

        if current_base_price is None or (float(current_base_price) == 0 and base_price_source != "manual"):
            metadata["basePrice"] = plan_base_price
            metadata["basePriceSource"] = "plan_base"
        document["metadata"] = metadata
        return document

    def create(self, payload, base_url: str | None = None) -> Dict[str, Any]:
        now = utc_now_iso()
        document_id = new_id(self.config.id_prefix)
        slug = slugify(payload.slug or payload.title)
        document = default_template_document(self.config.entity_kind, payload.title, slug, now, document_id)
        payload_data = payload.model_dump(mode="json", exclude_none=True)
        for field in SERVER_MANAGED_TEMPLATE_FIELDS:
            payload_data.pop(field, None)
        payload_data["experienceType"] = self.config.experience_type
        logger.info(
            "Template create request | database=%s collection=%s title=%s requestedSlug=%s generatedId=%s",
            self.repository.database_name(),
            self.config.collection,
            payload.title,
            slug,
            document_id,
        )
        for key, value in payload_data.items():
            document[key] = value
        product_type = normalize_product_type(document.get("productType"), default="invitation" if self.config.entity_kind == "invitation" else "website")
        document["productType"] = product_type
        document["planTier"] = normalize_plan_tier(document.get("planTier"), default=DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE[product_type])
        document["templateCategory"] = normalize_template_category(document.get("templateCategory"), product_type=product_type)
        if "pages" not in payload_data:
            document.pop("pages", None)
        if self.config.data_field not in payload_data:
            document.pop(self.config.data_field, None)
        document["updatedAt"] = now
        append_status_history(document, "templateStatus", None, "initial_draft")
        document = normalize_document(document, "templateStatus")
        document = self._apply_template_base_price_defaults(document)
        document = self.commercial_rules.validate_document(document)
        self._ensure_slug_available(document["slug"])
        logger.info("Template created | collection=%s id=%s", self.config.collection, document["id"])
        stored = self.repository.insert_document(self.config.collection, document, self.config.duplicate_message)
        return _decorate_public_media(stored, base_url=base_url)

    def _merge_missing_template_fields(self, current: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
        merged = deepcopy(document)
        skip_fields: set[str] = set()
        if "pages" in merged:
            skip_fields.add("blocks")
        if "blocks" in merged:
            skip_fields.add("pages")
        if "pages" not in merged and "blocks" in merged and not merged.get("blocks"):
            merged["pages"] = deepcopy(current.get("pages", []))
        for field in COMMON_EXPERIENCE_FIELDS | {self.config.data_field}:
            if field in skip_fields:
                continue
            if field not in merged and field in current:
                merged[field] = deepcopy(current[field])
        return merged

    def list(
        self,
        limit: int = 20,
        skip: int = 0,
        template_status: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[VariantLevel] = None,
        catalog_visible: Optional[bool] = None,
        base_url: str | None = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if template_status:
            filters["templateStatus"] = template_status
        if category:
            filters["templateCategory"] = category
        if level:
            filters["metadata.level"] = level
        if catalog_visible is not None:
            filters["metadata.catalogVisible"] = catalog_visible
        return [self._prepare_template_response(document, base_url=base_url) for document in self.repository.find_documents(self.config.collection, filters, limit=limit, skip=skip)]

    def get(self, template_id: str, base_url: str | None = None) -> Dict[str, Any]:
        return self._prepare_template_response(self._get_template_document(template_id), base_url=base_url)

    def update(self, template_id: str, payload, base_url: str | None = None) -> Dict[str, Any]:
        current = self._get_template_document(template_id)
        now = utc_now_iso()
        document = payload.model_dump(mode="json", exclude_none=True)
        for field in SERVER_MANAGED_TEMPLATE_FIELDS:
            document.pop(field, None)
        document = self._merge_missing_template_fields(current, document)
        document.update(
            {
                "id": current["id"],
                "experienceType": self.config.experience_type,
                "productType": normalize_product_type(current.get("productType"), default="invitation" if self.config.entity_kind == "invitation" else "website"),
                "templateStatus": current["templateStatus"],
                "statusHistory": current.get("statusHistory", []),
                "publishedSnapshotId": current.get("publishedSnapshotId"),
                "lastPublishedAt": current.get("lastPublishedAt"),
                "createdAt": current["createdAt"],
                "updatedAt": now,
            }
        )
        document = normalize_document(document, "templateStatus")
        document = self._apply_template_base_price_defaults(document)
        document = self.commercial_rules.validate_document(document)
        self._ensure_slug_available(document["slug"], current_id=template_id)
        logger.info("Template updated | collection=%s id=%s", self.config.collection, template_id)
        stored = self.repository.replace_document(
            self.config.collection,
            template_id,
            document,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )
        return _decorate_public_media(stored, base_url=base_url)

    def update_status(self, template_id: str, template_status: str, changed_by: Optional[str], reason: Optional[str], base_url: str | None = None) -> Dict[str, Any]:
        if template_status == "published":
            self.publish(template_id, changed_by=changed_by, reason=reason, base_url=base_url)
            return self.get(template_id, base_url=base_url)

        current = self._get_template_document(template_id)
        if current["templateStatus"] == template_status:
            return self._prepare_template_response(current, base_url=base_url)
        if template_status == "deprecated":
            self._ensure_not_published_for_deprecation(current)
        current["templateStatus"] = template_status
        current["updatedAt"] = utc_now_iso()
        append_status_history(current, "templateStatus", changed_by, reason)
        current = normalize_document(current, "templateStatus")
        logger.info("Template status changed | collection=%s id=%s status=%s", self.config.collection, template_id, template_status)
        stored = self.repository.replace_document(
            self.config.collection,
            template_id,
            current,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )
        return self._prepare_template_response(stored, base_url=base_url)

    def publish(
        self,
        template_id: str,
        changed_by: Optional[str] = None,
        reason: Optional[str] = None,
        base_url: str | None = None,
        publish_request: PublishRequest | None = None,
    ) -> Dict[str, Any]:
        current = self._get_template_document(template_id)
        now = utc_now_iso()
        document = deepcopy(current)
        if document["templateStatus"] != "published":
            document["templateStatus"] = "published"
            append_status_history(document, "templateStatus", changed_by, reason)
        document["updatedAt"] = now
        document = normalize_document(document, "templateStatus")
        document = self._apply_template_base_price_defaults(document, publish_request=publish_request)
        document = self.commercial_rules.validate_document(document)

        version = self.repository.count_documents(self.config.snapshot_collection, {"sourceId": template_id}) + 1
        snapshot = {
            "id": new_id("snap"),
            "sourceId": template_id,
            "sourceType": self.config.source_type,
            "version": version,
            "slug": document["slug"],
            "snapshot": self._build_snapshot_payload(document, version, now),
            "createdAt": now,
            "publishedAt": now,
        }
        self.repository.insert_document(
            self.config.snapshot_collection,
            snapshot,
            duplicate_message="Ya existe un snapshot con esa version.",
            duplicate_code="DUPLICATED_SNAPSHOT_VERSION",
        )
        document["publishedSnapshotId"] = snapshot["id"]
        document["lastPublishedAt"] = now
        self.repository.replace_document(
            self.config.collection,
            template_id,
            document,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )
        logger.info("Template published | collection=%s id=%s snapshot=%s version=%s", self.config.collection, template_id, snapshot["id"], version)
        return _decorate_public_media(snapshot, base_url=base_url)

    def unpublish(self, template_id: str, changed_by: Optional[str] = None, reason: Optional[str] = "unpublish_template") -> Dict[str, Any]:
        current = self.get(template_id)
        if current["templateStatus"] == "unpublished":
            return current

        current["templateStatus"] = "unpublished"
        current["updatedAt"] = utc_now_iso()
        append_status_history(current, "templateStatus", changed_by, reason)
        current = normalize_document(current, "templateStatus")
        logger.info("Template unpublished | collection=%s id=%s", self.config.collection, template_id)
        return self.repository.replace_document(
            self.config.collection,
            template_id,
            current,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )

    def list_public(
        self,
        limit: int = 20,
        skip: int = 0,
        category: Optional[str] = None,
        level: Optional[VariantLevel] = None,
        tags: Optional[List[str]] = None,
        extra_filter_value: Optional[str] = None,
        base_url: str | None = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {"templateStatus": "published"}
        if category:
            filters["templateCategory"] = category
        if level:
            filters["metadata.level"] = level
        if tags:
            filters["metadata.tags"] = {"$in": tags}
        if extra_filter_value:
            if self.config.entity_kind == "invitation":
                filters["invitationData.eventType"] = extra_filter_value
            else:
                filters["websiteData.industry"] = extra_filter_value

        documents = self.repository.find_documents(
            self.config.collection,
            filters,
            limit=limit,
            skip=skip,
            sort_field="lastPublishedAt",
        )
        logger.info(
            "Public templates query | collection=%s filter=%s totalPublishedFound=%s",
            self.config.collection,
            filters,
            len(documents),
        )
        logger.info(
            "Public templates result | collection=%s returnedIds=%s",
            self.config.collection,
            [document.get("id") for document in documents],
        )
        return [self._build_public_card(document, base_url=base_url) for document in documents]

    def get_public_by_slug(self, slug: str, base_url: str | None = None) -> Dict[str, Any]:
        normalized_slug = slugify(slug)
        snapshots = self.repository.find_documents(
            self.config.snapshot_collection,
            {"slug": normalized_slug},
            limit=50,
            skip=0,
            sort_field="publishedAt",
        )
        for snapshot in snapshots:
            document = self.repository.find_document(
                self.config.collection,
                {
                    "id": snapshot["sourceId"],
                    "templateStatus": "published",
                    "publishedSnapshotId": snapshot["id"],
                },
            )
            if document:
                return _prepare_snapshot_response(snapshot, "templateStatus", base_url=base_url)
        if not snapshots:
            raise NuvlyError("Template publico no encontrado.", 404, "PUBLIC_TEMPLATE_NOT_FOUND")
        raise NuvlyError("El slug solicitado no corresponde al snapshot publicado vigente.", 404, "PUBLIC_TEMPLATE_NOT_FOUND")

    def _build_snapshot_payload(self, document: Dict[str, Any], version: int, now: str) -> Dict[str, Any]:
        payload = {
            "id": document["id"],
            "title": document["title"],
            "slug": document["slug"],
            "experienceType": self.config.experience_type,
            "productType": document["productType"],
            "planTier": document["planTier"],
            "templateCategory": document["templateCategory"],
            "templateStatus": "published",
            "styles": deepcopy(document.get("styles", {})),
            "layout": deepcopy(document.get("layout", {})),
            "blocks": deepcopy(document.get("blocks", [])),
            "pages": deepcopy(document.get("pages", [])),
            "seo": deepcopy(document.get("seo", {})),
            "metadata": deepcopy(document.get("metadata", {})),
            "selectedComponentExtras": deepcopy(document.get("selectedComponentExtras", [])),
            "version": version,
            "publishedAt": now,
        }
        if document.get("commercialValidationSkipped"):
            payload["commercialValidationSkipped"] = True
        if self.config.data_field in document:
            payload[self.config.data_field] = deepcopy(document.get(self.config.data_field))
        return payload

    def _build_public_card(self, document: Dict[str, Any], base_url: str | None = None) -> Dict[str, Any]:
        card = {
            "id": document["id"],
            "title": document.get("title", ""),
            "slug": document.get("slug", ""),
            "templateStatus": document.get("templateStatus", "published"),
            "metadata": deepcopy(document.get("metadata", {})),
            "seo": deepcopy(document.get("seo", {})),
            "updatedAt": document.get("updatedAt"),
            "lastPublishedAt": document.get("lastPublishedAt"),
            "publishedSnapshotId": document.get("publishedSnapshotId"),
        }
        return _absolutize_uploaded_media_urls(card, _resolve_public_asset_base_url(base_url))

    def _get_published_snapshot_from_document(self, document: Dict[str, Any], raise_on_missing: bool = True) -> Optional[Dict[str, Any]]:
        snapshot_id = document.get("publishedSnapshotId")
        if not snapshot_id:
            if raise_on_missing:
                raise NuvlyError("El template publicado no tiene snapshot asociado.", 409, "PUBLISHED_TEMPLATE_WITHOUT_SNAPSHOT")
            return None
        snapshot = self.repository.find_document(self.config.snapshot_collection, {"id": snapshot_id})
        if snapshot:
            return snapshot
        if raise_on_missing:
            raise NuvlyError("Snapshot publicado no encontrado.", 404, "PUBLISHED_TEMPLATE_SNAPSHOT_NOT_FOUND")
        return None

    def _prepare_template_response(self, document: Dict[str, Any], base_url: str | None = None) -> Dict[str, Any]:
        prepared = deepcopy(document)
        prepared["experienceType"] = self.config.experience_type
        normalized = normalize_document(prepared, "templateStatus")
        return _absolutize_uploaded_media_urls(normalized, _resolve_public_asset_base_url(base_url))


class CustomerProjectService:
    def __init__(self, config: CustomerConfig, repository: DomainRepository | None = None):
        self.config = config
        self.repository = repository or DomainRepository()
        self.template_service = TemplateService(config.template_config, repository=self.repository)
        self.commercial_rules = CommercialRulesService(self.repository)

    def _merge_missing_customer_fields(self, current: Dict[str, Any], document: Dict[str, Any]) -> Dict[str, Any]:
        merged = deepcopy(document)
        skip_fields: set[str] = set()
        if "pages" in merged:
            skip_fields.add("blocks")
        if "blocks" in merged:
            skip_fields.add("pages")
        if "pages" not in merged and "blocks" in merged and not merged.get("blocks"):
            merged["pages"] = deepcopy(current.get("pages", []))
        customer_specific_fields = {
            self.config.data_field,
            "customerData",
            "publicSlug",
            "productType",
            "planTier",
            "templateCategory",
            "selectedComponentExtras",
        }
        if self.config.entity_kind == "invitation":
            customer_specific_fields.update({"guests", "rsvpResponses", "personalizedMessages"})
        else:
            customer_specific_fields.update({"leadForms", "formSubmissions", "customDomain"})
        for field in COMMON_EXPERIENCE_FIELDS | customer_specific_fields:
            if field in skip_fields:
                continue
            if field not in merged and field in current:
                merged[field] = deepcopy(current[field])
        return merged

    def _get_project_document(self, project_id: str) -> Dict[str, Any]:
        document = self.repository.find_document(self.config.collection, {"id": project_id})
        if not document:
            raise NuvlyError(self.config.not_found_message, 404, self.config.not_found_code)
        return document

    def create_from_template(self, payload, base_url: str | None = None, current_user: Dict[str, Any] | None = None) -> Dict[str, Any]:
        template = self.repository.find_document(
            self.config.template_config.collection,
            {"id": payload.templateId, "templateStatus": "published"},
        )
        if not template:
            raise NuvlyError("El template publicado no fue encontrado.", 404, "PUBLISHED_TEMPLATE_NOT_FOUND")
        template_snapshot = self.template_service._get_published_snapshot_from_document(template)
        base_snapshot = template_snapshot["snapshot"]

        now = utc_now_iso()
        document_id = new_id(self.config.id_prefix)
        document = {
            "id": document_id,
            "title": base_snapshot["title"],
            "slug": slugify(f"{base_snapshot['slug']}-{document_id[-6:]}"),
            "productType": base_snapshot["productType"],
            "planTier": base_snapshot["planTier"],
            "templateCategory": base_snapshot["templateCategory"],
            "styles": deepcopy(base_snapshot.get("styles", {})),
            "layout": deepcopy(base_snapshot.get("layout", {})),
            "blocks": deepcopy(base_snapshot.get("blocks", [])),
            "pages": deepcopy(base_snapshot.get("pages")),
            "seo": deepcopy(base_snapshot.get("seo", {})),
            "metadata": deepcopy(base_snapshot.get("metadata", {})),
            "ownerId": current_user.get("id") if current_user else None,
            "ownerEmail": current_user.get("email") if current_user else (payload.customerData.email or None),
            "templateId": template["id"],
            "templateSnapshotId": template_snapshot["id"],
            "selectionSource": payload.selectionSource,
            "selectedAt": payload.selectedAt or now,
            "externalAuthProvider": payload.externalAuthProvider,
            "externalAuthSubject": payload.externalAuthSubject,
            "selectedComponentExtras": deepcopy(base_snapshot.get("selectedComponentExtras", [])),
            "customerData": payload.customerData.model_dump(mode="json"),
            "customerStatus": "draft",
            "payment": default_payment(),
            "publicSlug": None,
            "statusHistory": [],
            "publishedSnapshotId": None,
            "lastPublishedAt": None,
            "createdAt": now,
            "updatedAt": now,
        }
        if self.config.data_field in base_snapshot:
            document[self.config.data_field] = deepcopy(base_snapshot.get(self.config.data_field))
        if self.config.entity_kind == "invitation":
            document.update(default_invitation_customer_fields())
        else:
            document.update(default_website_customer_fields())

        product_type = document.get("productType")
        plan_tier = document.get("planTier")
        metadata = document.get("metadata") or {}
        snapshot_price = (base_snapshot.get("metadata") or {}).get("basePrice")
        snapshot_price_source = (base_snapshot.get("metadata") or {}).get("basePriceSource")
        if snapshot_price is not None and not (float(snapshot_price) == 0 and snapshot_price_source != "manual"):
            metadata["basePrice"] = snapshot_price
            if snapshot_price_source:
                metadata["basePriceSource"] = snapshot_price_source
        else:
            metadata["basePrice"] = self.template_service._resolve_plan_base_price(product_type, plan_tier)
            metadata["basePriceSource"] = "plan_base"
        document["metadata"] = metadata

        append_status_history(document, "customerStatus", None, "created_from_template")
        document = normalize_document(document, "customerStatus")
        document = self.commercial_rules.validate_document(document)
        document["seo"] = deepcopy(base_snapshot.get("seo", {}))
        logger.info("Customer project created | collection=%s id=%s template=%s", self.config.collection, document["id"], template["id"])
        stored = self.repository.insert_document(self.config.collection, document, self.config.duplicate_message)
        return _decorate_public_media(stored, base_url=base_url)

    def _normalize_public_slug(self, public_slug: str | None, title: str | None) -> str | None:
        if public_slug is None:
            if title is None:
                return None
            generated = slugify(title)
            return generated or None

        normalized = public_slug.strip()
        if not normalized:
            return None
        if len(normalized) < 3:
            raise NuvlyError("publicSlug debe tener al menos 3 caracteres.", 400, "INVALID_PUBLIC_SLUG")
        if not PUBLIC_SLUG_PATTERN.fullmatch(normalized):
            raise NuvlyError("publicSlug solo puede contener minusculas, numeros y guiones.", 400, "INVALID_PUBLIC_SLUG")
        return normalized

    def _ensure_public_slug_available(self, public_slug: str, current_id: str | None = None) -> None:
        existing = self.repository.find_document(self.config.collection, {"publicSlug": public_slug})
        if existing and existing.get("id") != current_id:
            raise NuvlyError("El publicSlug ya existe para otro proyecto.", 409, "PUBLIC_SLUG_ALREADY_EXISTS")

    def _validate_ready_for_pending_payment(self, document: Dict[str, Any]) -> None:
        title = (document.get("title") or "").strip()
        if not title:
            raise NuvlyError("El titulo es obligatorio antes de continuar al pago.", 400, "TITLE_REQUIRED")

        public_slug = document.get("publicSlug")
        if not public_slug:
            raise NuvlyError("El publicSlug es obligatorio antes de continuar al pago.", 400, "PUBLIC_SLUG_REQUIRED")

        self._ensure_public_slug_available(public_slug, current_id=document.get("id"))

    @staticmethod
    def _build_owner_filters(owner_id: str | None = None, owner_email: str | None = None) -> Dict[str, Any]:
        clauses: List[Dict[str, Any]] = []
        if owner_id:
            clauses.append({"ownerId": owner_id})
        if owner_email:
            clauses.append({"ownerEmail": owner_email})
        if not clauses:
            return {}
        if len(clauses) == 1:
            return clauses[0]
        return {"$or": clauses}

    def list_by_owner(
        self,
        owner_id: str | None = None,
        owner_email: str | None = None,
        *,
        limit: int = 50,
        skip: int = 0,
        base_url: str | None = None,
    ) -> List[Dict[str, Any]]:
        filters = self._build_owner_filters(owner_id=owner_id, owner_email=owner_email)
        if not filters:
            return []
        documents = self.repository.find_documents(self.config.collection, filters, limit=limit, skip=skip)
        return [self._prepare_customer_response(document, base_url=base_url) for document in documents]

    @staticmethod
    def _owner_matches(document: Dict[str, Any], owner_id: str | None = None, owner_email: str | None = None) -> bool:
        if owner_id and document.get("ownerId") == owner_id:
            return True
        if owner_email and document.get("ownerEmail") == owner_email:
            return True
        return False

    def _get_project_document_for_owner(
        self,
        project_id: str,
        *,
        owner_id: str | None = None,
        owner_email: str | None = None,
    ) -> Dict[str, Any]:
        document = self._get_project_document(project_id)
        if not self._owner_matches(document, owner_id=owner_id, owner_email=owner_email):
            raise NuvlyError("No tienes permisos para acceder a este recurso.", 403, "CUSTOMER_PROJECT_FORBIDDEN")
        return document

    @staticmethod
    def to_product_summary(document: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": document["id"],
            "title": document["title"],
            "productType": document["productType"],
            "planTier": document["planTier"],
            "templateCategory": document["templateCategory"],
            "customerStatus": document["customerStatus"],
            "publicSlug": document.get("publicSlug"),
            "ownerId": document.get("ownerId"),
            "ownerEmail": document.get("ownerEmail"),
            "templateId": document["templateId"],
            "templateSnapshotId": document["templateSnapshotId"],
            "selectionSource": document.get("selectionSource", "catalog"),
            "selectedAt": document["selectedAt"],
            "payment": deepcopy(document.get("payment", default_payment())),
            "metadata": deepcopy(document.get("metadata", {})),
            "createdAt": document["createdAt"],
            "updatedAt": document["updatedAt"],
            "lastPublishedAt": document.get("lastPublishedAt"),
        }

    def get(self, project_id: str, base_url: str | None = None) -> Dict[str, Any]:
        return self._prepare_customer_response(self._get_project_document(project_id), base_url=base_url)

    def get_for_owner(
        self,
        project_id: str,
        *,
        owner_id: str | None = None,
        owner_email: str | None = None,
        base_url: str | None = None,
    ) -> Dict[str, Any]:
        return self._prepare_customer_response(
            self._get_project_document_for_owner(project_id, owner_id=owner_id, owner_email=owner_email),
            base_url=base_url,
        )

    def update(self, project_id: str, payload, base_url: str | None = None) -> Dict[str, Any]:
        current = self._get_project_document(project_id)
        now = utc_now_iso()
        document = payload.model_dump(mode="json", exclude_none=True)
        document = self._merge_missing_customer_fields(current, document)
        # Only generate publicSlug if explicitly provided in the update payload
        payload_dict = payload.model_dump(mode="json", exclude_none=False)
        if "publicSlug" in payload_dict and payload_dict["publicSlug"] is not None:
            public_slug = self._normalize_public_slug(payload_dict["publicSlug"], document.get("title"))
        elif current.get("publicSlug") is None:
            public_slug = self._normalize_public_slug(None, document.get("title"))
        else:
            public_slug = current.get("publicSlug")
        if not document.get("slug"):
            document["slug"] = current["slug"]
        if public_slug:
            self._ensure_public_slug_available(public_slug, current_id=project_id)
        document.update(
            {
                "id": current["id"],
                "ownerId": current.get("ownerId"),
                "ownerEmail": current.get("ownerEmail"),
                "templateId": current["templateId"],
                "templateSnapshotId": current["templateSnapshotId"],
                "selectionSource": current.get("selectionSource", "catalog"),
                "selectedAt": current.get("selectedAt", current["createdAt"]),
                "externalAuthProvider": current.get("externalAuthProvider"),
                "externalAuthSubject": current.get("externalAuthSubject"),
                "productType": normalize_product_type(current.get("productType"), default="invitation" if self.config.entity_kind == "invitation" else "website"),
                "planTier": normalize_plan_tier(current.get("planTier"), default=DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE[current.get("productType", "website")]),
                "templateCategory": normalize_template_category(
                    current.get("templateCategory"),
                    product_type=normalize_product_type(current.get("productType"), default="invitation" if self.config.entity_kind == "invitation" else "website"),
                ),
                "publicSlug": public_slug,
                "customerStatus": current["customerStatus"],
                "payment": current.get("payment", default_payment()),
                "statusHistory": current.get("statusHistory", []),
                "publishedSnapshotId": current.get("publishedSnapshotId"),
                "lastPublishedAt": current.get("lastPublishedAt"),
                "createdAt": current["createdAt"],
                "updatedAt": now,
            }
        )
        document = normalize_document(document, "customerStatus")
        document = self.commercial_rules.validate_document(document)
        logger.info("Customer project updated | collection=%s id=%s", self.config.collection, project_id)
        stored = self.repository.replace_document(
            self.config.collection,
            project_id,
            document,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )
        return _decorate_public_media(stored, base_url=base_url)

    def update_for_owner(
        self,
        project_id: str,
        payload,
        *,
        owner_id: str | None = None,
        owner_email: str | None = None,
        base_url: str | None = None,
    ) -> Dict[str, Any]:
        self._get_project_document_for_owner(project_id, owner_id=owner_id, owner_email=owner_email)
        return self.update(project_id, payload, base_url=base_url)

    def update_status(self, project_id: str, customer_status: str, changed_by: Optional[str], reason: Optional[str], base_url: str | None = None) -> Dict[str, Any]:
        if customer_status == "published":
            self.publish(project_id, changed_by=changed_by, reason=reason, base_url=base_url)
            return self.get(project_id, base_url=base_url)

        current = self._get_project_document(project_id)
        if current["customerStatus"] == customer_status:
            return self._prepare_customer_response(current, base_url=base_url)
        if customer_status == "pending_payment":
            self._validate_ready_for_pending_payment(current)
        current["customerStatus"] = customer_status
        current["updatedAt"] = utc_now_iso()
        append_status_history(current, "customerStatus", changed_by, reason)
        current = normalize_document(current, "customerStatus")
        logger.info("Customer status changed | collection=%s id=%s status=%s", self.config.collection, project_id, customer_status)
        stored = self.repository.replace_document(
            self.config.collection,
            project_id,
            current,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )
        return self._prepare_customer_response(stored, base_url=base_url)

    def update_status_for_owner(
        self,
        project_id: str,
        customer_status: str,
        changed_by: Optional[str],
        reason: Optional[str],
        *,
        owner_id: str | None = None,
        owner_email: str | None = None,
        base_url: str | None = None,
    ) -> Dict[str, Any]:
        self._get_project_document_for_owner(project_id, owner_id=owner_id, owner_email=owner_email)
        return self.update_status(project_id, customer_status, changed_by, reason, base_url=base_url)

    def publish(
        self,
        project_id: str,
        changed_by: Optional[str] = None,
        reason: Optional[str] = None,
        base_url: str | None = None,
        publish_request: PublishRequest | None = None,
    ) -> Dict[str, Any]:
        current = self._get_project_document(project_id)
        self._validate_ready_for_pending_payment(current)
        now = utc_now_iso()
        document = deepcopy(current)
        if document["customerStatus"] != "published":
            document["customerStatus"] = "published"
            append_status_history(document, "customerStatus", changed_by, reason)
        document["updatedAt"] = now
        document = normalize_document(document, "customerStatus")
        document = self.template_service._apply_template_base_price_defaults(document, publish_request=publish_request)
        document = self.commercial_rules.validate_document(document)

        version = self.repository.count_documents(self.config.snapshot_collection, {"sourceId": project_id}) + 1
        snapshot = {
            "id": new_id("snap"),
            "sourceId": project_id,
            "sourceType": self.config.source_type,
            "version": version,
            "slug": document["slug"],
            "publicSlug": document["publicSlug"],
            "snapshot": self._build_snapshot_payload(document, version, now),
            "createdAt": now,
            "publishedAt": now,
        }
        self.repository.insert_document(
            self.config.snapshot_collection,
            snapshot,
            duplicate_message="Ya existe un snapshot con esa version.",
            duplicate_code="DUPLICATED_SNAPSHOT_VERSION",
        )
        document["publishedSnapshotId"] = snapshot["id"]
        document["lastPublishedAt"] = now
        self.repository.replace_document(
            self.config.collection,
            project_id,
            document,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )
        logger.info("Customer project published | collection=%s id=%s snapshot=%s version=%s", self.config.collection, project_id, snapshot["id"], version)
        return _decorate_public_media(snapshot, base_url=base_url)

    def publish_for_owner(
        self,
        project_id: str,
        *,
        owner_id: str | None = None,
        owner_email: str | None = None,
        changed_by: Optional[str] = None,
        reason: Optional[str] = None,
        base_url: str | None = None,
        publish_request: PublishRequest | None = None,
    ) -> Dict[str, Any]:
        self._get_project_document_for_owner(project_id, owner_id=owner_id, owner_email=owner_email)
        return self.publish(
            project_id,
            changed_by=changed_by,
            reason=reason,
            base_url=base_url,
            publish_request=publish_request,
        )

    def get_published_by_slug(self, slug: str, base_url: str | None = None) -> Dict[str, Any]:
        normalized_slug = self._normalize_public_slug(slugify(slug), None)
        if not normalized_slug:
            raise NuvlyError("Experiencia publicada no encontrada.", 404, "PUBLISHED_CUSTOMER_PROJECT_NOT_FOUND")
        document = self.repository.find_document(
            self.config.collection,
            {"publicSlug": normalized_slug, "customerStatus": "published"},
        )
        if not document:
            raise NuvlyError("Experiencia publicada no encontrada.", 404, "PUBLISHED_CUSTOMER_PROJECT_NOT_FOUND")
        snapshot = self.repository.find_document(
            self.config.snapshot_collection,
            {"id": document.get("publishedSnapshotId")},
        )
        ensured = ensure_snapshot(snapshot, "Snapshot publicado no encontrado.", "PUBLISHED_CUSTOMER_PROJECT_NOT_FOUND")
        return _prepare_snapshot_response(ensured, "customerStatus", base_url=base_url)

    def _build_snapshot_payload(self, document: Dict[str, Any], version: int, now: str) -> Dict[str, Any]:
        payload = {
            "id": document["id"],
            "ownerId": document.get("ownerId"),
            "ownerEmail": document.get("ownerEmail"),
            "title": document["title"],
            "slug": document["slug"],
            "publicSlug": document.get("publicSlug"),
            "productType": document["productType"],
            "planTier": document["planTier"],
            "templateCategory": document["templateCategory"],
            "customerStatus": "published",
            "styles": deepcopy(document.get("styles", {})),
            "layout": deepcopy(document.get("layout", {})),
            "blocks": deepcopy(document.get("blocks", [])),
            "pages": deepcopy(document.get("pages", [])),
            "seo": deepcopy(document.get("seo", {})),
            "metadata": deepcopy(document.get("metadata", {})),
            "templateId": document["templateId"],
            "templateSnapshotId": document["templateSnapshotId"],
            "selectionSource": document.get("selectionSource", "catalog"),
            "selectedAt": document.get("selectedAt", document["createdAt"]),
            "externalAuthProvider": document.get("externalAuthProvider"),
            "externalAuthSubject": document.get("externalAuthSubject"),
            "customerData": deepcopy(document.get("customerData", default_customer_data())),
            "payment": deepcopy(document.get("payment", default_payment())),
            "selectedComponentExtras": deepcopy(document.get("selectedComponentExtras", [])),
            "version": version,
            "publishedAt": now,
        }
        if document.get("commercialValidationSkipped"):
            payload["commercialValidationSkipped"] = True
        if self.config.data_field in document:
            payload[self.config.data_field] = deepcopy(document.get(self.config.data_field))
        if self.config.entity_kind == "invitation":
            payload["guests"] = deepcopy(document.get("guests", []))
            payload["rsvpResponses"] = deepcopy(document.get("rsvpResponses", []))
            payload["personalizedMessages"] = deepcopy(document.get("personalizedMessages", []))
        else:
            payload["leadForms"] = deepcopy(document.get("leadForms", []))
            payload["formSubmissions"] = deepcopy(document.get("formSubmissions", []))
            payload["customDomain"] = document.get("customDomain")
        return payload

    def _prepare_customer_response(self, document: Dict[str, Any], base_url: str | None = None) -> Dict[str, Any]:
        normalized = normalize_document(deepcopy(document), "customerStatus")
        return _absolutize_uploaded_media_urls(normalized, _resolve_public_asset_base_url(base_url))
