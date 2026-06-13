from typing import Optional

from fastapi import APIRouter, Query, Request

from app.core.catalog import VariantLevel
from app.modules.domain.schemas import PublicTemplateCardResponse, SnapshotResponse
from app.modules.domain.services import (
    INVITATION_TEMPLATE_CONFIG,
    WEBSITE_TEMPLATE_CONFIG,
    CUSTOMER_INVITATION_CONFIG,
    CUSTOMER_WEBSITE_CONFIG,
    CustomerProjectService,
    TemplateService,
)

router = APIRouter(prefix="/public", tags=["public"])
invitation_service = TemplateService(INVITATION_TEMPLATE_CONFIG)
website_service = TemplateService(WEBSITE_TEMPLATE_CONFIG)
customer_invitation_service = CustomerProjectService(CUSTOMER_INVITATION_CONFIG)
customer_website_service = CustomerProjectService(CUSTOMER_WEBSITE_CONFIG)


def parse_csv(value: Optional[str]) -> list[str] | None:
    if not value:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return parts or None


@router.get("/invitation-templates", response_model=list[PublicTemplateCardResponse])
def list_public_invitation_templates(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    level: VariantLevel | None = Query(default=None),
    tags: str | None = Query(default=None),
    eventType: str | None = Query(default=None),
):
    return invitation_service.list_public(limit, skip, category, level, parse_csv(tags), eventType, base_url=str(request.base_url).rstrip("/"))


@router.get("/invitation-templates/{slug}", response_model=SnapshotResponse)
def get_public_invitation_template(slug: str, request: Request):
    return invitation_service.get_public_by_slug(slug, base_url=str(request.base_url).rstrip("/"))


@router.get("/website-templates", response_model=list[PublicTemplateCardResponse])
def list_public_website_templates(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    category: str | None = Query(default=None),
    level: VariantLevel | None = Query(default=None),
    tags: str | None = Query(default=None),
    industry: str | None = Query(default=None),
):
    return website_service.list_public(limit, skip, category, level, parse_csv(tags), industry, base_url=str(request.base_url).rstrip("/"))


@router.get("/website-templates/{slug}", response_model=SnapshotResponse)
def get_public_website_template(slug: str, request: Request):
    return website_service.get_public_by_slug(slug, base_url=str(request.base_url).rstrip("/"))


@router.get("/invitations/{publicSlug}", response_model=SnapshotResponse)
def get_public_customer_invitation(publicSlug: str, request: Request):
    return customer_invitation_service.get_published_by_slug(publicSlug, base_url=str(request.base_url).rstrip("/"))


@router.get("/websites/{publicSlug}", response_model=SnapshotResponse)
def get_public_customer_website(publicSlug: str, request: Request):
    return customer_website_service.get_published_by_slug(publicSlug, base_url=str(request.base_url).rstrip("/"))
