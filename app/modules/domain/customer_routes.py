from fastapi import APIRouter

from app.modules.domain.schemas import (
    CustomerInvitationResponse,
    CustomerInvitationUpdate,
    CustomerProjectCreate,
    CustomerStatusUpdate,
    CustomerWebsiteResponse,
    CustomerWebsiteUpdate,
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


@router.post("/invitations", response_model=CustomerInvitationResponse, status_code=201)
def create_customer_invitation(payload: CustomerProjectCreate):
    return invitation_service.create_from_template(payload)


@router.get("/invitations/{project_id}", response_model=CustomerInvitationResponse)
def get_customer_invitation(project_id: str):
    return invitation_service.get(project_id)


@router.put("/invitations/{project_id}", response_model=CustomerInvitationResponse)
def update_customer_invitation(project_id: str, payload: CustomerInvitationUpdate):
    return invitation_service.update(project_id, payload)


@router.patch("/invitations/{project_id}/status", response_model=CustomerInvitationResponse)
def update_customer_invitation_status(project_id: str, payload: CustomerStatusUpdate):
    return invitation_service.update_status(project_id, payload.customerStatus, payload.changedBy, payload.reason)


@router.post("/invitations/{project_id}/publish", response_model=SnapshotResponse)
def publish_customer_invitation(project_id: str):
    return invitation_service.publish(project_id)


@router.post("/websites", response_model=CustomerWebsiteResponse, status_code=201)
def create_customer_website(payload: CustomerProjectCreate):
    return website_service.create_from_template(payload)


@router.get("/websites/{project_id}", response_model=CustomerWebsiteResponse)
def get_customer_website(project_id: str):
    return website_service.get(project_id)


@router.put("/websites/{project_id}", response_model=CustomerWebsiteResponse)
def update_customer_website(project_id: str, payload: CustomerWebsiteUpdate):
    return website_service.update(project_id, payload)


@router.patch("/websites/{project_id}/status", response_model=CustomerWebsiteResponse)
def update_customer_website_status(project_id: str, payload: CustomerStatusUpdate):
    return website_service.update_status(project_id, payload.customerStatus, payload.changedBy, payload.reason)


@router.post("/websites/{project_id}/publish", response_model=SnapshotResponse)
def publish_customer_website(project_id: str):
    return website_service.publish(project_id)
