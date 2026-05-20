from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


TemplateStatus = Literal["draft", "private_preview", "published", "archived"]
CustomerStatus = Literal["temporary", "editing", "abandoned", "pending_payment", "paid", "published", "cancelled"]
PaymentStatus = Literal["unpaid", "pending", "paid", "refunded"]


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
    level: str = "basic"
    basePrice: float = 0
    tags: List[str] = Field(default_factory=list)
    catalogVisible: bool = False
    previewVariant: str = ""
    previewStyle: Dict[str, Any] = Field(default_factory=dict)


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


class InvitationTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    styles: Optional[Styles] = None
    layout: Optional[Layout] = None
    blocks: Optional[List[ExperienceBlock]] = None
    seo: Optional[Seo] = None
    metadata: Optional[Metadata] = None
    invitationData: Optional[InvitationData] = None
    model_config = ConfigDict(extra="ignore")


class WebsiteTemplateCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: Optional[str] = Field(default=None, min_length=1, max_length=160)
    styles: Optional[Styles] = None
    layout: Optional[Layout] = None
    blocks: Optional[List[ExperienceBlock]] = None
    seo: Optional[Seo] = None
    metadata: Optional[Metadata] = None
    websiteData: Optional[WebsiteData] = None
    model_config = ConfigDict(extra="ignore")


class InvitationTemplateUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    styles: Styles = Field(default_factory=Styles)
    layout: Layout = Field(default_factory=Layout)
    blocks: List[ExperienceBlock] = Field(default_factory=list)
    seo: Seo = Field(default_factory=Seo)
    metadata: Metadata = Field(default_factory=Metadata)
    invitationData: InvitationData = Field(default_factory=InvitationData)


class WebsiteTemplateUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    styles: Styles = Field(default_factory=Styles)
    layout: Layout = Field(default_factory=Layout)
    blocks: List[ExperienceBlock] = Field(default_factory=list)
    seo: Seo = Field(default_factory=Seo)
    metadata: Metadata = Field(default_factory=Metadata)
    websiteData: WebsiteData = Field(default_factory=WebsiteData)


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
    model_config = ConfigDict(from_attributes=True)


class CustomerProjectCreate(BaseModel):
    templateId: str = Field(min_length=1)
    customerData: CustomerData = Field(default_factory=CustomerData)


class CustomerInvitationUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    styles: Styles = Field(default_factory=Styles)
    layout: Layout = Field(default_factory=Layout)
    blocks: List[ExperienceBlock] = Field(default_factory=list)
    seo: Seo = Field(default_factory=Seo)
    metadata: Metadata = Field(default_factory=Metadata)
    invitationData: InvitationData = Field(default_factory=InvitationData)
    customerData: CustomerData = Field(default_factory=CustomerData)
    guests: List[Dict[str, Any]] = Field(default_factory=list)
    rsvpResponses: List[Dict[str, Any]] = Field(default_factory=list)
    personalizedMessages: List[Dict[str, Any]] = Field(default_factory=list)


class CustomerWebsiteUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    styles: Styles = Field(default_factory=Styles)
    layout: Layout = Field(default_factory=Layout)
    blocks: List[ExperienceBlock] = Field(default_factory=list)
    seo: Seo = Field(default_factory=Seo)
    metadata: Metadata = Field(default_factory=Metadata)
    websiteData: WebsiteData = Field(default_factory=WebsiteData)
    customerData: CustomerData = Field(default_factory=CustomerData)
    leadForms: List[Dict[str, Any]] = Field(default_factory=list)
    formSubmissions: List[Dict[str, Any]] = Field(default_factory=list)
    customDomain: Optional[str] = None


class CustomerInvitationResponse(CustomerInvitationUpdate):
    id: str
    templateId: str
    templateSnapshotId: str
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
    templateId: str
    templateSnapshotId: str
    customerStatus: CustomerStatus
    payment: PaymentInfo = Field(default_factory=PaymentInfo)
    statusHistory: List[StatusHistoryEntry] = Field(default_factory=list)
    publishedSnapshotId: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    model_config = ConfigDict(from_attributes=True)


class SnapshotResponse(BaseModel):
    id: str
    sourceId: str
    sourceType: str
    version: int
    slug: str
    snapshot: Dict[str, Any]
    createdAt: str
    publishedAt: str
