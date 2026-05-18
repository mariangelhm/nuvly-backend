import logging
from copy import deepcopy
from typing import Any, Dict, List
from app.core.errors import NuvlyError
from app.modules.experiences.defaults import default_blocks, default_metadata, default_seo, default_styles
from app.modules.experiences.normalizer import normalize_experience
from app.modules.experiences.repository import ExperienceRepository
from app.modules.experiences.schemas import ExperienceCreate, ExperienceStatusUpdate, ExperienceUpdate
from app.modules.experiences.utils import new_id, slugify, utc_now_iso

logger = logging.getLogger(__name__)

class ExperienceService:
    def __init__(self, repository: ExperienceRepository | None = None):
        self.repository = repository or ExperienceRepository()
    def create(self, payload: ExperienceCreate) -> Dict[str, Any]:
        now = utc_now_iso(); blocks = default_blocks(payload.experienceType)
        document = {"id": new_id("exp"), "title": payload.title, "slug": slugify(payload.title), "experienceType": payload.experienceType, "status": "draft", "presetId": payload.presetId, "styles": default_styles(), "layout": {"sectionOrder": [b["id"] for b in blocks]}, "blocks": blocks, "seo": default_seo(payload.title), "metadata": default_metadata(payload.experienceType), "content": None, "publishedSnapshotId": None, "lastPublishedAt": None, "createdAt": now, "updatedAt": now}
        document = normalize_experience(document)
        logger.info("Experience created | id=%s type=%s", document["id"], document["experienceType"])
        return self.repository.insert_experience(document)
    def list(self, limit: int = 20, skip: int = 0) -> List[Dict[str, Any]]:
        return self.repository.list_experiences(limit=min(max(limit, 1), 100), skip=max(skip, 0))
    def get(self, experience_id: str) -> Dict[str, Any]:
        experience = self.repository.get_experience(experience_id)
        if not experience:
            raise NuvlyError("Experiencia no encontrada.", 404, "EXPERIENCE_NOT_FOUND")
        return experience
    def update(self, experience_id: str, payload: ExperienceUpdate) -> Dict[str, Any]:
        current = self.get(experience_id); now = utc_now_iso()
        document = payload.model_dump(mode="json")
        document.update({"id": current["id"], "createdAt": current["createdAt"], "updatedAt": now, "publishedSnapshotId": current.get("publishedSnapshotId"), "lastPublishedAt": current.get("lastPublishedAt")})
        document = normalize_experience(document)
        logger.info("Experience updated | id=%s", experience_id)
        return self.repository.replace_experience(experience_id, document)
    def publish(self, experience_id: str) -> Dict[str, Any]:
        current = self.get(experience_id); now = utc_now_iso()
        document = deepcopy(current); document["status"] = "published"; document["updatedAt"] = now
        document = normalize_experience(document)
        version = self.repository.count_snapshots(experience_id) + 1; snapshot_id = new_id("snap")
        snapshot_payload = {"id": document["id"], "title": document["title"], "slug": document["slug"], "experienceType": document["experienceType"], "status": "published", "presetId": document.get("presetId"), "styles": document.get("styles", {}), "layout": document.get("layout", {}), "blocks": document.get("blocks", []), "seo": document.get("seo", {}), "metadata": document.get("metadata", {}), "content": document.get("content"), "publishedAt": now, "version": version}
        snapshot = {"id": snapshot_id, "experienceId": experience_id, "experienceType": document["experienceType"], "slug": document["slug"], "version": version, "snapshot": snapshot_payload, "createdAt": now, "publishedAt": now}
        self.repository.insert_snapshot(snapshot)
        document["publishedSnapshotId"] = snapshot_id; document["lastPublishedAt"] = now
        self.repository.replace_experience(experience_id, document)
        logger.info("Experience published | id=%s snapshot=%s version=%s", experience_id, snapshot_id, version)
        return snapshot
    def update_status(self, experience_id: str, payload: ExperienceStatusUpdate) -> Dict[str, Any]:
        if payload.status == "published":
            self.publish(experience_id); return self.get(experience_id)
        current = self.get(experience_id); current["status"] = payload.status; current["updatedAt"] = utc_now_iso(); current = normalize_experience(current)
        logger.info("Experience status changed | id=%s status=%s", experience_id, payload.status)
        return self.repository.replace_experience(experience_id, current)
    def get_published(self, experience_type: str, slug: str) -> Dict[str, Any]:
        snapshot = self.repository.get_published_snapshot_by_slug(experience_type, slugify(slug))
        if not snapshot:
            raise NuvlyError("Experiencia pública no encontrada o no publicada.", 404, "PUBLISHED_EXPERIENCE_NOT_FOUND")
        return snapshot
