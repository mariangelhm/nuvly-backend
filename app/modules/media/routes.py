from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from app.modules.media.schemas import MediaAssetResponse, MediaScope
from app.modules.media.service import upload_media_asset

router = APIRouter(prefix="/media", tags=["media"])


@router.post(
    "/upload",
    response_model=MediaAssetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image asset",
)
def upload_media(
    request: Request,
    file: UploadFile = File(...),
    scope: Annotated[MediaScope | None, Form()] = None,
    ownerId: Annotated[str | None, Form()] = None,
):
    return upload_media_asset(file=file, scope=scope, owner_id=ownerId, request=request)
