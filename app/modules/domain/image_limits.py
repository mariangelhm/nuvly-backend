"""Media quotas shared by invitation and website customer projects."""

import re
from urllib.parse import parse_qs, urlsplit

from app.core.errors import NuvlyError

WEBSITE_IMAGE_LIMITS = {"essential": 16, "plus": 16, "pro": 24, "custom": 60}
INVITATION_IMAGE_LIMITS = {"essential": 8, "plus": 8, "pro": 16, "custom": 60}
PLAN_VIDEO_LIMITS = {"essential": 0, "plus": 0, "pro": 1, "custom": 1}
PLAN_NAMES = {"essential": "Básico", "plus": "Básico", "pro": "Avanzado", "custom": "Personalizable"}


def canonical_image_url(value):
    value = str(value or "").strip()
    if value.startswith("url("):
        value = value[4:-1].strip(" \"'")
    parsed = urlsplit(value)
    return parsed.path if parsed.path.startswith(("/static/", "/media/", "/assets/")) else value


def canonical_video_url(value):
    parsed = urlsplit(value)
    host = (parsed.hostname or "").removeprefix("www.")
    if host in ("youtube.com", "m.youtube.com", "youtube-nocookie.com", "youtu.be"):
        match = re.match(r"^/(?:embed|shorts)/([^/]+)", parsed.path)
        video_id = (
            parsed.path.lstrip("/")
            if host == "youtu.be"
            else (parse_qs(parsed.query).get("v", [None])[0] or (match[1] if match else None))
        )
        if video_id:
            return f"youtube:{video_id}"
    return canonical_image_url(value)


def project_media_urls(document, kind="image"):
    result = set()

    def collect(value, context="", block=None):
        # Ignore demo links in disabled starter blocks; images still use storage.
        if kind == "video" and block and block.get("enabled") is False:
            return
        if isinstance(value, dict):
            if value.get("type") and value.get("variant"):
                block = value
            if kind == "video" and block and block.get("enabled") is False:
                return
            for name, nested in value.items():
                # Shared defaults may contain videos unused by the selected variant.
                unused_video = (
                    kind == "video"
                    and block
                    and block.get("variant")
                    and (
                        (
                            block.get("type") == "hero"
                            and name == "videoUrl"
                            and block["variant"] != "HP2-Editorial-Video-Youtube"
                        )
                        or (
                            block.get("type") == "socialProof"
                            and re.fullmatch(r"proofVideo(?:Url|File)\d+", name)
                            and block["variant"] != "PSP2-Video-Grid"
                        )
                    )
                )
                if not unused_video and not re.search(r"Files$|Quota$|Snapshot$", name, re.I):
                    collect(nested, f"{context}.{name}", block)
        elif isinstance(value, list):
            for nested in value:
                collect(nested, context, block)
        elif isinstance(value, str):
            image_field = bool(re.search(r"image|logo|avatar|photo|poster|thumbnail|gallery", context, re.I))
            video_field = bool(re.search(r"video|youtube", context, re.I)) and not image_field
            raw = value.strip()
            if raw.startswith("url("):
                raw = raw[4:-1].strip(" \"'")
            for ref in re.split(r"[|\s]+", raw):
                if not ref.startswith(("http://", "https://", "/", "blob:", "data:image", "data:video")):
                    continue
                image = bool(re.search(r"\.(?:png|jpe?g|webp|gif|svg|avif)(?:[?#].*)?$", ref, re.I)) or ref.startswith(
                    "data:image"
                )
                video = bool(re.search(r"\.(?:mp4|webm|mov|m4v)(?:[?#].*)?$", ref, re.I)) or ref.startswith(
                    "data:video"
                )
                if kind == "image" and (image or (image_field and not video)):
                    result.add(canonical_image_url(ref))
                if kind == "video" and (video or (video_field and not image)):
                    result.add(canonical_video_url(ref))

    pages = document.get("pages") or []
    blocks = [block for page in pages for block in page.get("blocks") or []] if pages else document.get("blocks") or []
    linked_blocks = [
        block for page in (document.get("metadata") or {}).get("linkedPages", []) for block in page.get("blocks") or []
    ]
    for block in [*blocks, *linked_blocks]:
        collect({**(block.get("settings") or {}), **(block.get("props") or {})}, block=block)
    for key in ("styles", "content", "images", "gallery", "base", "invitationData", "websiteData"):
        collect(document.get(key) or {}, key)
    return result


def project_image_urls(document):
    return project_media_urls(document)


def website_image_quota(document, template_snapshot=None):
    tier = document.get("planTier") or "plus"
    limits = INVITATION_IMAGE_LIMITS if document.get("productType") == "invitation" else WEBSITE_IMAGE_LIMITS
    return {
        "limit": limits.get(tier, limits["plus"]),
        "used": len(project_image_urls(document)),
        "includesTemplateImages": True,
        "planName": PLAN_NAMES.get(tier, "Básico"),
    }


def project_video_quota(document):
    tier = document.get("planTier") or "plus"
    return {
        "limit": PLAN_VIDEO_LIMITS.get(tier, 0),
        "used": len(project_media_urls(document, "video")),
        "planName": PLAN_NAMES.get(tier, "Básico"),
    }


def validate_website_image_quota(document, template_snapshot=None):
    quota = website_image_quota(document)
    if quota["used"] > quota["limit"]:
        raise NuvlyError(
            f"Tu plan {quota['planName']} permite hasta {quota['limit']} imágenes en total, incluidas las del template. Quita una imagen para liberar un cupo.",
            422,
            "IMAGE_QUOTA_EXCEEDED",
        )
    return quota


def validate_project_media_quota(document):
    validate_website_image_quota(document)
    quota = project_video_quota(document)
    if quota["used"] > quota["limit"]:
        message = (
            "El plan Básico no incluye videos. El plan Avanzado incluye 1 video."
            if quota["limit"] == 0
            else f"Tu plan {quota['planName']} permite hasta {quota['limit']} video en total. Quita el video anterior para reemplazarlo."
        )
        raise NuvlyError(message, 422, "VIDEO_QUOTA_EXCEEDED")

    if any(url.startswith(("/", "blob:", "data:")) for url in project_media_urls(document, "video")):
        raise NuvlyError(
            "El video debe ser un enlace externo. No se permiten archivos de video guardados en Nuvly.",
            422,
            "EXTERNAL_VIDEO_REQUIRED",
        )
