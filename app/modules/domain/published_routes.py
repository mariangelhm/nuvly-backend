from fastapi import APIRouter, Request

from app.modules.domain.schemas import SnapshotResponse
from app.modules.domain.services import (
    CUSTOMER_INVITATION_CONFIG,
    CUSTOMER_WEBSITE_CONFIG,
    CustomerProjectService,
)

router = APIRouter(prefix="/published", tags=["published"])
invitation_service = CustomerProjectService(CUSTOMER_INVITATION_CONFIG)
website_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG)


@router.get("/invitations/{slug}", response_model=SnapshotResponse)
def get_published_invitation(slug: str, request: Request):
    return invitation_service.get_published_by_slug(slug, base_url=str(request.base_url).rstrip("/"))


@router.get("/websites/{slug}", response_model=SnapshotResponse)
def get_published_website(slug: str, request: Request):
    return website_service.get_published_by_slug(slug, base_url=str(request.base_url).rstrip("/"))
