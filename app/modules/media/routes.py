from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Form, Request, UploadFile, status

from app.modules.media.schemas import MediaAssetResponse, MediaBatchUploadResponse, MediaScope
from app.modules.media.service import upload_media_asset, upload_media_assets_batch

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


@router.post(
    "/upload-batch",
    response_model=MediaBatchUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload multiple image assets",
)
def upload_media_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    scope: Annotated[MediaScope | None, Form()] = None,
    ownerId: Annotated[str | None, Form()] = None,
    clientKeys: Annotated[list[str] | None, Form()] = None,
):
    return upload_media_assets_batch(
        files=files,
        scope=scope,
        owner_id=ownerId,
        client_keys=clientKeys,
        request=request,
    )
