from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


ProductType = Literal["website", "invitation"]
PlanTier = Literal["essential", "plus", "pro", "custom"]
CurrencyCode = Literal["CLP"]
PriceUnit = Literal["component"]


class PricingPlanBase(BaseModel):
    code: str = Field(min_length=1, max_length=160)
    productType: ProductType
    tier: PlanTier
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    basePrice: int = Field(ge=0)
    durationMonths: int = Field(ge=0)
    currency: CurrencyCode = "CLP"
    active: bool = True
    sortOrder: int = Field(default=1, ge=0)


class PricingPlanCreate(PricingPlanBase):
    pass


class PricingPlanUpdate(PricingPlanBase):
    pass


class PricingPlanActiveUpdate(BaseModel):
    active: bool


class PricingPlanResponse(PricingPlanBase):
    id: str
    createdAt: str
    updatedAt: str


class PricingComponentVariant(BaseModel):
    variantCode: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    active: bool = True
    model_config = ConfigDict(extra="allow")


class PricingComponentBase(BaseModel):
    componentCode: str = Field(min_length=1, max_length=160)
    productType: ProductType
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    active: bool = True
    variants: List[PricingComponentVariant] = Field(default_factory=list)
    includedInPlans: List[PlanTier] = Field(default_factory=list)
    canBeExtraInPlans: List[PlanTier] = Field(default_factory=list)
    extraPrice: int = Field(ge=0)
    currency: CurrencyCode = "CLP"
    unit: PriceUnit = "component"
    sortOrder: int = Field(default=1, ge=0)
    model_config = ConfigDict(extra="allow")


class PricingComponentCreate(PricingComponentBase):
    pass


class PricingComponentUpdate(PricingComponentBase):
    pass


class PricingComponentActiveUpdate(BaseModel):
    active: bool


class PricingVariantActiveUpdate(BaseModel):
    active: bool


class PricingComponentResponse(PricingComponentBase):
    id: str
    createdAt: str
    updatedAt: str


class PricingCatalogSummary(BaseModel):
    plans: List[PricingPlanResponse] = Field(default_factory=list)
    components: List[PricingComponentResponse] = Field(default_factory=list)


class PricingSummaryMatrixCell(BaseModel):
    status: Literal["included", "extra", "blocked"]
    label: str
    extraPrice: Optional[int] = None


class PricingSummaryPlan(BaseModel):
    id: str
    code: str
    tier: PlanTier
    name: str
    basePrice: int
    currency: CurrencyCode
    includedCount: int
    extraCount: int
    blockedCount: int


class PricingSummaryComponent(BaseModel):
    id: str
    componentCode: str
    name: str
    description: str
    active: bool
    variantsCount: int
    activeVariantsCount: int
    matrix: Dict[str, PricingSummaryMatrixCell] = Field(default_factory=dict)


class PricingSummaryResponse(BaseModel):
    productType: ProductType
    plans: List[PricingSummaryPlan] = Field(default_factory=list)
    components: List[PricingSummaryComponent] = Field(default_factory=list)


class PricingSeedStats(BaseModel):
    insertedPlans: int = 0
    insertedComponents: int = 0
    skippedPlans: int = 0
    skippedComponents: int = 0
    model_config = ConfigDict(extra="allow")


PlainDocument = Dict[str, Any]
