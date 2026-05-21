import logging
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

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
from app.modules.experiences.utils import new_id, slugify, utc_now_iso

logger = logging.getLogger(__name__)


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


class TemplateService:
    def __init__(self, config: TemplateConfig, repository: DomainRepository | None = None):
        self.config = config
        self.repository = repository or DomainRepository()

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

    def create(self, payload) -> Dict[str, Any]:
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
        if self.config.data_field not in payload_data:
            document.pop(self.config.data_field, None)
        document["updatedAt"] = now
        append_status_history(document, "templateStatus", None, "initial_draft")
        document = normalize_document(document, "templateStatus")
        self._ensure_slug_available(document["slug"])
        logger.info("Template created | collection=%s id=%s", self.config.collection, document["id"])
        return self.repository.insert_document(self.config.collection, document, self.config.duplicate_message)

    def list(
        self,
        limit: int = 20,
        skip: int = 0,
        template_status: Optional[str] = None,
        category: Optional[str] = None,
        level: Optional[str] = None,
        catalog_visible: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {}
        if template_status:
            filters["templateStatus"] = template_status
        if category:
            filters["metadata.category"] = category
        if level:
            filters["metadata.level"] = level
        if catalog_visible is not None:
            filters["metadata.catalogVisible"] = catalog_visible
        return [self._prepare_template_response(document) for document in self.repository.find_documents(self.config.collection, filters, limit=limit, skip=skip)]

    def get(self, template_id: str) -> Dict[str, Any]:
        document = self.repository.find_document(self.config.collection, {"id": template_id})
        if not document:
            raise NuvlyError(self.config.not_found_message, 404, self.config.not_found_code)
        return self._prepare_template_response(document)

    def update(self, template_id: str, payload) -> Dict[str, Any]:
        current = self.get(template_id)
        now = utc_now_iso()
        document = payload.model_dump(mode="json", exclude_none=True)
        for field in SERVER_MANAGED_TEMPLATE_FIELDS:
            document.pop(field, None)
        document.update(
            {
                "id": current["id"],
                "experienceType": self.config.experience_type,
                "templateStatus": current["templateStatus"],
                "statusHistory": current.get("statusHistory", []),
                "publishedSnapshotId": current.get("publishedSnapshotId"),
                "lastPublishedAt": current.get("lastPublishedAt"),
                "createdAt": current["createdAt"],
                "updatedAt": now,
            }
        )
        document = normalize_document(document, "templateStatus")
        self._ensure_slug_available(document["slug"], current_id=template_id)
        logger.info("Template updated | collection=%s id=%s", self.config.collection, template_id)
        return self.repository.replace_document(
            self.config.collection,
            template_id,
            document,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )

    def update_status(self, template_id: str, template_status: str, changed_by: Optional[str], reason: Optional[str]) -> Dict[str, Any]:
        if template_status == "published":
            self.publish(template_id, changed_by=changed_by, reason=reason)
            return self.get(template_id)

        current = self.get(template_id)
        if current["templateStatus"] == template_status:
            return current
        current["templateStatus"] = template_status
        current["updatedAt"] = utc_now_iso()
        append_status_history(current, "templateStatus", changed_by, reason)
        current = normalize_document(current, "templateStatus")
        logger.info("Template status changed | collection=%s id=%s status=%s", self.config.collection, template_id, template_status)
        return self.repository.replace_document(
            self.config.collection,
            template_id,
            current,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )

    def publish(self, template_id: str, changed_by: Optional[str] = None, reason: Optional[str] = None) -> Dict[str, Any]:
        current = self.get(template_id)
        now = utc_now_iso()
        document = deepcopy(current)
        if document["templateStatus"] != "published":
            document["templateStatus"] = "published"
            append_status_history(document, "templateStatus", changed_by, reason)
        document["updatedAt"] = now
        document = normalize_document(document, "templateStatus")

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
        return snapshot

    def list_public(
        self,
        limit: int = 20,
        skip: int = 0,
        category: Optional[str] = None,
        level: Optional[str] = None,
        tags: Optional[List[str]] = None,
        extra_filter_value: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        filters: Dict[str, Any] = {"templateStatus": "published"}
        if category:
            filters["metadata.category"] = category
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
        return [self._build_public_card(document) for document in documents]

    def get_public_by_slug(self, slug: str) -> Dict[str, Any]:
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
                return snapshot
        if not snapshots:
            raise NuvlyError("Template publico no encontrado.", 404, "PUBLIC_TEMPLATE_NOT_FOUND")
        raise NuvlyError("El slug solicitado no corresponde al snapshot publicado vigente.", 404, "PUBLIC_TEMPLATE_NOT_FOUND")

    def _build_snapshot_payload(self, document: Dict[str, Any], version: int, now: str) -> Dict[str, Any]:
        payload = {
            "id": document["id"],
            "title": document["title"],
            "slug": document["slug"],
            "experienceType": self.config.experience_type,
            "templateStatus": "published",
            "styles": deepcopy(document.get("styles", {})),
            "layout": deepcopy(document.get("layout", {})),
            "blocks": deepcopy(document.get("blocks", [])),
            "seo": deepcopy(document.get("seo", {})),
            "metadata": deepcopy(document.get("metadata", {})),
            "version": version,
            "publishedAt": now,
        }
        if self.config.data_field in document:
            payload[self.config.data_field] = deepcopy(document.get(self.config.data_field))
        return payload

    def _build_public_card(self, document: Dict[str, Any]) -> Dict[str, Any]:
        return {
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

    def _prepare_template_response(self, document: Dict[str, Any]) -> Dict[str, Any]:
        prepared = deepcopy(document)
        prepared["experienceType"] = self.config.experience_type
        return prepared


class CustomerProjectService:
    def __init__(self, config: CustomerConfig, repository: DomainRepository | None = None):
        self.config = config
        self.repository = repository or DomainRepository()
        self.template_service = TemplateService(config.template_config, repository=self.repository)

    def create_from_template(self, payload) -> Dict[str, Any]:
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
            "styles": deepcopy(base_snapshot.get("styles", {})),
            "layout": deepcopy(base_snapshot.get("layout", {})),
            "blocks": deepcopy(base_snapshot.get("blocks", [])),
            "seo": deepcopy(base_snapshot.get("seo", {})),
            "metadata": deepcopy(base_snapshot.get("metadata", {})),
            "templateId": template["id"],
            "templateSnapshotId": template_snapshot["id"],
            "customerData": payload.customerData.model_dump(mode="json"),
            "customerStatus": "temporary",
            "payment": default_payment(),
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

        append_status_history(document, "customerStatus", None, "created_from_template")
        document = normalize_document(document, "customerStatus")
        logger.info("Customer project created | collection=%s id=%s template=%s", self.config.collection, document["id"], template["id"])
        return self.repository.insert_document(self.config.collection, document, self.config.duplicate_message)

    def get(self, project_id: str) -> Dict[str, Any]:
        document = self.repository.find_document(self.config.collection, {"id": project_id})
        if not document:
            raise NuvlyError(self.config.not_found_message, 404, self.config.not_found_code)
        return document

    def update(self, project_id: str, payload) -> Dict[str, Any]:
        current = self.get(project_id)
        now = utc_now_iso()
        document = payload.model_dump(mode="json")
        document.update(
            {
                "id": current["id"],
                "templateId": current["templateId"],
                "templateSnapshotId": current["templateSnapshotId"],
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
        logger.info("Customer project updated | collection=%s id=%s", self.config.collection, project_id)
        return self.repository.replace_document(
            self.config.collection,
            project_id,
            document,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )

    def update_status(self, project_id: str, customer_status: str, changed_by: Optional[str], reason: Optional[str]) -> Dict[str, Any]:
        if customer_status == "published":
            self.publish(project_id, changed_by=changed_by, reason=reason)
            return self.get(project_id)

        current = self.get(project_id)
        if current["customerStatus"] == customer_status:
            return current
        current["customerStatus"] = customer_status
        current["updatedAt"] = utc_now_iso()
        append_status_history(current, "customerStatus", changed_by, reason)
        current = normalize_document(current, "customerStatus")
        logger.info("Customer status changed | collection=%s id=%s status=%s", self.config.collection, project_id, customer_status)
        return self.repository.replace_document(
            self.config.collection,
            project_id,
            current,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )

    def publish(self, project_id: str, changed_by: Optional[str] = None, reason: Optional[str] = None) -> Dict[str, Any]:
        current = self.get(project_id)
        now = utc_now_iso()
        document = deepcopy(current)
        if document["customerStatus"] != "published":
            document["customerStatus"] = "published"
            append_status_history(document, "customerStatus", changed_by, reason)
        document["updatedAt"] = now
        document = normalize_document(document, "customerStatus")

        version = self.repository.count_documents(self.config.snapshot_collection, {"sourceId": project_id}) + 1
        snapshot = {
            "id": new_id("snap"),
            "sourceId": project_id,
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
            project_id,
            document,
            self.config.not_found_message,
            self.config.not_found_code,
            self.config.duplicate_message,
        )
        logger.info("Customer project published | collection=%s id=%s snapshot=%s version=%s", self.config.collection, project_id, snapshot["id"], version)
        return snapshot

    def get_published_by_slug(self, slug: str) -> Dict[str, Any]:
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
                    "customerStatus": "published",
                    "publishedSnapshotId": snapshot["id"],
                },
            )
            if document:
                return snapshot
        if not snapshots:
            raise NuvlyError("Experiencia publicada no encontrada.", 404, "PUBLISHED_CUSTOMER_PROJECT_NOT_FOUND")
        raise NuvlyError("El slug solicitado no corresponde al snapshot publicado vigente.", 404, "PUBLISHED_CUSTOMER_PROJECT_NOT_FOUND")

    def _build_snapshot_payload(self, document: Dict[str, Any], version: int, now: str) -> Dict[str, Any]:
        payload = {
            "id": document["id"],
            "title": document["title"],
            "slug": document["slug"],
            "customerStatus": "published",
            "styles": deepcopy(document.get("styles", {})),
            "layout": deepcopy(document.get("layout", {})),
            "blocks": deepcopy(document.get("blocks", [])),
            "seo": deepcopy(document.get("seo", {})),
            "metadata": deepcopy(document.get("metadata", {})),
            "templateId": document["templateId"],
            "templateSnapshotId": document["templateSnapshotId"],
            "customerData": deepcopy(document.get("customerData", default_customer_data())),
            "payment": deepcopy(document.get("payment", default_payment())),
            "version": version,
            "publishedAt": now,
        }
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
