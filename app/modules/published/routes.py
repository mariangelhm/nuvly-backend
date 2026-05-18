from fastapi import APIRouter
from app.modules.experiences.schemas import ExperienceType, SnapshotResponse
from app.modules.experiences.service import ExperienceService

router = APIRouter(prefix="/published", tags=["published"])
service = ExperienceService()

@router.get("/{experience_type}/{slug}", response_model=SnapshotResponse)
def get_published_experience(experience_type: ExperienceType, slug: str):
    return service.get_published(experience_type, slug)
