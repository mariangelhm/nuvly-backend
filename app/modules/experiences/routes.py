from fastapi import APIRouter, Query
from app.modules.experiences.schemas import ExperienceCreate, ExperienceResponse, ExperienceStatusUpdate, ExperienceUpdate, SnapshotResponse
from app.modules.experiences.service import ExperienceService

router = APIRouter(prefix="/experiences", tags=["experiences"])
service = ExperienceService()

@router.post("", response_model=ExperienceResponse, status_code=201)
def create_experience(payload: ExperienceCreate):
    return service.create(payload)

@router.get("", response_model=list[ExperienceResponse])
def list_experiences(limit: int = Query(default=20, ge=1, le=100), skip: int = Query(default=0, ge=0)):
    return service.list(limit=limit, skip=skip)

@router.get("/{experience_id}", response_model=ExperienceResponse)
def get_experience(experience_id: str):
    return service.get(experience_id)

@router.put("/{experience_id}", response_model=ExperienceResponse)
def update_experience(experience_id: str, payload: ExperienceUpdate):
    return service.update(experience_id, payload)

@router.post("/{experience_id}/publish", response_model=SnapshotResponse)
def publish_experience(experience_id: str):
    return service.publish(experience_id)

@router.patch("/{experience_id}/status", response_model=ExperienceResponse)
def update_experience_status(experience_id: str, payload: ExperienceStatusUpdate):
    return service.update_status(experience_id, payload)
