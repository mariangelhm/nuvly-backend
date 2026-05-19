from copy import deepcopy


def default_metadata(entity_kind: str) -> dict:
    base = {
        "category": "invitation" if entity_kind == "invitation" else "landing",
        "style": "",
        "purpose": "",
        "eventType": "wedding" if entity_kind == "invitation" else "",
        "coverImage": "",
        "badge": "",
        "featured": False,
        "level": "basic",
        "basePrice": 0,
        "tags": [],
        "catalogVisible": False,
        "previewVariant": "",
        "previewStyle": {},
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
    data: dict = {
        "id": document_id,
        "title": title,
        "slug": slug,
        "styles": {
            "themeId": None,
            "colors": {},
            "typography": {},
        },
        "layout": {"sectionOrder": []},
        "blocks": [],
        "seo": {
            "title": title,
            "description": "",
            "noIndex": True,
        },
        "metadata": default_metadata(entity_kind),
        "templateStatus": "draft",
        "statusHistory": [],
        "publishedSnapshotId": None,
        "lastPublishedAt": None,
        "createdAt": now,
        "updatedAt": now,
    }
    if entity_kind == "invitation":
        data["invitationData"] = default_invitation_data()
    else:
        data["websiteData"] = default_website_data()
    return data
