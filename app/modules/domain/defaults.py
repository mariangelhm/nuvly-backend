from copy import deepcopy

from app.core.catalog import DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE, DEFAULT_TEMPLATE_CATEGORY_BY_PRODUCT_TYPE


def default_page_source() -> dict:
    return {
        "blockId": None,
        "blockType": None,
        "sourceItemIndex": None,
        "sourceChildKey": None,
    }


def default_main_page(title: str = "Pagina principal", blocks: list[dict] | None = None) -> dict:
    return {
        "id": "main",
        "kind": "primary",
        "title": title,
        "slug": "",
        "path": "/",
        "parentPageId": None,
        "source": default_page_source(),
        "seo": {},
        "settings": {},
        "blocks": deepcopy(blocks or []),
    }


def default_metadata(entity_kind: str) -> dict:
    base = {
        "category": "invitation" if entity_kind == "invitation" else "landing",
        "style": "",
        "purpose": "",
        "eventType": "wedding" if entity_kind == "invitation" else "",
        "coverImage": "",
        "badge": "",
        "featured": False,
        "level": "core",
        "basePrice": 0,
        "tags": [],
        "catalogVisible": False,
        "previewVariant": "",
        "previewStyle": {},
        "linkedPages": [],
    }
    return deepcopy(base)


def default_invitation_data() -> dict:
    return {
        "eventType": "wedding",
        "coupleNames": [],
        "eventDate": None,
        "venueName": "",
        "venueAddress": "",
        "mapUrl": "",
        "rsvpEnabled": True,
        "guestLimit": None,
        "personalizedUrlsEnabled": False,
        "thankYouMessageEnabled": False,
    }


def default_website_data() -> dict:
    return {
        "businessName": "",
        "industry": "",
        "contactEmail": "",
        "contactPhone": "",
        "primaryGoal": "",
        "leadFormEnabled": False,
        "analyticsEnabled": False,
    }


def default_customer_data() -> dict:
    return {
        "name": "",
        "email": "",
        "phone": "",
    }


def default_payment() -> dict:
    return {
        "status": "unpaid",
        "provider": None,
        "providerPaymentId": None,
        "amount": None,
        "subtotalAmount": None,
        "discountAmount": 0,
        "discountCode": None,
        "discountType": None,
        "discountValue": None,
        "currency": None,
        "paidAt": None,
    }


def default_invitation_customer_fields() -> dict:
    return {
        "guests": [],
        "rsvpResponses": [],
        "personalizedMessages": [],
    }


def default_website_customer_fields() -> dict:
    return {
        "leadForms": [],
        "formSubmissions": [],
        "customDomain": None,
    }


def default_template_document(entity_kind: str, title: str, slug: str, now: str, document_id: str) -> dict:
    product_type = "invitation" if entity_kind == "invitation" else "website"
    data: dict = {
        "id": document_id,
        "title": title,
        "slug": slug,
        "experienceType": "invitation" if entity_kind == "invitation" else "web",
        "productType": product_type,
        "planTier": DEFAULT_PLAN_TIER_BY_PRODUCT_TYPE[product_type],
        "templateCategory": DEFAULT_TEMPLATE_CATEGORY_BY_PRODUCT_TYPE[product_type],
        "styles": {
            "themeId": None,
            "colors": {},
            "typography": {},
        },
        "layout": {"sectionOrder": []},
        "blocks": [],
        "pages": [default_main_page(title)],
        "seo": {
            "title": title,
            "description": "",
            "noIndex": True,
        },
        "metadata": default_metadata(entity_kind),
        "selectedComponentExtras": [],
        "templateStatus": "draft",
        "statusHistory": [],
        "publishedSnapshotId": None,
        "lastPublishedAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    if entity_kind == "invitation":
        data["invitationData"] = default_invitation_data()
    return data
