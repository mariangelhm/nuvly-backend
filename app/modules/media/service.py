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


def upload_media_asset(
    *,
    file: UploadFile,
    scope: str | None,
    owner_id: str | None,
    request: Request,
) -> dict:
    ensure_static_directories()
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

    resolved_scope = scope or DEFAULT_SCOPE
    asset_id = f"asset_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{uuid4().hex}"
    filename = f"{asset_id}.{extension}"
    upload_directory = ensure_upload_directory(resolved_scope)
    file_path = upload_directory / filename
    relative_path = file_path.as_posix()

    try:
        width, height = extract_dimensions(content_type, content)

        # Temporary MVP storage for Render. This filesystem is not permanent and must
        # be migrated later to object storage such as Cloudinary, S3 or Cloudflare R2.
        file_path.write_bytes(content)

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
            "scope": resolved_scope,
            "ownerId": owner_id,
            "createdAt": created_at,
            "storage": {
                "provider": "render_filesystem_mvp",
                "path": relative_path,
                "filename": filename,
            },
        }
        get_database().media_assets.insert_one(document)
        return document
    except NuvlyError:
        raise
    except Exception as exc:
        if file_path.exists():
            file_path.unlink(missing_ok=True)
        raise NuvlyError(
            f"Media upload failed: {exc}",
            status_code=500,
            code="UPLOAD_FAILED",
        ) from exc
    finally:
        file.file.close()
