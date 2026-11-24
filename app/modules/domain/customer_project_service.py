"""Customer project lifecycle, ownership and publication."""

import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from app.core.catalog import (
    DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE,
    normalize_plan_tier,
    normalize_product_type,
    normalize_template_category,
)
from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.core.utils import new_id, slugify, utc_now_iso
from app.modules.domain.commercial_rules import CommercialRulesService
from app.modules.domain.configs import CustomerConfig
from app.modules.domain.defaults import (
    default_customer_data,
    default_invitation_customer_fields,
    default_payment,
    default_website_customer_fields,
)
from app.modules.domain.image_limits import (
    project_video_quota,
    validate_project_media_quota,
    website_image_quota,
)
from app.modules.domain.normalizer import normalize_document
from app.modules.domain.project_support import (
    COMMON_EXPERIENCE_FIELDS,
    PUBLIC_SLUG_PATTERN,
    SERVER_MANAGED_CUSTOMER_METADATA,
    _absolutize_uploaded_media_urls,
    _decorate_public_media,
    _prepare_snapshot_response,
    _resolve_public_asset_base_url,
    append_status_history,
    ensure_snapshot,
)
from app.modules.domain.repository import DomainRepository
from app.modules.domain.schemas import PublishRequest
from app.modules.domain.template_service import TemplateService

logger = logging.getLogger(__name__)


class CustomerProjectService:
    def __init__(self, config: CustomerConfig, repository: DomainRepository | None = None):
        self.config = config
        self.repository = repository or DomainRepository()
        self.template_service = TemplateService(config.template_config, repository=self.repository)
        self.commercial_rules = CommercialRulesService(self.repository)

    def _template_image_source(self, document):
        snapshot_id = document.get("templateSnapshotId")
        snapshot = (
            self.repository.find_document(
                self.config.template_config.snapshot_collection,
                {"id": snapshot_id, "sourceId": document.get("templateId")},
            )
            if snapshot_id
            else None
        )
        return (snapshot or {}).get("snapshot") or {}

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
        if not document or document.get("draftArchivedAt"):
            raise NuvlyError(self.config.not_found_message, 404, self.config.not_found_code)
        return document

    def create_from_template(
        self, payload, base_url: str | None = None, current_user: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        template_id = payload.templateId
        selected_snapshot = None
        # Recover selections saved by older catalog pages that sent the
        # publication ID. Only the template's current public snapshot is valid.
        if template_id.startswith("snap_"):
            selected_snapshot = self.repository.find_document(
                self.config.template_config.snapshot_collection,
                {"id": template_id, "sourceType": self.config.template_config.source_type},
            )
            template_id = selected_snapshot.get("sourceId") if selected_snapshot else None
        template = self.repository.find_document(
            self.config.template_config.collection,
            {"id": template_id, "templateStatus": "published"},
        )
        if not template or (selected_snapshot and template.get("publishedSnapshotId") != selected_snapshot["id"]):
            raise NuvlyError("El template publicado no fue encontrado.", 404, "PUBLISHED_TEMPLATE_NOT_FOUND")
        template_snapshot = self.template_service._get_published_snapshot_from_document(template)
        base_snapshot = template_snapshot["snapshot"]

        if current_user:
            for draft in self._active_owner_documents(current_user.get("id"), current_user.get("email")):
                if draft.get("templateId") == template["id"] and self._is_temporary_draft(draft):
                    return self._prepare_customer_response(draft, base_url=base_url)

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
        for field in ("templateComponent", "content"):
            if field in base_snapshot:
                document[field] = deepcopy(base_snapshot[field])
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
        logger.info(
            "Customer project created | collection=%s id=%s template=%s",
            self.config.collection,
            document["id"],
            template["id"],
        )
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
            raise NuvlyError("El nombre para la URL debe tener al menos 3 caracteres.", 400, "INVALID_PUBLIC_SLUG")
        if not PUBLIC_SLUG_PATTERN.fullmatch(normalized):
            raise NuvlyError(
                "El nombre para la URL solo puede contener letras minúsculas, números y guiones.",
                400,
                "INVALID_PUBLIC_SLUG",
            )
        return normalized

    def _ensure_public_slug_available(self, public_slug: str, current_id: str | None = None) -> None:
        existing = self.repository.find_document(self.config.collection, {"publicSlug": public_slug})
        if existing and existing.get("id") != current_id:
            raise NuvlyError(
                "Esa dirección web ya está en uso. Elige otro nombre para tu URL.", 409, "PUBLIC_SLUG_ALREADY_EXISTS"
            )

    def _validate_ready_for_pending_payment(self, document: Dict[str, Any]) -> None:
        title = (document.get("title") or "").strip()
        if not title:
            raise NuvlyError("El titulo es obligatorio antes de continuar al pago.", 400, "TITLE_REQUIRED")

        public_slug = document.get("publicSlug")
        if not public_slug:
            raise NuvlyError(
                "Falta elegir la dirección de tu web. Vuelve al editor, completa «Nombre para la URL» y guarda los cambios para continuar al pago.",
                400,
                "PUBLIC_SLUG_REQUIRED",
            )

        self._ensure_public_slug_available(public_slug, current_id=document.get("id"))

    @staticmethod
    def _build_owner_filters(owner_id: str | None = None, owner_email: str | None = None) -> Dict[str, Any]:
        return {"ownerId": owner_id} if owner_id else {}

    @staticmethod
    def _is_temporary_draft(document: Dict[str, Any]) -> bool:
        payment = document.get("payment") or {}
        return (
            document.get("customerStatus") == "draft"
            and payment.get("status", "unpaid") == "unpaid"
            and not payment.get("paidAt")
            and not payment.get("providerPaymentId")
            and not document.get("publishedSnapshotId")
            and not document.get("lastPublishedAt")
        )

    def _active_owner_documents(self, owner_id=None, owner_email=None):
        filters = self._build_owner_filters(owner_id=owner_id, owner_email=owner_email)
        if not filters:
            return []
        documents = self.repository.find_documents(self.config.collection, filters, limit=0)
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        active = []
        seen_templates = set()
        for document in documents:
            if document.get("draftArchivedAt"):
                continue
            if not self._is_temporary_draft(document):
                active.append(document)
                continue
            try:
                touched = datetime.fromisoformat(
                    str(document.get("updatedAt") or document.get("createdAt")).replace("Z", "+00:00")
                )
                if touched.tzinfo is None:
                    touched = touched.replace(tzinfo=timezone.utc)
            except TypeError, ValueError:
                # Preserve drafts with an unknown age rather than expire them by guesswork.
                touched = datetime.now(timezone.utc)
            template_id = document.get("templateId")
            expired = touched < cutoff
            duplicate = bool(template_id and template_id in seen_templates)
            if expired or duplicate:
                self.repository.archive_temporary_draft(
                    self.config.collection, document, "expired" if expired else "superseded"
                )
                continue
            if template_id:
                seen_templates.add(template_id)
            active.append(document)
        return active

    def product_page_by_owner(self, owner_id, *, limit=50, skip=0, base_url=None):
        page = self.repository.customer_product_page(self.config.collection, owner_id, limit, skip)
        return {
            "items": [
                self.to_product_summary(self._prepare_customer_response(item, base_url=base_url))
                for item in page["items"]
            ],
            "total": page["total"],
        }

    def list_by_owner(
        self,
        owner_id: str | None = None,
        owner_email: str | None = None,
        *,
        limit: int = 50,
        skip: int = 0,
        base_url: str | None = None,
    ) -> List[Dict[str, Any]]:
        documents = self._active_owner_documents(owner_id, owner_email)
        documents = documents[skip : skip + limit] if limit > 0 else documents[skip:]
        return [self._prepare_customer_response(document, base_url=base_url) for document in documents]

    @staticmethod
    def _owner_matches(document: Dict[str, Any], owner_id: str | None = None, owner_email: str | None = None) -> bool:
        return bool(owner_id and document.get("ownerId") == owner_id)

    def claim_for_verified_owner(self, project_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
        email = str(user.get("email") or "").strip().lower()
        if not user.get("id") or user.get("emailVerified") is not True or not email:
            raise NuvlyError(
                "Verifica tu email antes de recuperar un proyecto anterior.", 403, "VERIFIED_EMAIL_REQUIRED"
            )
        current = self._get_project_document(project_id)
        if current.get("ownerId"):
            return self.get_for_owner(project_id, owner_id=user["id"])
        if str(current.get("ownerEmail") or "").strip().lower() != email:
            raise NuvlyError("No tienes permisos para recuperar este proyecto.", 403, "CUSTOMER_PROJECT_FORBIDDEN")
        return self._prepare_customer_response(
            self.repository.claim_customer_project(
                self.config.collection,
                project_id,
                current.get("ownerEmail"),
                user["id"],
                email,
            )
        )

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
        if self._is_temporary_draft(document):
            self._active_owner_documents(owner_id, owner_email)
            return self._get_project_document(project_id)
        return document

    @staticmethod
    def to_product_summary(document: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": document["id"],
            "schemaVersion": document.get("schemaVersion", 1),
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

    def get_original_format_for_owner(self, project_id, *, owner_id=None, owner_email=None):
        project = self._get_project_document_for_owner(project_id, owner_id=owner_id, owner_email=owner_email)
        snapshot = self.repository.find_document(
            self.config.template_config.snapshot_collection,
            {
                "id": project.get("templateSnapshotId"),
                "sourceId": project.get("templateId"),
                "sourceType": self.config.template_config.source_type,
            },
        )
        if not snapshot or not isinstance(snapshot.get("snapshot"), dict):
            raise NuvlyError(
                "No encontramos el formato original de este template.", 404, "ORIGINAL_TEMPLATE_FORMAT_NOT_FOUND"
            )
        original = snapshot["snapshot"]

        def block_formats(blocks):
            return [
                {"id": block.get("id"), "type": block.get("type"), "settings": deepcopy(block.get("settings") or {})}
                for block in blocks or []
            ]

        return {
            "styles": deepcopy(original.get("styles") or {}),
            "layout": deepcopy(original.get("layout") or {}),
            "blocks": block_formats(original.get("blocks")),
            "pages": [
                {"id": page.get("id"), "blocks": block_formats(page.get("blocks"))}
                for page in original.get("pages") or []
            ],
        }

    def update(self, project_id: str, payload, base_url: str | None = None) -> Dict[str, Any]:
        current = self._get_project_document(project_id)
        now = utc_now_iso()
        document = payload.model_dump(mode="json", exclude_none=True)
        expected = document.pop("expectedUpdatedAt", None)
        if expected is not None and expected != current.get("updatedAt"):
            raise NuvlyError(
                "El proyecto cambió en otra sesión. Recarga antes de guardar.", 409, "PROJECT_VERSION_CONFLICT"
            )
        save_as_draft = document.pop("saveAsDraft", False)
        document = self._merge_missing_customer_fields(current, document)
        metadata = {**(current.get("metadata") or {}), **(document.get("metadata") or {})}
        for field in SERVER_MANAGED_CUSTOMER_METADATA:
            if field in (current.get("metadata") or {}):
                metadata[field] = deepcopy(current["metadata"][field])
            else:
                metadata.pop(field, None)
        document["metadata"] = metadata
        if (current.get("payment") or {}).get("status") == "paid":

            def extra_pairs(items):
                return {(item.get("componentCode"), item.get("variantCode")) for item in items or []}

            if extra_pairs(document.get("selectedComponentExtras")) != extra_pairs(
                current.get("selectedComponentExtras")
            ):
                raise NuvlyError(
                    "Los extras adquiridos requieren un proceso de cambio de plan.", 409, "PAID_EXTRAS_IMMUTABLE"
                )
        for protected_field in ("firstPublishedAt", "subscription"):
            if protected_field in current:
                document[protected_field] = deepcopy(current[protected_field])
            else:
                document.pop(protected_field, None)
        # Only generate publicSlug if explicitly provided in the update payload
        payload_dict = payload.model_dump(mode="json", exclude_none=False)
        if save_as_draft:
            public_slug = current.get("publicSlug")
        elif "publicSlug" in payload_dict and payload_dict["publicSlug"] is not None:
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
                "productType": normalize_product_type(
                    current.get("productType"),
                    default="invitation" if self.config.entity_kind == "invitation" else "website",
                ),
                "planTier": normalize_plan_tier(
                    current.get("planTier"),
                    default=DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE[current.get("productType", "website")],
                ),
                "templateCategory": normalize_template_category(
                    current.get("templateCategory"),
                    product_type=normalize_product_type(
                        current.get("productType"),
                        default="invitation" if self.config.entity_kind == "invitation" else "website",
                    ),
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
        validate_project_media_quota(document)
        logger.info("Customer project updated | collection=%s id=%s", self.config.collection, project_id)
        if self.config.entity_kind == "website" and current["customerStatus"] == "published" and not save_as_draft:
            # Saving an already public customer website also replaces its public version.
            # Validate and insert the snapshot before switching the project's reference,
            # so a failed publication cannot report a successful save.
            self._validate_ready_for_pending_payment(document)
            self._store_publication(document, now, base_url=base_url, expected_updated_at=current.get("updatedAt"))
            return self.get(project_id, base_url=base_url)
        stored = self.repository.replace_document(
            self.config.collection,
            project_id,
            document,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
            expected_updated_at=current.get("updatedAt"),
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
        if payload.expectedUpdatedAt is None:
            raise NuvlyError("Recarga el proyecto para guardar con su versión actual.", 428, "PROJECT_VERSION_REQUIRED")
        return self.update(project_id, payload, base_url=base_url)

    def update_status(
        self,
        project_id: str,
        customer_status: str,
        changed_by: Optional[str],
        reason: Optional[str],
        base_url: str | None = None,
    ) -> Dict[str, Any]:
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
        logger.info(
            "Customer status changed | collection=%s id=%s status=%s",
            self.config.collection,
            project_id,
            customer_status,
        )
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
        if customer_status in {"paid", "payment_failed"}:
            raise NuvlyError(
                "El estado de pago solo puede cambiar mediante el flujo de pagos.", 422, "SERVER_MANAGED_STATUS"
            )
        return self.update_status(project_id, customer_status, owner_id, reason, base_url=base_url)

    def publish(
        self,
        project_id: str,
        changed_by: Optional[str] = None,
        reason: Optional[str] = None,
        base_url: str | None = None,
        publish_request: PublishRequest | None = None,
    ) -> Dict[str, Any]:
        current = self._get_project_document(project_id)
        self._assert_publication_entitlement(current)
        validate_project_media_quota(current)
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
        validate_project_media_quota(document)

        return self._store_publication(document, now, base_url=base_url, expected_updated_at=current.get("updatedAt"))

    def _store_publication(
        self, document: Dict[str, Any], now: str, base_url: str | None = None, *, expected_updated_at=None
    ) -> Dict[str, Any]:
        self._assert_publication_entitlement(document)
        project_id = document["id"]
        version = self._next_publication_version(project_id)
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
        if version == 1:
            document.setdefault("firstPublishedAt", now)
        try:
            self.repository.replace_document(
                self.config.collection,
                project_id,
                document,
                self.config.not_found_message,
                self.config.not_found_code,
                self.config.duplicate_message,
                expected_updated_at=expected_updated_at,
            )
        except NuvlyError as error:
            if error.code == "PROJECT_VERSION_CONFLICT":
                self.repository.discard_unpublished_snapshot(self.config.snapshot_collection, snapshot["id"])
            raise
        logger.info(
            "Customer project published | collection=%s id=%s snapshot=%s version=%s",
            self.config.collection,
            project_id,
            snapshot["id"],
            version,
        )
        return _decorate_public_media(snapshot, base_url=base_url)

    @staticmethod
    def _assert_publication_entitlement(document: Dict[str, Any]) -> None:
        payment = document.get("payment") or {}
        if payment.get("status") != "paid":
            raise NuvlyError("El proyecto requiere un pago verificado antes de publicarse.", 402, "PAYMENT_REQUIRED")
        if get_settings().app_env.lower() in {"production", "prod"} and (
            payment.get("testMode") or payment.get("environment") == "integration"
        ):
            raise NuvlyError(
                "Un pago de prueba no habilita una publicación de producción.", 403, "TEST_PAYMENT_NOT_ALLOWED"
            )

    def _next_publication_version(self, project_id: str) -> int:
        latest = self.repository.find_documents(
            self.config.snapshot_collection, {"sourceId": project_id}, limit=1, sort_field="version", sort_direction=-1
        )
        return int(latest[0]["version"]) + 1 if latest else 1

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
        if publish_request is not None:
            raise NuvlyError(
                "El precio de publicación es administrado por el servidor.", 403, "CUSTOMER_PRICE_OVERRIDE_FORBIDDEN"
            )
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
            "schemaVersion": document.get("schemaVersion", 1),
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
        for field in ("templateComponent", "content"):
            if field in document:
                payload[field] = deepcopy(document[field])
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
        normalized["imageQuota"] = website_image_quota(normalized)
        normalized["videoQuota"] = project_video_quota(normalized)
        return _absolutize_uploaded_media_urls(normalized, _resolve_public_asset_base_url(base_url))
