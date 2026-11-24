from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, computed_field, model_validator

from app.core.catalog import (
    INVITATION_TEMPLATE_CATEGORIES,
    WEBSITE_TEMPLATE_CATEGORIES,
    PlanTier,
    ProductType,
    TemplateCategoryCode,
    VariantLevel,
)
from app.core.value_types import CLPAmount, IsoTimestamp, clp_amount
from app.modules.domain.states import CustomerStatus, PaymentStatus, TemplateStatus


class DataModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class ExperienceWriteModel(DataModel):
    productType: ProductType
    templateCategory: TemplateCategoryCode
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    metadata: Optional[Metadata | Dict[str, JsonValue]] = None

    @model_validator(mode="after")
    def validate_commercial_identity(self) -> Self:
        categories = INVITATION_TEMPLATE_CATEGORIES if self.productType == "invitation" else WEBSITE_TEMPLATE_CATEGORIES
        if self.templateCategory not in categories:
            raise ValueError("La categoría no corresponde al tipo de producto.")
        extras = self.selectedComponentExtras or []
        pairs = [(extra.componentCode, extra.variantCode) for extra in extras]
        if len(pairs) != len(set(pairs)):
            raise ValueError("No se puede seleccionar el mismo extra más de una vez.")
        metadata = self.metadata
        if isinstance(metadata, dict) and "basePrice" in metadata:
            metadata["basePrice"] = clp_amount(metadata["basePrice"])
        return self


class StatusHistoryEntry(DataModel):
    status: str
    changedAt: str
    changedBy: Optional[str] = None
    reason: Optional[str] = None


class TemplateStatusUpdate(DataModel):
    templateStatus: TemplateStatus
    changedBy: Optional[str] = None
    reason: Optional[str] = None


class CustomerStatusUpdate(DataModel):
    customerStatus: CustomerStatus
    changedBy: Optional[str] = None
    reason: Optional[str] = None


class ExperienceBlock(DataModel):
    model_config = ConfigDict(extra="allow")
    id: str
    type: str
    variant: str
    customVariant: Optional[bool] = None
    enabled: bool = True
    order: int = Field(default=1, ge=1)
    props: Dict[str, JsonValue] = Field(default_factory=dict)
    settings: Dict[str, JsonValue] = Field(default_factory=dict)


class Styles(DataModel):
    themeId: Optional[str] = None
    colors: Dict[str, JsonValue] = Field(default_factory=dict)
    typography: Dict[str, JsonValue] = Field(default_factory=dict)
    fonts: Dict[str, JsonValue] = Field(default_factory=dict)
    themeTokens: Dict[str, JsonValue] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow")


class Layout(DataModel):
    sectionOrder: List[str] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")


class Seo(DataModel):
    title: str = ""
    description: str = ""
    noIndex: bool = True


class Metadata(DataModel):
    category: str = ""
    style: str = ""
    purpose: str = ""
    eventType: str = ""
    coverImage: str = ""
    badge: str = ""
    featured: bool = False
    level: VariantLevel = "core"
    basePrice: CLPAmount = 0
    tags: List[str] = Field(default_factory=list)
    catalogVisible: bool = False
    previewVariant: str = ""
    previewStyle: Dict[str, JsonValue] = Field(default_factory=dict)
    linkedPages: List[Dict[str, JsonValue]] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")


class InvitationData(DataModel):
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


class WebsiteData(DataModel):
    businessName: str = ""
    industry: str = ""
    contactEmail: str = ""
    contactPhone: str = ""
    primaryGoal: str = ""
    leadFormEnabled: bool = False
    analyticsEnabled: bool = False


class WebsiteBlock(DataModel):
    id: str
    type: str
    label: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    variant: str
    customVariant: Optional[bool] = None
    enabled: bool = True
    order: int = Field(default=1, ge=1)
    props: Dict[str, JsonValue] = Field(default_factory=dict)
    settings: Dict[str, JsonValue] = Field(default_factory=dict)
    model_config = ConfigDict(extra="allow")


class RestoreWebsiteVersionRequest(DataModel):
    expectedSnapshotId: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)


class PaymentInfo(DataModel):
    finalUrl: Optional[str] = None
    environment: Optional[str] = None
    testMode: bool = False
    paymentId: Optional[str] = None
    status: PaymentStatus = "unpaid"
    provider: Optional[str] = None
    providerPaymentId: Optional[str] = None
    amount: Optional[CLPAmount] = None
    currency: Optional[str] = None
    paidAt: Optional[str] = None


class CustomerData(DataModel):
    name: str = ""
    email: str = ""
    phone: str = ""


class PageSource(DataModel):
    blockId: Optional[str] = None
    blockType: Optional[str] = None
    sourceItemIndex: Optional[int] = None
    sourceChildKey: Optional[str] = None
    model_config = ConfigDict(extra="allow")


class ExperiencePage(DataModel):
    id: str
    kind: Literal["primary", "linked"]
    title: str
    slug: str = ""
    path: str
    parentPageId: Optional[str] = None
    source: PageSource = Field(default_factory=PageSource)
    seo: Dict[str, JsonValue] = Field(default_factory=dict)
    settings: Dict[str, JsonValue] = Field(default_factory=dict)
    blocks: List[Dict[str, JsonValue]] = Field(default_factory=list)
    model_config = ConfigDict(extra="allow")


class SelectedComponentExtra(DataModel):
    componentCode: str = Field(min_length=1, max_length=160)
    variantCode: str = Field(min_length=1, max_length=160)
    extraPrice: CLPAmount = 0


class InvitationTemplateCreate(ExperienceWriteModel):
    experienceType: Literal["invitation"] = "invitation"
    templateComponent: Optional[str] = None
    content: Optional[Dict[str, JsonValue]] = None
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    productType: Literal["invitation"] = "invitation"
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
    model_config = ConfigDict(extra="forbid")


class WebsiteTemplateCreate(ExperienceWriteModel):
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    experienceType: Literal["web"] = "web"
    productType: Literal["website"] = "website"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "corporate"
    styles: Optional[Dict[str, JsonValue]] = None
    layout: Optional[Dict[str, JsonValue]] = None
    blocks: Optional[List[WebsiteBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Dict[str, JsonValue]] = None
    metadata: Optional[Dict[str, JsonValue]] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    model_config = ConfigDict(extra="allow")


class InvitationTemplateUpdate(ExperienceWriteModel):
    expectedUpdatedAt: Optional[IsoTimestamp] = None
    experienceType: Literal["invitation"] = "invitation"
    templateComponent: Optional[str] = None
    content: Optional[Dict[str, JsonValue]] = None
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    productType: Literal["invitation"] = "invitation"
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
    model_config = ConfigDict(extra="forbid")


class WebsiteTemplateUpdate(ExperienceWriteModel):
    expectedUpdatedAt: Optional[IsoTimestamp] = None
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    experienceType: Literal["web"] = "web"
    productType: Literal["website"] = "website"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "corporate"
    styles: Optional[Dict[str, JsonValue]] = None
    layout: Optional[Dict[str, JsonValue]] = None
    blocks: Optional[List[WebsiteBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Dict[str, JsonValue]] = None
    metadata: Optional[Dict[str, JsonValue]] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    model_config = ConfigDict(extra="allow")


class InvitationTemplateResponse(InvitationTemplateUpdate):
    schemaVersion: Literal[1] = 1
    id: str
    templateStatus: TemplateStatus
    statusHistory: List[StatusHistoryEntry] = Field(default_factory=list)
    publishedSnapshotId: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class WebsiteTemplateResponse(WebsiteTemplateUpdate):
    schemaVersion: Literal[1] = 1
    id: str
    templateStatus: TemplateStatus
    statusHistory: List[StatusHistoryEntry] = Field(default_factory=list)
    publishedSnapshotId: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    model_config = ConfigDict(from_attributes=True, extra="allow")

    @computed_field  # type: ignore[prop-decorator]  # Pydantic descriptor is supported at runtime.
    @property
    def status(self) -> TemplateStatus:
        return self.templateStatus


class CustomerProjectCreate(DataModel):
    templateId: str = Field(min_length=1)
    customerData: CustomerData = Field(default_factory=CustomerData)
    selectionSource: str = Field(default="catalog", min_length=1, max_length=80)
    selectedAt: Optional[IsoTimestamp] = None
    externalAuthProvider: Optional[str] = Field(default=None, max_length=80)
    externalAuthSubject: Optional[str] = Field(default=None, max_length=160)


class PublishRequest(DataModel):
    priceMode: Literal["plan_base", "manual"] = "plan_base"
    basePrice: Optional[CLPAmount] = Field(default=None, ge=0)

    def model_post_init(self, __context: Any) -> None:
        if self.priceMode == "manual" and self.basePrice is None:
            raise ValueError("basePrice es requerido cuando priceMode='manual'.")


class CustomerInvitationUpdate(ExperienceWriteModel):
    expectedUpdatedAt: Optional[IsoTimestamp] = None
    experienceType: Literal["invitation"] = "invitation"
    templateComponent: Optional[str] = None
    content: Optional[Dict[str, JsonValue]] = None
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    publicSlug: Optional[str] = Field(default=None, min_length=3, max_length=160)
    productType: Literal["invitation"] = "invitation"
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
    guests: Optional[List[Dict[str, JsonValue]]] = None
    rsvpResponses: Optional[List[Dict[str, JsonValue]]] = None
    personalizedMessages: Optional[List[Dict[str, JsonValue]]] = None
    model_config = ConfigDict(extra="forbid")


class CustomerWebsiteUpdate(ExperienceWriteModel):
    expectedUpdatedAt: Optional[IsoTimestamp] = None
    saveAsDraft: bool = False
    templateComponent: Optional[str] = None
    content: Optional[Dict[str, JsonValue]] = None
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    publicSlug: Optional[str] = Field(default=None, min_length=3, max_length=160)
    productType: Literal["website"] = "website"
    planTier: PlanTier = "plus"
    templateCategory: TemplateCategoryCode = "corporate"
    styles: Optional[Dict[str, JsonValue]] = None
    layout: Optional[Dict[str, JsonValue]] = None
    blocks: Optional[List[ExperienceBlock]] = None
    pages: Optional[List[ExperiencePage]] = None
    seo: Optional[Dict[str, JsonValue]] = None
    metadata: Optional[Dict[str, JsonValue]] = None
    websiteData: Optional[Dict[str, JsonValue]] = None
    customerData: Optional[Dict[str, JsonValue]] = None
    selectedComponentExtras: Optional[List[SelectedComponentExtra]] = None
    commercialValidationSkipped: Optional[bool] = None
    leadForms: Optional[List[Dict[str, JsonValue]]] = None
    formSubmissions: Optional[List[Dict[str, JsonValue]]] = None
    customDomain: Optional[str] = None
    model_config = ConfigDict(extra="ignore")


class CustomerInvitationResponse(CustomerInvitationUpdate):
    schemaVersion: Literal[1] = 1
    imageQuota: Optional[Dict[str, JsonValue]] = None
    videoQuota: Optional[Dict[str, JsonValue]] = None
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
    model_config = ConfigDict(from_attributes=True, extra="allow")


class CustomerWebsiteResponse(CustomerWebsiteUpdate):
    schemaVersion: Literal[1] = 1
    videoQuota: Optional[Dict[str, JsonValue]] = None
    imageQuota: Optional[Dict[str, JsonValue]] = None
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
    model_config = ConfigDict(from_attributes=True, extra="allow")


class CustomerProductSummaryResponse(DataModel):
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
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)
    createdAt: str
    updatedAt: str
    lastPublishedAt: Optional[str] = None


class CustomerProductsResponse(DataModel):
    totalInvitations: int = 0
    totalWebsites: int = 0
    products: List[CustomerProductSummaryResponse] = Field(default_factory=list)
    invitations: List[CustomerProductSummaryResponse] = Field(default_factory=list)
    websites: List[CustomerProductSummaryResponse] = Field(default_factory=list)


class SnapshotResponse(DataModel):
    id: str
    sourceId: str
    sourceType: str
    version: int
    slug: str
    snapshot: Dict[str, JsonValue]
    createdAt: str
    publishedAt: str


class PublicTemplateCardResponse(DataModel):
    id: str
    title: str
    slug: str
    templateStatus: TemplateStatus
    metadata: Dict[str, JsonValue] = Field(default_factory=dict)
    seo: Dict[str, JsonValue] = Field(default_factory=dict)
    updatedAt: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    publishedSnapshotId: Optional[str] = None


class StudioRecentActivityItem(DataModel):
    id: str
    title: str
    subtitle: str
    type: Literal["template", "project", "invitation", "component", "configuration", "customer"]
    createdAt: str


class StudioQuickSummaryResponse(DataModel):
    webTemplates: int = 0
    invitationTemplates: int = 0
    webComponents: int = 0
    invitationComponents: int = 0
    extras: int = 0
    activeUsers: int = 0


class StudioDashboardResponse(DataModel):
    recentActivity: List[StudioRecentActivityItem] = Field(default_factory=list)
    quickSummary: StudioQuickSummaryResponse = Field(default_factory=StudioQuickSummaryResponse)
