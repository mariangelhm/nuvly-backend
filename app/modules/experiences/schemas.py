from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field

ExperienceType = Literal["web", "invitation"]
ExperienceStatus = Literal["draft", "private_preview", "published", "archived"]

class ExperienceCreate(BaseModel):
    experienceType: ExperienceType
    presetId: Optional[str] = None
    title: str = Field(min_length=1, max_length=120)

class ExperienceStatusUpdate(BaseModel):
    status: ExperienceStatus

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
    integrations: Dict[str, Any] = Field(default_factory=dict)
    analytics: Dict[str, Any] = Field(default_factory=dict)
    previewVariant: str = ""
    previewStyle: Dict[str, Any] = Field(default_factory=dict)

class ExperienceUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(min_length=1, max_length=160)
    experienceType: ExperienceType
    status: ExperienceStatus = "draft"
    presetId: Optional[str] = None
    styles: Styles = Field(default_factory=Styles)
    layout: Layout = Field(default_factory=Layout)
    blocks: List[ExperienceBlock] = Field(default_factory=list)
    seo: Seo = Field(default_factory=Seo)
    metadata: Metadata = Field(default_factory=Metadata)
    content: Optional[Any] = None

class ExperienceResponse(ExperienceUpdate):
    id: str
    publishedSnapshotId: Optional[str] = None
    lastPublishedAt: Optional[str] = None
    createdAt: str
    updatedAt: str
    model_config = ConfigDict(from_attributes=True)

class SnapshotResponse(BaseModel):
    id: str
    experienceId: str
    experienceType: ExperienceType
    slug: str
    version: int
    snapshot: Dict[str, Any]
    createdAt: str
    publishedAt: str
