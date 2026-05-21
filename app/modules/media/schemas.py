from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

MediaScope = Literal[
    "website_template",
    "invitation_template",
    "customer_website",
    "customer_invitation",
    "general",
]


class MediaAssetResponse(BaseModel):
    id: str
    url: str
    thumbnailUrl: str
    mimeType: str
    width: int
    height: int
    size: int
    scope: str
    ownerId: str | None = None
    createdAt: datetime


class BatchMediaAssetResponse(MediaAssetResponse):
    clientKey: str | None = None


class MediaBatchUploadResponse(BaseModel):
    assets: list[BatchMediaAssetResponse]
    errors: list[dict[str, str]]
