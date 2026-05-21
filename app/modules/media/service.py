from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from uuid import uuid4
import struct
import xml.etree.ElementTree as ET

from fastapi import Request, UploadFile

from app.core.config import get_settings
from app.core.database import get_database
from app.core.errors import NuvlyError

STATIC_DIR = Path("static")
ALLOWED_CONTENT_TYPES: Final[dict[str, str]] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/svg+xml": "svg",
}
DEFAULT_SCOPE = "general"
MAX_BATCH_FILES = 20


def ensure_static_directories() -> None:
    STATIC_DIR.mkdir(parents=True, exist_ok=True)
    (STATIC_DIR / "uploads").mkdir(parents=True, exist_ok=True)


def ensure_upload_directory(scope: str) -> Path:
    directory = STATIC_DIR / "uploads" / scope
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def build_public_url(request: Request, relative_path: str) -> str:
    settings = get_settings()
    if settings.public_base_url:
        return f"{settings.public_base_url.rstrip('/')}/{relative_path.lstrip('/')}"

    base_url = str(request.base_url).rstrip("/")
    return f"{base_url}/{relative_path.lstrip('/')}"


def _extract_png_dimensions(content: bytes) -> tuple[int, int]:
    if len(content) < 24 or content[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid PNG file")
    return struct.unpack(">II", content[16:24])


def _extract_jpeg_dimensions(content: bytes) -> tuple[int, int]:
    if len(content) < 4 or content[:2] != b"\xff\xd8":
        raise ValueError("Invalid JPEG file")

    offset = 2
    while offset < len(content):
        if content[offset] != 0xFF:
            offset += 1
            continue
        while offset < len(content) and content[offset] == 0xFF:
            offset += 1
        if offset >= len(content):
            break
        marker = content[offset]
        offset += 1
        if marker in {0xD8, 0xD9}:
            continue
        if offset + 2 > len(content):
            break
        segment_length = struct.unpack(">H", content[offset:offset + 2])[0]
        if segment_length < 2 or offset + segment_length > len(content):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
            if offset + 7 > len(content):
                break
            height, width = struct.unpack(">HH", content[offset + 3:offset + 7])
            return width, height
        offset += segment_length

    raise ValueError("JPEG dimensions not found")


def _extract_webp_dimensions(content: bytes) -> tuple[int, int]:
    if len(content) < 30 or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise ValueError("Invalid WEBP file")

    chunk_type = content[12:16]
    if chunk_type == b"VP8 ":
        if len(content) < 30:
            raise ValueError("Invalid WEBP VP8 file")
        width, height = struct.unpack("<HH", content[26:30])
        return width & 0x3FFF, height & 0x3FFF

    if chunk_type == b"VP8L":
        if len(content) < 25:
            raise ValueError("Invalid WEBP VP8L file")
        bits = int.from_bytes(content[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height

    if chunk_type == b"VP8X":
        if len(content) < 30:
            raise ValueError("Invalid WEBP VP8X file")
        width = int.from_bytes(content[24:27], "little") + 1
        height = int.from_bytes(content[27:30], "little") + 1
        return width, height

    raise ValueError("Unsupported WEBP chunk type")


def _parse_svg_length(value: str | None) -> int | None:
    if not value:
        return None
    numeric = "".join(character for character in value if character.isdigit() or character in {".", "-"})
    if not numeric:
        return None
    return max(int(float(numeric)), 0)


def _extract_svg_dimensions(content: bytes) -> tuple[int, int]:
    root = ET.fromstring(content.decode("utf-8"))
    width = _parse_svg_length(root.attrib.get("width"))
    height = _parse_svg_length(root.attrib.get("height"))
    if width and height:
        return width, height

    view_box = root.attrib.get("viewBox")
    if view_box:
        parts = view_box.replace(",", " ").split()
        if len(parts) == 4:
            return max(int(float(parts[2])), 0), max(int(float(parts[3])), 0)

    raise ValueError("SVG dimensions not found")


def extract_dimensions(content_type: str, content: bytes) -> tuple[int, int]:
    if content_type == "image/png":
        return _extract_png_dimensions(content)
    if content_type == "image/jpeg":
        return _extract_jpeg_dimensions(content)
    if content_type == "image/webp":
        return _extract_webp_dimensions(content)
    if content_type == "image/svg+xml":
        return _extract_svg_dimensions(content)
    raise ValueError("Unsupported content type")


def _raise_invalid_file_type() -> None:
    raise NuvlyError(
        "Invalid file type. Allowed types: image/jpeg, image/png, image/webp, image/svg+xml.",
        status_code=400,
        code="INVALID_FILE_TYPE",
    )


def _resolve_scope(scope: str | None) -> str:
    return scope or DEFAULT_SCOPE


def _validate_batch_size(files: list[UploadFile]) -> None:
    if len(files) > MAX_BATCH_FILES:
        raise NuvlyError(
            f"Batch upload supports a maximum of {MAX_BATCH_FILES} files per request.",
            status_code=400,
            code="TOO_MANY_FILES",
        )


def _build_asset_payload(
    *,
    file: UploadFile,
    scope: str,
    owner_id: str | None,
    request: Request,
    client_key: str | None = None,
) -> dict:
    settings = get_settings()

    content_type = (file.content_type or "").lower().strip()
    extension = ALLOWED_CONTENT_TYPES.get(content_type)
    if extension is None:
        _raise_invalid_file_type()

    content = file.file.read()
    size = len(content)
    if size > settings.media_max_size_bytes:
        raise NuvlyError(
            f"File exceeds the maximum allowed size of {settings.media_max_size_mb}MB.",
            status_code=400,
            code="FILE_TOO_LARGE",
        )

    asset_id = f"asset_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{uuid4().hex}"
    filename = f"{asset_id}.{extension}"
    upload_directory = ensure_upload_directory(scope)
    file_path = upload_directory / filename
    relative_path = file_path.as_posix()
    width, height = extract_dimensions(content_type, content)
    created_at = datetime.now(timezone.utc)
    asset_url = build_public_url(request, relative_path)
    document = {
        "id": asset_id,
        "url": asset_url,
        "thumbnailUrl": asset_url,
        "mimeType": content_type,
        "width": width,
        "height": height,
        "size": size,
        "scope": scope,
        "ownerId": owner_id,
        "createdAt": created_at,
        "storage": {
            "provider": "render_filesystem_mvp",
            "path": relative_path,
            "filename": filename,
        },
    }
    if client_key is not None:
        document["clientKey"] = client_key

    return {"document": document, "content": content, "file_path": file_path}


def _persist_prepared_assets(prepared_assets: list[dict], *, error_code: str, error_message: str) -> list[dict]:
    collection = get_database().media_assets
    saved_paths: list[Path] = []
    inserted_ids: list[str] = []

    try:
        # Temporary MVP storage for Render. This filesystem is not permanent and must
        # be migrated later to object storage such as Cloudinary, S3 or Cloudflare R2.
        for prepared_asset in prepared_assets:
            prepared_asset["file_path"].write_bytes(prepared_asset["content"])
            saved_paths.append(prepared_asset["file_path"])

        documents = [prepared_asset["document"] for prepared_asset in prepared_assets]
        if len(documents) == 1:
            collection.insert_one(documents[0])
            inserted_ids.append(documents[0]["id"])
        else:
            if hasattr(collection, "insert_many"):
                collection.insert_many(documents, ordered=True)
                inserted_ids.extend(document["id"] for document in documents)
            else:
                for document in documents:
                    collection.insert_one(document)
                    inserted_ids.append(document["id"])
        return documents
    except NuvlyError:
        raise
    except Exception as exc:
        for file_path in saved_paths:
            if file_path.exists():
                file_path.unlink(missing_ok=True)
        if inserted_ids and hasattr(collection, "delete_many"):
            collection.delete_many({"id": {"$in": inserted_ids}})
        raise NuvlyError(
            f"{error_message}: {exc}",
            status_code=500,
            code=error_code,
        ) from exc


def upload_media_asset(
    *,
    file: UploadFile,
    scope: str | None,
    owner_id: str | None,
    request: Request,
) -> dict:
    ensure_static_directories()
    try:
        prepared_asset = _build_asset_payload(
            file=file,
            scope=_resolve_scope(scope),
            owner_id=owner_id,
            request=request,
        )
        return _persist_prepared_assets(
            [prepared_asset],
            error_code="UPLOAD_FAILED",
            error_message="Media upload failed",
        )[0]
    finally:
        file.file.close()


def upload_media_assets_batch(
    *,
    files: list[UploadFile],
    scope: str | None,
    owner_id: str | None,
    client_keys: list[str] | None,
    request: Request,
) -> dict:
    ensure_static_directories()
    _validate_batch_size(files)

    if client_keys is not None and len(client_keys) != len(files):
        for file in files:
            file.file.close()
        raise NuvlyError(
            "clientKeys must match the number of uploaded files.",
            status_code=400,
            code="UPLOAD_BATCH_FAILED",
        )

    resolved_scope = _resolve_scope(scope)
    prepared_assets: list[dict] = []
    try:
        for index, file in enumerate(files):
            client_key = client_keys[index] if client_keys is not None else None
            prepared_assets.append(
                _build_asset_payload(
                    file=file,
                    scope=resolved_scope,
                    owner_id=owner_id,
                    request=request,
                    client_key=client_key,
                )
            )

        documents = _persist_prepared_assets(
            prepared_assets,
            error_code="UPLOAD_BATCH_FAILED",
            error_message="Batch media upload failed",
        )
        return {"assets": documents, "errors": []}
    finally:
        for file in files:
            file.file.close()
