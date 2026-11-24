"""Admin-only history and restoration of customer website content."""

from copy import deepcopy

from app.core.errors import NuvlyError
from app.core.utils import new_id, utc_now_iso
from app.modules.domain.image_limits import validate_project_media_quota
from app.modules.domain.normalizer import normalize_document
from app.modules.domain.project_support import _decorate_public_media
from app.modules.domain.services import CUSTOMER_WEBSITE_CONFIG, CustomerProjectService


class WebsiteVersionsService:
    CONTENT_FIELDS = (
        "title",
        "styles",
        "layout",
        "blocks",
        "pages",
        "seo",
        "metadata",
        "websiteData",
        "content",
        "templateComponent",
        "selectedComponentExtras",
    )

    def __init__(self, repository=None):
        self.projects = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG, repository=repository)
        self.repository = self.projects.repository
        self.config = CUSTOMER_WEBSITE_CONFIG

    def list_websites(self, search="", limit=20, skip=0):
        return self.repository.list_admin_customer_websites(search.strip(), limit, skip)

    def _project(self, project_id):
        return self.projects._get_project_document(project_id)

    def _snapshot(self, project_id, snapshot_id):
        snapshot = self.repository.find_document(
            self.config.snapshot_collection,
            {
                "id": snapshot_id,
                "sourceId": project_id,
                "sourceType": self.config.source_type,
            },
        )
        if not snapshot or not isinstance(snapshot.get("snapshot"), dict):
            raise NuvlyError("No encontramos esa versión de esta web.", 404, "WEBSITE_VERSION_NOT_FOUND")
        return snapshot

    def history(self, project_id, limit=20, skip=0):
        project = self._project(project_id)
        filters = {"sourceId": project_id, "sourceType": self.config.source_type}
        snapshots = self.repository.find_documents(
            self.config.snapshot_collection, filters, limit=limit, skip=skip, sort_field="version", sort_direction=-1
        )
        items = [
            {
                "id": row["id"],
                "version": row["version"],
                "publishedAt": row.get("publishedAt"),
                "title": row["snapshot"].get("title"),
                "isCurrent": row["id"] == project.get("publishedSnapshotId"),
                "restoration": row.get("restoration"),
            }
            for row in snapshots
        ]
        return {
            "project": {
                **{
                    key: project.get(key)
                    for key in ("id", "title", "ownerEmail", "publicSlug", "customerStatus", "publishedSnapshotId")
                },
                "finalUrl": (project.get("payment") or {}).get("finalUrl"),
            },
            "canRestore": project.get("customerStatus") == "published"
            and (project.get("payment") or {}).get("status") == "paid",
            "items": items,
            "total": self.repository.count_documents(self.config.snapshot_collection, filters),
        }

    def preview(self, project_id, snapshot_id, base_url=None):
        self._project(project_id)
        snapshot = deepcopy(self._snapshot(project_id, snapshot_id))
        # Rendering needs the design and content, not operational or customer records.
        payload = snapshot["snapshot"]
        snapshot["snapshot"] = {key: payload[key] for key in self.CONTENT_FIELDS if key in payload}
        snapshot["snapshot"].update(
            {
                "id": project_id,
                "experienceType": "web",
                "productType": "website",
                "publicSlug": payload.get("publicSlug"),
            }
        )
        return _decorate_public_media(snapshot, base_url=base_url)

    def restore(self, project_id, snapshot_id, expected_snapshot_id, actor, note=""):
        current = self._project(project_id)
        if current.get("customerStatus") != "published" or (current.get("payment") or {}).get("status") != "paid":
            raise NuvlyError(
                "Solo se pueden restaurar webs pagadas que ya estén publicadas.", 409, "WEBSITE_NOT_PUBLISHED"
            )
        if current.get("publishedSnapshotId") != expected_snapshot_id:
            raise NuvlyError(
                "La web cambió. Actualiza el historial antes de restaurar.", 409, "WEBSITE_VERSION_CONFLICT"
            )
        if snapshot_id == expected_snapshot_id:
            raise NuvlyError("Esta versión ya es la publicada.", 409, "WEBSITE_VERSION_ALREADY_CURRENT")
        source = self._snapshot(project_id, snapshot_id)
        document = deepcopy(current)
        for key in self.CONTENT_FIELDS:
            if key in source["snapshot"]:
                document[key] = deepcopy(source["snapshot"][key])
            elif key in ("content", "templateComponent"):
                document[key] = None
        # Historic visual metadata must not revert the customer's current plan/prices.
        for key in ("planTier", "productType", "templateCategory", "basePrice", "basePriceSource"):
            if key in (current.get("metadata") or {}):
                document.setdefault("metadata", {})[key] = current["metadata"][key]
        document = normalize_document(document, "customerStatus")
        document = self.projects.commercial_rules.validate_document(document)
        validate_project_media_quota(document)
        self.projects._validate_ready_for_pending_payment(document)
        now = utc_now_iso()
        restoration = {
            "fromSnapshotId": snapshot_id,
            "fromVersion": source["version"],
            "previousSnapshotId": expected_snapshot_id,
            "actorId": actor["id"],
            "actorName": actor.get("name") or "Administrador",
            "note": note.strip(),
            "at": now,
        }
        version = self.projects._next_publication_version(project_id)
        snapshot = {
            "id": new_id("snap"),
            "sourceId": project_id,
            "sourceType": self.config.source_type,
            "version": version,
            "slug": current["slug"],
            "publicSlug": current["publicSlug"],
            "snapshot": self.projects._build_snapshot_payload(document, version, now),
            "createdAt": now,
            "publishedAt": now,
            "restoration": restoration,
        }
        self.repository.insert_document(
            self.config.snapshot_collection,
            snapshot,
            duplicate_message="La web cambió. Actualiza el historial y vuelve a intentarlo.",
            duplicate_code="WEBSITE_VERSION_CONFLICT",
        )
        changes = {key: deepcopy(document[key]) for key in self.CONTENT_FIELDS if key in document}
        changes.update(publishedSnapshotId=snapshot["id"], lastPublishedAt=now, updatedAt=now)
        event = {
            "status": "published",
            "changedAt": now,
            "changedBy": actor["id"],
            "reason": "admin_version_restored",
            "restoration": restoration,
        }
        try:
            self.repository.restore_customer_website(
                project_id, expected_snapshot_id, changes, event, expected_updated_at=current.get("updatedAt")
            )
        except NuvlyError as error:
            if error.code == "WEBSITE_VERSION_CONFLICT":
                self.repository.discard_unpublished_restore_snapshot(snapshot["id"])
            raise
        return {
            "snapshotId": snapshot["id"],
            "version": version,
            "restoredFromVersion": source["version"],
            "publicSlug": current["publicSlug"],
            "message": "Versión restaurada en el editor y en la página pública.",
        }
