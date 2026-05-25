from fastapi import APIRouter, Query

from app.core.catalog import VariantLevel
from app.modules.domain.schemas import (
    InvitationTemplateCreate,
    InvitationTemplateResponse,
    InvitationTemplateUpdate,
    SnapshotResponse,
    TemplateStatus,
    TemplateStatusUpdate,
    WebsiteTemplateCreate,
    WebsiteTemplateResponse,
    WebsiteTemplateUpdate,
)
from app.modules.domain.services import (
    INVITATION_TEMPLATE_CONFIG,
    WEBSITE_TEMPLATE_CONFIG,
    TemplateService,
)

router = APIRouter(prefix="/studio", tags=["studio"])
invitation_service = TemplateService(INVITATION_TEMPLATE_CONFIG)
website_service = TemplateService(WEBSITE_TEMPLATE_CONFIG)


@router.post("/invitation-templates", response_model=InvitationTemplateResponse, status_code=201)
def create_invitation_template(payload: InvitationTemplateCreate):
    return invitation_service.create(payload)


@router.get("/invitation-templates", response_model=list[InvitationTemplateResponse])
def list_invitation_templates(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    templateStatus: TemplateStatus | None = Query(default=None),
    category: str | None = Query(default=None),
    level: VariantLevel | None = Query(default=None),
    catalogVisible: bool | None = Query(default=None),
):
    return invitation_service.list(limit, skip, templateStatus, category, level, catalogVisible)


@router.get("/invitation-templates/{template_id}", response_model=InvitationTemplateResponse)
def get_invitation_template(template_id: str):
    return invitation_service.get(template_id)


@router.put("/invitation-templates/{template_id}", response_model=InvitationTemplateResponse)
def update_invitation_template(template_id: str, payload: InvitationTemplateUpdate):
    return invitation_service.update(template_id, payload)


@router.patch("/invitation-templates/{template_id}/status", response_model=InvitationTemplateResponse)
def update_invitation_template_status(template_id: str, payload: TemplateStatusUpdate):
    return invitation_service.update_status(template_id, payload.templateStatus, payload.changedBy, payload.reason)


@router.post("/invitation-templates/{template_id}/publish", response_model=SnapshotResponse)
def publish_invitation_template(template_id: str):
    return invitation_service.publish(template_id)


@router.post("/invitation-templates/{template_id}/unpublish", response_model=InvitationTemplateResponse)
def unpublish_invitation_template(template_id: str):
    return invitation_service.unpublish(template_id)


@router.post("/website-templates", response_model=WebsiteTemplateResponse, status_code=201)
def create_website_template(payload: WebsiteTemplateCreate):
    return website_service.create(payload)


@router.get("/website-templates", response_model=list[WebsiteTemplateResponse])
def list_website_templates(
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    templateStatus: TemplateStatus | None = Query(default=None),
    category: str | None = Query(default=None),
    level: VariantLevel | None = Query(default=None),
    catalogVisible: bool | None = Query(default=None),
):
    return website_service.list(limit, skip, templateStatus, category, level, catalogVisible)


@router.get("/website-templates/{template_id}", response_model=WebsiteTemplateResponse)
def get_website_template(template_id: str):
    return website_service.get(template_id)


@router.put("/website-templates/{template_id}", response_model=WebsiteTemplateResponse)
def update_website_template(template_id: str, payload: WebsiteTemplateUpdate):
    return website_service.update(template_id, payload)


@router.patch("/website-templates/{template_id}/status", response_model=WebsiteTemplateResponse)
def update_website_template_status(template_id: str, payload: TemplateStatusUpdate):
    return website_service.update_status(template_id, payload.templateStatus, payload.changedBy, payload.reason)


@router.post("/website-templates/{template_id}/publish", response_model=SnapshotResponse)
def publish_website_template(template_id: str):
    return website_service.publish(template_id)


@router.post("/website-templates/{template_id}/unpublish", response_model=WebsiteTemplateResponse)
def unpublish_website_template(template_id: str):
    return website_service.unpublish(template_id)
