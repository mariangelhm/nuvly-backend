"""Template lifecycle: creation, editing and publication."""

import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional

from app.core.catalog import (
    DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE,
    PlanTier,
    ProductType,
    VariantLevel,
    normalize_plan_tier,
    normalize_product_type,
    normalize_template_category,
)
from app.core.errors import NuvlyError
from app.core.utils import new_id, slugify, utc_now_iso
from app.core.value_types import clp_amount
from app.modules.domain.commercial_rules import CommercialRulesService
from app.modules.domain.configs import TemplateConfig
from app.modules.domain.defaults import default_template_document
from app.modules.domain.normalizer import normalize_document
from app.modules.domain.project_support import (
    COMMON_EXPERIENCE_FIELDS,
    SERVER_MANAGED_TEMPLATE_FIELDS,
    _absolutize_uploaded_media_urls,
    _decorate_public_media,
    _prepare_snapshot_response,
    _resolve_public_asset_base_url,
    append_status_history,
)
from app.modules.domain.public_projection import public_metadata
from app.modules.domain.repository import DomainRepository
from app.modules.domain.schemas import PublishRequest
from app.modules.pricing.service import PricingPlanService

logger = logging.getLogger(__name__)


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
        if not document or document.get("draftArchivedAt"):
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

    def _resolve_plan_base_price(self, product_type: ProductType, plan_tier: PlanTier) -> int:
        pricing_plan_service = PricingPlanService(repository=self.repository)  # type: ignore[arg-type]
        try:
            plan = pricing_plan_service.find_by_tier(product_type, plan_tier)
            return clp_amount(plan.get("basePrice", 0) or 0)
        except ValueError as error:
            raise NuvlyError("El plan tiene una tarifa CLP inválida.", 422, "INVALID_CLP_AMOUNT") from error
        except NuvlyError:
            logger.warning(
                "Pricing plan not found while resolving basePrice | productType=%s planTier=%s",
                product_type,
                plan_tier,
            )
            return 0

    def _apply_template_base_price_defaults(
        self, document: Dict[str, Any], publish_request: PublishRequest | None = None
    ) -> Dict[str, Any]:
        metadata = document.get("metadata") or {}
        base_price_source = metadata.get("basePriceSource")
        current_base_price = metadata.get("basePrice")
        plan_base_price = self._resolve_plan_base_price(document["productType"], document["planTier"])

        if publish_request is not None:
            if publish_request.priceMode == "manual":
                metadata["basePrice"] = clp_amount(publish_request.basePrice or 0)
                metadata["basePriceSource"] = "manual"
            else:
                metadata["basePrice"] = plan_base_price
                metadata["basePriceSource"] = "plan_base"
            document["metadata"] = metadata
            return document

        if (
            base_price_source == "plan_base"
            or current_base_price is None
            or (float(current_base_price) == 0 and base_price_source != "manual")
        ):
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
        product_type = normalize_product_type(
            document.get("productType"), default="invitation" if self.config.entity_kind == "invitation" else "website"
        )
        document["productType"] = product_type
        document["planTier"] = normalize_plan_tier(
            document.get("planTier"), default=DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE[product_type]
        )
        document["templateCategory"] = normalize_template_category(
            document.get("templateCategory"), product_type=product_type
        )
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
        return [
            self._prepare_template_response(document, base_url=base_url)
            for document in self.repository.find_documents(self.config.collection, filters, limit=limit, skip=skip)
        ]

    def get(self, template_id: str, base_url: str | None = None) -> Dict[str, Any]:
        return self._prepare_template_response(self._get_template_document(template_id), base_url=base_url)

    def update(self, template_id: str, payload, base_url: str | None = None) -> Dict[str, Any]:
        current = self._get_template_document(template_id)
        now = utc_now_iso()
        document = payload.model_dump(mode="json", exclude_none=True)
        expected = document.pop("expectedUpdatedAt", None)
        if expected is not None and expected != current.get("updatedAt"):
            raise NuvlyError(
                "El template cambió en otra sesión. Recarga antes de guardar.", 409, "PROJECT_VERSION_CONFLICT"
            )
        for field in SERVER_MANAGED_TEMPLATE_FIELDS:
            document.pop(field, None)
        document = self._merge_missing_template_fields(current, document)
        document.update(
            {
                "id": current["id"],
                "experienceType": self.config.experience_type,
                "productType": normalize_product_type(
                    current.get("productType"),
                    default="invitation" if self.config.entity_kind == "invitation" else "website",
                ),
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
            expected_updated_at=current.get("updatedAt"),
        )
        return _decorate_public_media(stored, base_url=base_url)

    def update_status(
        self,
        template_id: str,
        template_status: str,
        changed_by: Optional[str],
        reason: Optional[str],
        base_url: str | None = None,
    ) -> Dict[str, Any]:
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
        logger.info(
            "Template status changed | collection=%s id=%s status=%s",
            self.config.collection,
            template_id,
            template_status,
        )
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

        latest = self.repository.find_documents(
            self.config.snapshot_collection, {"sourceId": template_id}, limit=1, sort_field="version", sort_direction=-1
        )
        version = int(latest[0]["version"]) + 1 if latest else 1
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
        try:
            self.repository.replace_document(
                self.config.collection,
                template_id,
                document,
                self.config.not_found_message,
                self.config.not_found_code,
                self.config.duplicate_message,
                expected_updated_at=current.get("updatedAt"),
            )
        except NuvlyError as error:
            if error.code == "PROJECT_VERSION_CONFLICT":
                self.repository.discard_unpublished_snapshot(self.config.snapshot_collection, snapshot["id"])
            raise
        logger.info(
            "Template published | collection=%s id=%s snapshot=%s version=%s",
            self.config.collection,
            template_id,
            snapshot["id"],
            version,
        )
        return _decorate_public_media(snapshot, base_url=base_url)

    def unpublish(
        self, template_id: str, changed_by: Optional[str] = None, reason: Optional[str] = "unpublish_template"
    ) -> Dict[str, Any]:
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
        raise NuvlyError(
            "El slug solicitado no corresponde al snapshot publicado vigente.", 404, "PUBLIC_TEMPLATE_NOT_FOUND"
        )

    def _build_snapshot_payload(self, document: Dict[str, Any], version: int, now: str) -> Dict[str, Any]:
        payload = {
            "id": document["id"],
            "schemaVersion": document.get("schemaVersion", 1),
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
        for field in ("templateComponent", "content"):
            if field in document:
                payload[field] = deepcopy(document[field])
        if self.config.data_field in document:
            payload[self.config.data_field] = deepcopy(document.get(self.config.data_field))
        return payload

    def _build_public_card(self, document: Dict[str, Any], base_url: str | None = None) -> Dict[str, Any]:
        card = {
            "id": document["id"],
            "schemaVersion": document.get("schemaVersion", 1),
            "title": document.get("title", ""),
            "slug": document.get("slug", ""),
            "templateStatus": document.get("templateStatus", "published"),
            "metadata": public_metadata(document.get("metadata") or {}),
            "seo": deepcopy(document.get("seo", {})),
            "updatedAt": document.get("updatedAt"),
            "lastPublishedAt": document.get("lastPublishedAt"),
            "publishedSnapshotId": document.get("publishedSnapshotId"),
        }
        return _absolutize_uploaded_media_urls(card, _resolve_public_asset_base_url(base_url))

    def _get_published_snapshot_from_document(
        self, document: Dict[str, Any], raise_on_missing: bool = True
    ) -> Optional[Dict[str, Any]]:
        snapshot_id = document.get("publishedSnapshotId")
        if not snapshot_id:
            if raise_on_missing:
                raise NuvlyError(
                    "El template publicado no tiene snapshot asociado.", 409, "PUBLISHED_TEMPLATE_WITHOUT_SNAPSHOT"
                )
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
