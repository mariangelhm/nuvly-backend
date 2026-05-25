from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.core.catalog import PlanTier, ProductType, TemplateCategoryCode, VariantLevel

CurrencyCode = Literal["CLP"]
PriceUnit = Literal["component"]
CatalogVariantStatus = Literal["included", "extra", "blocked_by_plan", "blocked_by_category", "inactive", "not_found"]
SummaryVariantStatus = Literal["included", "extra", "blocked"]


class PricingPlanBase(BaseModel):
    code: str = Field(min_length=1, max_length=160)
    productType: ProductType
    tier: PlanTier
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    basePrice: int = Field(ge=0)
    basePriceMonthly: int | None = Field(default=None, ge=0)
    basePriceYearly: int | None = Field(default=None, ge=0)
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
    variantTier: VariantLevel
    active: bool = True
    includedInPlans: List[PlanTier] = Field(default_factory=list)
    canBeExtraInPlans: List[PlanTier] = Field(default_factory=list)
    extraPrice: int = Field(default=0, ge=0)
    currency: CurrencyCode = "CLP"
    sortOrder: int = Field(default=1, ge=0)
    model_config = ConfigDict(extra="allow")


class PricingComponentBase(BaseModel):
    componentCode: str = Field(min_length=1, max_length=160)
    productType: ProductType
    categoryCode: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    active: bool = True
    variants: List[PricingComponentVariant] = Field(default_factory=list)
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


class PricingVariantUpdate(PricingComponentVariant):
    pass


class PricingComponentResponse(PricingComponentBase):
    id: str
    createdAt: str
    updatedAt: str


class PricingSummaryMatrixCell(BaseModel):
    status: SummaryVariantStatus
    label: str
    extraPrice: Optional[int] = None


class PricingSummaryVariant(BaseModel):
    variantCode: str
    name: str
    description: str = ""
    variantTier: VariantLevel
    active: bool = True
    extraPrice: int = 0
    currency: CurrencyCode = "CLP"
    matrix: Dict[str, PricingSummaryMatrixCell] = Field(default_factory=dict)


class PricingSummaryPlan(BaseModel):
    id: str
    code: str
    tier: PlanTier
    name: str
    basePrice: int
    basePriceMonthly: int | None = None
    basePriceYearly: int | None = None
    currency: CurrencyCode
    includedCount: int
    extraCount: int
    blockedCount: int


class PricingSummaryComponent(BaseModel):
    id: str
    componentCode: str
    categoryCode: str
    name: str
    description: str
    active: bool
    variants: List[PricingSummaryVariant] = Field(default_factory=list)


class PricingSummaryResponse(BaseModel):
    productType: ProductType
    plans: List[PricingSummaryPlan] = Field(default_factory=list)
    components: List[PricingSummaryComponent] = Field(default_factory=list)


class TemplateCategoryBase(BaseModel):
    productType: ProductType
    categoryCode: TemplateCategoryCode
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    active: bool = True
    sortOrder: int = Field(default=1, ge=0)
    allowedComponentCodes: List[str] = Field(default_factory=list)


class TemplateCategoryCreate(TemplateCategoryBase):
    pass


class TemplateCategoryUpdate(TemplateCategoryBase):
    pass


class TemplateCategoryActiveUpdate(BaseModel):
    active: bool


class TemplateCategoryResponse(TemplateCategoryBase):
    id: str
    createdAt: str
    updatedAt: str


class CatalogComponentVariantResponse(BaseModel):
    variantCode: str
    name: str
    description: str = ""
    variantTier: VariantLevel
    sortOrder: int = Field(default=1, ge=0)
    status: CatalogVariantStatus
    label: str
    active: bool = True
    extraPrice: int = 0
    currency: CurrencyCode = "CLP"
    locked: bool
    lockReason: str | None = None


class CatalogComponentResponse(BaseModel):
    componentCode: str
    categoryCode: str
    name: str
    description: str = ""
    active: bool = True
    sortOrder: int = Field(default=1, ge=0)
    allowedByCategory: bool
    variants: List[CatalogComponentVariantResponse] = Field(default_factory=list)


class CatalogComponentsResponse(BaseModel):
    productType: ProductType
    templateCategory: TemplateCategoryCode
    planTier: PlanTier
    components: List[CatalogComponentResponse] = Field(default_factory=list)


class SelectedComponentExtraInput(BaseModel):
    componentCode: str = Field(min_length=1, max_length=160)
    variantCode: str = Field(min_length=1, max_length=160)


class PricingCalculateRequest(BaseModel):
    productType: ProductType
    planTier: PlanTier
    templateCategory: TemplateCategoryCode
    selectedComponentExtras: List[SelectedComponentExtraInput] = Field(default_factory=list)
    selectedExtras: List[str] = Field(default_factory=list)
    durationMonths: int = Field(default=12, ge=1)


class PricingBreakdownItem(BaseModel):
    code: str
    label: str
    type: Literal["plan", "component_extra", "general_extra"]
    amount: int


class PricingCalculateResponse(BaseModel):
    currency: CurrencyCode
    basePrice: int
    componentExtrasTotal: int
    extrasTotal: int
    total: int
    breakdown: List[PricingBreakdownItem] = Field(default_factory=list)


class PricingSeedStats(BaseModel):
    insertedPlans: int = 0
    insertedComponents: int = 0
    insertedTemplateCategories: int = 0
    skippedPlans: int = 0
    skippedComponents: int = 0
    skippedTemplateCategories: int = 0
    model_config = ConfigDict(extra="allow")


PlainDocument = Dict[str, Any]
