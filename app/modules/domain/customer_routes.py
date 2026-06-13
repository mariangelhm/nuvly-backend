from fastapi import APIRouter, Request

from app.modules.domain.schemas import (
    CustomerInvitationResponse,
    CustomerInvitationUpdate,
    CustomerProjectCreate,
    CustomerStatusUpdate,
    CustomerWebsiteResponse,
    CustomerWebsiteUpdate,
    PublishRequest,
    SnapshotResponse,
)
from app.modules.domain.services import (
    CUSTOMER_INVITATION_CONFIG,
    CUSTOMER_WEBSITE_CONFIG,
    CustomerProjectService,
)

router = APIRouter(prefix="/customer", tags=["customer"])
invitation_service = CustomerProjectService(CUSTOMER_INVITATION_CONFIG)
website_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG)

# TODO MVP: If we need template_viewed/template_clicked metrics later, expose them
# in a separate analytics endpoint such as POST /api/analytics/events instead of
# creating customer projects just for tracking public catalog interactions.


@router.post("/invitations", response_model=CustomerInvitationResponse, status_code=201)
def create_customer_invitation(payload: CustomerProjectCreate):
    return invitation_service.create_from_template(payload)


@router.get("/invitations/{project_id}", response_model=CustomerInvitationResponse)
def get_customer_invitation(project_id: str, request: Request):
    return invitation_service.get(project_id, base_url=str(request.base_url).rstrip("/"))


@router.put("/invitations/{project_id}", response_model=CustomerInvitationResponse)
def update_customer_invitation(project_id: str, payload: CustomerInvitationUpdate, request: Request):
    return invitation_service.update(project_id, payload, base_url=str(request.base_url).rstrip("/"))


@router.patch("/invitations/{project_id}/status", response_model=CustomerInvitationResponse)
def update_customer_invitation_status(project_id: str, payload: CustomerStatusUpdate, request: Request):
    return invitation_service.update_status(
        project_id,
        payload.customerStatus,
        payload.changedBy,
        payload.reason,
        base_url=str(request.base_url).rstrip("/"),
    )


@router.post("/invitations/{project_id}/publish", response_model=SnapshotResponse)
def publish_customer_invitation(project_id: str, request: Request, payload: PublishRequest | None = None):
    return invitation_service.publish(project_id, base_url=str(request.base_url).rstrip("/"), publish_request=payload)


@router.post("/websites", response_model=CustomerWebsiteResponse, status_code=201)
def create_customer_website(payload: CustomerProjectCreate, request: Request):
    return website_service.create_from_template(payload, base_url=str(request.base_url).rstrip("/"))


@router.get("/websites/{project_id}", response_model=CustomerWebsiteResponse)
def get_customer_website(project_id: str, request: Request):
    return website_service.get(project_id, base_url=str(request.base_url).rstrip("/"))


@router.put("/websites/{project_id}", response_model=CustomerWebsiteResponse)
def update_customer_website(project_id: str, payload: CustomerWebsiteUpdate, request: Request):
    return website_service.update(project_id, payload, base_url=str(request.base_url).rstrip("/"))


@router.patch("/websites/{project_id}/status", response_model=CustomerWebsiteResponse)
def update_customer_website_status(project_id: str, payload: CustomerStatusUpdate, request: Request):
    return website_service.update_status(
        project_id,
        payload.customerStatus,
        payload.changedBy,
        payload.reason,
        base_url=str(request.base_url).rstrip("/"),
    )


@router.post("/websites/{project_id}/publish", response_model=SnapshotResponse)
def publish_customer_website(project_id: str, request: Request, payload: PublishRequest | None = None):
    return website_service.publish(project_id, base_url=str(request.base_url).rstrip("/"), publish_request=payload)
