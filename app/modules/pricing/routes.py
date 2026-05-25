from fastapi import APIRouter, Query

from app.core.catalog import ProductType, VariantLevel
from app.modules.pricing.schemas import (
    PlanTier,
    PricingCalculateRequest,
    PricingCalculateResponse,
    PricingComponentActiveUpdate,
    PricingComponentCreate,
    PricingComponentResponse,
    PricingComponentUpdate,
    PricingPlanActiveUpdate,
    PricingPlanCreate,
    PricingPlanResponse,
    PricingPlanUpdate,
    PricingSeedStats,
    PricingSummaryResponse,
    PricingVariantUpdate,
    PricingVariantActiveUpdate,
)
from app.modules.pricing.service import (
    PricingCalculatorService,
    PricingComponentService,
    PricingPlanService,
    PricingSummaryService,
    ensure_pricing_seed,
)

router = APIRouter(prefix="/pricing", tags=["pricing"])
admin_router = APIRouter(prefix="/admin/pricing", tags=["admin-pricing"])

plan_service = PricingPlanService()
component_service = PricingComponentService()
summary_service = PricingSummaryService()
calculator_service = PricingCalculatorService()


@router.get("/plans", response_model=list[PricingPlanResponse])
def list_pricing_plans(
    productType: ProductType | None = Query(default=None),
    active: bool | None = Query(default=None),
):
    return plan_service.list(product_type=productType, active=active)


@router.get("/plans/{plan_id}", response_model=PricingPlanResponse)
def get_pricing_plan(plan_id: str):
    return plan_service.get(plan_id)


@router.get("/components", response_model=list[PricingComponentResponse])
def list_pricing_components(
    productType: ProductType | None = Query(default=None),
    active: bool | None = Query(default=None),
    tier: PlanTier | None = Query(default=None),
    variantLevel: VariantLevel | None = Query(default=None),
):
    return component_service.list(product_type=productType, active=active, tier=tier, variant_level=variantLevel)


@router.get("/components/{component_id}", response_model=PricingComponentResponse)
def get_pricing_component(component_id: str):
    return component_service.get(component_id)


@router.get("/summary", response_model=PricingSummaryResponse)
def get_pricing_summary(
    productType: ProductType = Query(...),
    includeInactive: bool = Query(default=False),
    variantLevel: VariantLevel | None = Query(default=None),
):
    return summary_service.build_summary(product_type=productType, include_inactive=includeInactive, variant_level=variantLevel)


@router.post("/calculate", response_model=PricingCalculateResponse)
def calculate_pricing(payload: PricingCalculateRequest):
    return calculator_service.calculate(payload)


@admin_router.post("/plans", response_model=PricingPlanResponse, status_code=201)
def create_pricing_plan(payload: PricingPlanCreate):
    return plan_service.create(payload)


@admin_router.put("/plans/{plan_id}", response_model=PricingPlanResponse)
def update_pricing_plan(plan_id: str, payload: PricingPlanUpdate):
    return plan_service.update(plan_id, payload)


@admin_router.patch("/plans/{plan_id}/active", response_model=PricingPlanResponse)
def update_pricing_plan_active(plan_id: str, payload: PricingPlanActiveUpdate):
    return plan_service.update_active(plan_id, payload.active)


@admin_router.post("/components", response_model=PricingComponentResponse, status_code=201)
def create_pricing_component(payload: PricingComponentCreate):
    return component_service.create(payload)


@admin_router.put("/components/{component_id}", response_model=PricingComponentResponse)
def update_pricing_component(component_id: str, payload: PricingComponentUpdate):
    return component_service.update(component_id, payload)


@admin_router.patch("/components/{component_id}/active", response_model=PricingComponentResponse)
def update_pricing_component_active(component_id: str, payload: PricingComponentActiveUpdate):
    return component_service.update_active(component_id, payload.active)


@admin_router.patch("/components/{component_id}/variants/{variantCode}/active", response_model=PricingComponentResponse)
def update_pricing_variant_active(component_id: str, variantCode: str, payload: PricingVariantActiveUpdate):
    return component_service.update_variant_active(component_id, variantCode, payload.active)


@admin_router.patch("/components/{component_id}/variants/{variantCode}", response_model=PricingComponentResponse)
def update_pricing_variant(component_id: str, variantCode: str, payload: PricingVariantUpdate):
    return component_service.update_variant(component_id, variantCode, payload)


@admin_router.post("/seed", response_model=PricingSeedStats)
def seed_pricing_catalog():
    return ensure_pricing_seed()
