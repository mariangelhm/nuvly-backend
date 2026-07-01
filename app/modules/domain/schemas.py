from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.core.catalog import PlanTier, ProductType, TemplateCategoryCode, VariantLevel

TemplateStatus = Literal["draft", "private_preview", "published", "unpublished", "deprecated", "archived"]
CustomerStatus = Literal["draft", "temporary", "editing", "abandoned", "pending_payment", "payment_failed", "paid", "published", "cancelled"]
PaymentStatus = Literal["unpaid", "pending", "paid", "failed", "refunded"]


class StatusHistoryEntry(BaseModel):
    status: str
    changedAt: str
    changedBy: Optional[str] = None
    reason: Optional[str] = None


class TemplateStatusUpdate(BaseModel):
    templateStatus: TemplateStatus
    changedBy: Optional[str] = None
    reason: Optional[str] = None


class CustomerStatusUpdate(BaseModel):
    customerStatus: CustomerStatus
    changedBy: Optional[str] = None
    reason: Optional[str] = None


class ExperienceBlock(BaseModel):
    id: str
    type: str
    variant: str
    customVariant: Optional[bool] = None
    enabled: bool = True
    order: int = Field(default=1, ge=1)
    props: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)


class Styles(BaseModel):
    themeId: Optional[str] = None
    colors: Dict[str, Any] = Field(default_factory=dict)
    typography: Dict[str, Any] = Field(default_factory=dict)


class Layout(BaseModel):
    sectionOrder: List[str] = Field(default_factory=list)


class Seo(BaseModel):
    title: str = ""
    description: str = ""
    noIndex: bool = True


class Metadata(BaseModel):
    category: str = ""
    style: str = ""
    purpose: str = ""
    eventType: str = ""
    coverImage: str = ""
    badge: str = ""
    featured: bool = False
    level: VariantLevel = "core"
    basePrice: float = 0
    tags: List[str] = Field(default_factory=list)
    catalogVisible: bool = False
    previewVariant: str = ""
    previewStyle: Dict[str, Any] = Field(default_factory=dict)
    linkedPages: List[Dict[str, Any]] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")


class InvitationData(BaseModel):
    eventType: str = "wedding"
    coupleNames: List[str] = Field(default_factory=list)
    eventDate: Optional[str] = None
    venueName: str = ""
    venueAddress: str = ""
    mapUrl: str = ""
    rsvpEnabled: bool = True
    guestLimit: Optional[int] = Field(default=None, ge=1)
    personalizedUrlsEnabled: bool = False
    thankYouMessageEnabled: bool = False


class WebsiteData(BaseModel):
    businessName: str = ""
    industry: str = ""
    contactEmail: str = ""
    contactPhone: str = ""
    primaryGoal: str = ""
    leadFormEnabled: bool = False
    analyticsEnabled: bool = False


class WebsiteBlock(BaseModel):
    id: str
    type: str
    label: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    variant: str
    customVariant: Optional[bool] = None
    enabled: bool = True
    order: int = Field(default=1, ge=1)
    props: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow")


class PaymentInfo(BaseModel):
    status: PaymentStatus = "unpaid"
    provider: Optional[str] = None
    providerPaymentId: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    paidAt: Optional[str] = None


class CustomerData(BaseModel):
    name: str = ""
    email: str = ""
    phone: str = ""


class PageSource(BaseModel):
    blockId: Optional[str] = None
    blockType: Optional[str] = None
    sourceItemIndex: Optional[int] = None
    sourceChildKey: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class ExperiencePage(BaseModel):
    id: str
    kind: str
    title: str
    slug: str = ""
    path: str
    parentPageId: Optional[str] = None
    source: PageSource = Field(default_factory=PageSource)
    seo: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)
    blocks: List[Dict[str, Any]] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")


class SelectedComponentExtra(BaseModel):
    componentCode: str = Field(min_length=1, max_length=160)
    variantCode: str = Field(min_length=1, max_length=160)
    extraPrice: int = Field(default=0, ge=0)


class InvitationTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    productType: ProductType = "invitation"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "wedding"
    styles: Optional[Styles] = None
    layout: Optional[Layout] = None
    blocks: Optional[List[ExperienceBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Seo] = None
    metadata: Optional[Metadata] = None
    invitationData: Optional[InvitationData] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    model_config = ConfigDict(extra="ignore")


class WebsiteTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    experienceType: Literal["web"] = "web"
    productType: ProductType = "website"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "corporate"
    styles: Optional[Dict[str, Any]] = None
    layout: Optional[Dict[str, Any]] = None
    blocks: Optional[List[WebsiteBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    model_config = ConfigDict(extra="allow")


class InvitationTemplateUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    productType: ProductType = "invitation"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "wedding"
    styles: Optional[Styles] = None
    layout: Optional[Layout] = None
    blocks: Optional[List[ExperienceBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Seo] = None
    metadata: Optional[Metadata] = None
    invitationData: Optional[InvitationData] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    model_config = ConfigDict(extra="ignore")


class WebsiteTemplateUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    experienceType: Literal["web"] = "web"
    productType: ProductType = "website"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "corporate"
    styles: Optional[Dict[str, Any]] = None
    layout: Optional[Dict[str, Any]] = None
    blocks: Optional[List[WebsiteBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    model_config = ConfigDict(extra="allow")


class InvitationTemplateResponse(InvitationTemplateUpdate):
    id: str
    templateStatus: TemplateStatus
    statusHistory: List[StatusHistoryEntry] = Field(default_factory=list)
    publishedSnapshotId: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    model_config = ConfigDict(from_attributes=True)


class WebsiteTemplateResponse(WebsiteTemplateUpdate):
    id: str
    templateStatus: TemplateStatus
    statusHistory: List[StatusHistoryEntry] = Field(default_factory=list)
    publishedSnapshotId: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    model_config = ConfigDict(from_attributes=True, extra="allow")

    @computed_field
    @property
    def status(self) -> TemplateStatus:
        return self.templateStatus


class CustomerProjectCreate(BaseModel):
    templateId: str = Field(min_length=1)
    customerData: CustomerData = Field(default_factory=CustomerData)
    selectionSource: str = Field(default="catalog", min_length=1, max_length=80)
    selectedAt: Optional[str] = None
    externalAuthProvider: Optional[str] = Field(default=None, max_length=80)
    externalAuthSubject: Optional[str] = Field(default=None, max_length=160)


class PublishRequest(BaseModel):
    priceMode: Literal["plan_base", "manual"] = "plan_base"
    basePrice: Optional[float] = Field(default=None, ge=0)

    def model_post_init(self, __context: Any) -> None:
        if self.priceMode == "manual" and self.basePrice is None:
            raise ValueError("basePrice es requerido cuando priceMode='manual'.")


class CustomerInvitationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    publicSlug: Optional[str] = Field(default=None, min_length=3, max_length=160)
    productType: ProductType = "invitation"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "wedding"
    styles: Optional[Styles] = None
    layout: Optional[Layout] = None
    blocks: Optional[List[ExperienceBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Seo] = None
    metadata: Optional[Metadata] = None
    invitationData: Optional[InvitationData] = None
    customerData: Optional[CustomerData] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    guests: Optional[List[Dict[str, Any]]] = None
    rsvpResponses: Optional[List[Dict[str, Any]]] = None
    personalizedMessages: Optional[List[Dict[str, Any]]] = None
    model_config = ConfigDict(extra="ignore")


class CustomerWebsiteUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    publicSlug: Optional[str] = Field(default=None, min_length=3, max_length=160)
    productType: ProductType = "website"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "corporate"
    styles: Optional[Styles] = None
    layout: Optional[Layout] = None
    blocks: Optional[List[ExperienceBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Seo] = None
    metadata: Optional[Metadata] = None
    websiteData: Optional[WebsiteData] = None
    customerData: Optional[CustomerData] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    leadForms: Optional[List[Dict[str, Any]]] = None
    formSubmissions: Optional[List[Dict[str, Any]]] = None
    customDomain: Optional[str] = None
    model_config = ConfigDict(extra="ignore")


class CustomerInvitationResponse(CustomerInvitationUpdate):
    id: str
    ownerId: Optional[str] = None
    ownerEmail: Optional[str] = None
    templateId: str
    templateSnapshotId: str
    selectionSource: str = "catalog"
    selectedAt: str
    externalAuthProvider: Optional[str] = None
    externalAuthSubject: Optional[str] = None
    customerStatus: CustomerStatus
    payment: PaymentInfo = Field(default_factory=PaymentInfo)
    statusHistory: List[StatusHistoryEntry] = Field(default_factory=list)
    publishedSnapshotId: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    model_config = ConfigDict(from_attributes=True)


class CustomerWebsiteResponse(CustomerWebsiteUpdate):
    id: str
    ownerId: Optional[str] = None
    ownerEmail: Optional[str] = None
    templateId: str
    templateSnapshotId: str
    selectionSource: str = "catalog"
    selectedAt: str
    externalAuthProvider: Optional[str] = None
    externalAuthSubject: Optional[str] = None
    customerStatus: CustomerStatus
    payment: PaymentInfo = Field(default_factory=PaymentInfo)
    statusHistory: List[StatusHistoryEntry] = Field(default_factory=list)
    publishedSnapshotId: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    model_config = ConfigDict(from_attributes=True)


class CustomerProductSummaryResponse(BaseModel):
    id: str
    title: str
    productType: ProductType
    planTier: PlanTier
    templateCategory: TemplateCategoryCode
    customerStatus: CustomerStatus
    publicSlug: Optional[str] = None
    ownerId: Optional[str] = None
    ownerEmail: Optional[str] = None
    templateId: str
    templateSnapshotId: str
    selectionSource: str = "catalog"
    selectedAt: str
    payment: PaymentInfo = Field(default_factory=PaymentInfo)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    createdAt: str
    updatedAt: str
    lastPublishedAt: Optional[str] = None


class CustomerProductsResponse(BaseModel):
    products: List[CustomerProductSummaryResponse] = Field(default_factory=list)
    invitations: List[CustomerInvitationResponse] = Field(default_factory=list)
    websites: List[CustomerWebsiteResponse] = Field(default_factory=list)


class SnapshotResponse(BaseModel):
    id: str
    sourceId: str
    sourceType: str
    version: int
    slug: str
    snapshot: Dict[str, Any]
    createdAt: str
    publishedAt: str


class PublicTemplateCardResponse(BaseModel):
    id: str
    title: str
    slug: str
    templateStatus: TemplateStatus
    metadata: Dict[str, Any] = Field(default_factory=dict)
    seo: Dict[str, Any] = Field(default_factory=dict)
    updatedAt: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    publishedSnapshotId: Optional[str] = None


class StudioRecentActivityItem(BaseModel):
    id: str
    title: str
    subtitle: str
    type: Literal["template", "project", "invitation", "component", "configuration", "customer"]
    createdAt: str


class StudioQuickSummaryResponse(BaseModel):
    webTemplates: int = 0
    invitationTemplates: int = 0
    webComponents: int = 0
    invitationComponents: int = 0
    extras: int = 0
    activeUsers: int = 0


class StudioDashboardResponse(BaseModel):
    recentActivity: List[StudioRecentActivityItem] = Field(default_factory=list)
    quickSummary: StudioQuickSummaryResponse = Field(default_factory=StudioQuickSummaryResponse)
