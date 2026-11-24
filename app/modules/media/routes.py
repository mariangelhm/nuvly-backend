from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status

from app.core.config import get_settings
from app.core.errors import NuvlyError
from app.core.rate_limits import consume_rate_limit
from app.modules.auth.dependencies import get_current_user
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
    current_user: dict = Depends(get_current_user),
):
    _authorize_scope(scope, current_user)
    _limit_owner(current_user, [file])
    return upload_media_asset(file=file, scope=scope, owner_id=current_user["id"], request=request)


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
    current_user: dict = Depends(get_current_user),
):
    _authorize_scope(scope, current_user)
    _limit_owner(current_user, files)
    return upload_media_assets_batch(
        files=files,
        scope=scope,
        owner_id=current_user["id"],
        client_keys=clientKeys,
        request=request,
    )


def _authorize_scope(scope, user):
    if scope in {"website_template", "invitation_template"} and user.get("accountType") != "internal":
        raise NuvlyError("Solo usuarios internos pueden subir recursos de templates.", 403, "MEDIA_SCOPE_FORBIDDEN")


def _limit_owner(user, files):
    consume_rate_limit("media-owner", user["id"], 20, 60)
    total = sum(file.size or 0 for file in files)
    if total:
        consume_rate_limit(
            "media-owner-bytes", user["id"], get_settings().media_owner_daily_upload_mb * 1024 * 1024, 86400, cost=total
        )
