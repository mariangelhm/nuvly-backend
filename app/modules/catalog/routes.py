from fastapi import APIRouter, Depends, Query

from app.modules.auth.dependencies import get_current_internal_user

from app.core.catalog import PlanTier, ProductType
from app.modules.pricing.schemas import (
    CatalogComponentsResponse,
    TemplateCategoryActiveUpdate,
    TemplateCategoryCreate,
    TemplateCategoryResponse,
    TemplateCategoryUpdate,
)
from app.modules.pricing.service import CatalogService, TemplateCategoryService

router = APIRouter(prefix="/catalog", tags=["catalog"])
admin_router = APIRouter(prefix="/admin/catalog", tags=["admin-catalog"], dependencies=[Depends(get_current_internal_user)])

catalog_service = CatalogService()
template_category_service = TemplateCategoryService()


@router.get("/template-categories", response_model=list[TemplateCategoryResponse])
def list_template_categories(productType: ProductType = Query(...)):
    return catalog_service.list_template_categories(productType)


@router.get("/components", response_model=CatalogComponentsResponse)
def list_catalog_components(
    productType: ProductType = Query(...),
    category: str = Query(...),
    planTier: PlanTier = Query(...),
):
    return catalog_service.list_components_for_catalog(productType, category, planTier)


@admin_router.post("/template-categories", response_model=TemplateCategoryResponse, status_code=201)
def create_template_category(payload: TemplateCategoryCreate):
    return template_category_service.create(payload)


@admin_router.put("/template-categories/{category_id}", response_model=TemplateCategoryResponse)
def update_template_category(category_id: str, payload: TemplateCategoryUpdate):
    return template_category_service.update(category_id, payload)


@admin_router.patch("/template-categories/{category_id}/active", response_model=TemplateCategoryResponse)
def update_template_category_active(category_id: str, payload: TemplateCategoryActiveUpdate):
    return template_category_service.update_active(category_id, payload.active)
