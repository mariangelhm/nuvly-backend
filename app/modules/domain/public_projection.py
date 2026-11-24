"""Public views are projections, never copies of a private project document."""

from copy import deepcopy

PUBLIC_EXPERIENCE_FIELDS = frozenset(
    {
        "id",
        "title",
        "slug",
        "publicSlug",
        "experienceType",
        "productType",
        "planTier",
        "templateCategory",
        "templateStatus",
        "customerStatus",
        "templateComponent",
        "content",
        "styles",
        "layout",
        "blocks",
        "pages",
        "seo",
        "metadata",
        "invitationData",
        "websiteData",
        "templateId",
        "templateSnapshotId",
        "version",
        "schemaVersion",
        "publishedAt",
    }
)
PUBLIC_METADATA_FIELDS = frozenset(
    {
        "category",
        "style",
        "purpose",
        "eventType",
        "coverImage",
        "badge",
        "featured",
        "level",
        "basePrice",
        "basePriceSource",
        "tags",
        "catalogVisible",
        "previewVariant",
        "previewStyle",
        "previewImage",
        "previewKicker",
        "previewTitle",
        "previewMeta",
        "previewNames",
        "previewDate",
        "localPresetId",
        "productType",
        "planTier",
        "templateCategory",
        "linkedPages",
    }
)
PRIVATE_KEYS = frozenset(
    {
        "ownerId",
        "ownerEmail",
        "customerData",
        "payment",
        "externalAuthSubject",
        "externalAuthProvider",
        "guests",
        "rsvpResponses",
        "personalizedMessages",
        "formSubmissions",
        "statusHistory",
        "password",
        "passwordHash",
        "token",
        "tokenHash",
        "refreshToken",
        "accessToken",
        "providerLinks",
    }
)


def remove_private_fields(value):
    if isinstance(value, dict):
        return {key: remove_private_fields(item) for key, item in value.items() if key not in PRIVATE_KEYS}
    if isinstance(value, list):
        return [remove_private_fields(item) for item in value]
    return deepcopy(value)


def public_metadata(metadata: dict) -> dict:
    return remove_private_fields({key: value for key, value in metadata.items() if key in PUBLIC_METADATA_FIELDS})


def public_experience(document: dict) -> dict:
    projected = {key: value for key, value in document.items() if key in PUBLIC_EXPERIENCE_FIELDS}
    if "metadata" in projected:
        projected["metadata"] = public_metadata(projected["metadata"] or {})
    return remove_private_fields(projected)
