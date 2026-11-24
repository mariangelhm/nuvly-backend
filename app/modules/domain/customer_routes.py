from fastapi import APIRouter, Depends, Query, Request

from app.core.rate_limits import consume_rate_limit
from app.modules.auth.dependencies import get_current_user, get_current_user_optional
from app.modules.domain.schemas import (
    CustomerInvitationResponse,
    CustomerInvitationUpdate,
    CustomerProductsResponse,
    CustomerProductSummaryResponse,
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


@router.post("/invitations/{project_id}/claim", response_model=CustomerInvitationResponse)
def claim_customer_invitation(project_id: str, current_user: dict = Depends(get_current_user)):
    return invitation_service.claim_for_verified_owner(project_id, current_user)


@router.post("/websites/{project_id}/claim", response_model=CustomerWebsiteResponse)
def claim_customer_website(project_id: str, current_user: dict = Depends(get_current_user)):
    return website_service.claim_for_verified_owner(project_id, current_user)


# TODO MVP: If we need template_viewed/template_clicked metrics later, expose them
# in a separate analytics endpoint such as POST /api/analytics/events instead of
# creating customer projects just for tracking public catalog interactions.


@router.get("/products", response_model=CustomerProductsResponse)
def list_customer_products(
    request: Request,
    current_user: dict = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
):
    base_url = str(request.base_url).rstrip("/")
    invitation_page = invitation_service.product_page_by_owner(
        owner_id=current_user.get("id"),
        limit=limit,
        skip=skip,
        base_url=base_url,
    )
    website_page = website_service.product_page_by_owner(
        owner_id=current_user.get("id"),
        limit=limit,
        skip=skip,
        base_url=base_url,
    )
    invitations, websites = invitation_page["items"], website_page["items"]
    total_invitations, total_websites = invitation_page["total"], website_page["total"]
    products = [
        CustomerProductSummaryResponse.model_validate(CustomerProjectService.to_product_summary(document))
        for document in sorted(
            [*invitations, *websites],
            key=lambda item: item.get("id", ""),
        )
    ]
    products.sort(key=lambda item: item.updatedAt, reverse=True)
    return CustomerProductsResponse(
        products=products,
        invitations=invitations,
        websites=websites,
        totalInvitations=total_invitations,
        totalWebsites=total_websites,
    )


@router.post("/invitations", response_model=CustomerInvitationResponse, status_code=201)
def create_customer_invitation(
    payload: CustomerProjectCreate, current_user: dict | None = Depends(get_current_user_optional)
):
    if current_user:
        consume_rate_limit("project-create-owner", current_user["id"], 10, 60)
    return invitation_service.create_from_template(payload, current_user=current_user)


@router.get("/invitations", response_model=list[CustomerInvitationResponse])
def list_customer_invitations(
    request: Request,
    current_user: dict = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
):
    return invitation_service.list_by_owner(
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        limit=limit,
        skip=skip,
        base_url=str(request.base_url).rstrip("/"),
    )


@router.get("/invitations/{project_id}", response_model=CustomerInvitationResponse)
def get_customer_invitation(project_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    return invitation_service.get_for_owner(
        project_id,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        base_url=str(request.base_url).rstrip("/"),
    )


@router.put("/invitations/{project_id}", response_model=CustomerInvitationResponse)
def update_customer_invitation(
    project_id: str,
    payload: CustomerInvitationUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return invitation_service.update_for_owner(
        project_id,
        payload,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        base_url=str(request.base_url).rstrip("/"),
    )


@router.patch("/invitations/{project_id}/status", response_model=CustomerInvitationResponse)
def update_customer_invitation_status(
    project_id: str,
    payload: CustomerStatusUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return invitation_service.update_status_for_owner(
        project_id,
        payload.customerStatus,
        payload.changedBy,
        payload.reason,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        base_url=str(request.base_url).rstrip("/"),
    )


@router.post("/invitations/{project_id}/publish", response_model=SnapshotResponse)
def publish_customer_invitation(
    project_id: str,
    request: Request,
    payload: PublishRequest | None = None,
    current_user: dict = Depends(get_current_user),
):
    return invitation_service.publish_for_owner(
        project_id,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        base_url=str(request.base_url).rstrip("/"),
        publish_request=payload,
    )


@router.post("/websites", response_model=CustomerWebsiteResponse, status_code=201)
def create_customer_website(
    payload: CustomerProjectCreate,
    request: Request,
    current_user: dict | None = Depends(get_current_user_optional),
):
    if current_user:
        consume_rate_limit("project-create-owner", current_user["id"], 10, 60)
    return website_service.create_from_template(
        payload, base_url=str(request.base_url).rstrip("/"), current_user=current_user
    )


@router.get("/websites", response_model=list[CustomerWebsiteResponse])
def list_customer_websites(
    request: Request,
    current_user: dict = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
):
    return website_service.list_by_owner(
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        limit=limit,
        skip=skip,
        base_url=str(request.base_url).rstrip("/"),
    )


@router.get("/websites/{project_id}", response_model=CustomerWebsiteResponse)
def get_customer_website(project_id: str, request: Request, current_user: dict = Depends(get_current_user)):
    return website_service.get_for_owner(
        project_id,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        base_url=str(request.base_url).rstrip("/"),
    )


@router.get("/websites/{project_id}/original-format")
def get_customer_website_original_format(project_id: str, current_user: dict = Depends(get_current_user)):
    return website_service.get_original_format_for_owner(
        project_id,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
    )


@router.put("/websites/{project_id}", response_model=CustomerWebsiteResponse)
def update_customer_website(
    project_id: str,
    payload: CustomerWebsiteUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return website_service.update_for_owner(
        project_id,
        payload,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        base_url=str(request.base_url).rstrip("/"),
    )


@router.patch("/websites/{project_id}/status", response_model=CustomerWebsiteResponse)
def update_customer_website_status(
    project_id: str,
    payload: CustomerStatusUpdate,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    return website_service.update_status_for_owner(
        project_id,
        payload.customerStatus,
        payload.changedBy,
        payload.reason,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        base_url=str(request.base_url).rstrip("/"),
    )


@router.post("/websites/{project_id}/publish", response_model=SnapshotResponse)
def publish_customer_website(
    project_id: str,
    request: Request,
    payload: PublishRequest | None = None,
    current_user: dict = Depends(get_current_user),
):
    return website_service.publish_for_owner(
        project_id,
        owner_id=current_user.get("id"),
        owner_email=current_user.get("email"),
        base_url=str(request.base_url).rstrip("/"),
        publish_request=payload,
    )
