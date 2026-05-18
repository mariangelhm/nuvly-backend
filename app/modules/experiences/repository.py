from typing import Any, Dict, List, Optional
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from app.core.database import get_database
from app.core.errors import NuvlyError

class ExperienceRepository:
    @property
    def experiences(self):
        return get_database().experiences
    @property
    def snapshots(self):
        return get_database().experience_snapshots
    def insert_experience(self, document: Dict[str, Any]) -> Dict[str, Any]:
        try:
            self.experiences.insert_one(document)
        except DuplicateKeyError:
            raise NuvlyError("Ya existe una experiencia con ese slug y tipo.", 409, "DUPLICATED_SLUG")
        return document
    def list_experiences(self, limit: int = 20, skip: int = 0) -> List[Dict[str, Any]]:
        return list(self.experiences.find({}, {"_id": 0}).sort("updatedAt", -1).skip(skip).limit(limit))
    def get_experience(self, experience_id: str) -> Optional[Dict[str, Any]]:
        return self.experiences.find_one({"id": experience_id}, {"_id": 0})
    def replace_experience(self, experience_id: str, document: Dict[str, Any]) -> Dict[str, Any]:
        try:
            result = self.experiences.replace_one({"id": experience_id}, document)
        except DuplicateKeyError:
            raise NuvlyError("Ya existe una experiencia con ese slug y tipo.", 409, "DUPLICATED_SLUG")
        if result.matched_count == 0:
            raise NuvlyError("Experiencia no encontrada.", 404, "EXPERIENCE_NOT_FOUND")
        return document
    def count_snapshots(self, experience_id: str) -> int:
        return self.snapshots.count_documents({"experienceId": experience_id})
    def insert_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        self.snapshots.insert_one(snapshot)
        return snapshot
    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        return self.snapshots.find_one({"id": snapshot_id}, {"_id": 0})
    def get_published_snapshot_by_slug(self, experience_type: str, slug: str) -> Optional[Dict[str, Any]]:
        experience = self.experiences.find_one({"experienceType": experience_type, "slug": slug, "status": "published"}, {"_id": 0})
        if not experience or not experience.get("publishedSnapshotId"):
            return None
        return self.get_snapshot(experience["publishedSnapshotId"])
