from app.modules.experiences.utils import new_id

def default_styles() -> dict:
    return {
        "themeId": "default",
        "colors": {"backgroundColor": "#ffffff", "surfaceColor": "#f8fafc", "textColor": "#111827", "accentColor": "#7c3aed"},
        "typography": {"headingFont": "Inter, sans-serif", "subtitleFont": "Inter, sans-serif", "bodyFont": "Inter, sans-serif"},
    }

def default_seo(title: str) -> dict:
    return {"title": title, "description": "", "noIndex": True}

def default_metadata(experience_type: str) -> dict:
    return {
        "category": "invitation" if experience_type == "invitation" else "landing",
        "style": "", "purpose": "", "eventType": "wedding" if experience_type == "invitation" else "",
        "coverImage": "", "badge": "", "featured": False, "level": "basic", "basePrice": 0,
        "tags": [], "catalogVisible": False,
        "integrations": {"formProvider": "", "analyticsProvider": "", "calendarProvider": ""},
        "analytics": {"enabled": False, "trackingId": ""},
        "previewVariant": "", "previewStyle": {},
    }

def default_blocks(experience_type: str) -> list[dict]:
    if experience_type == "invitation":
        ids = [new_id("blk") for _ in range(5)]
        return [
            {"id": ids[0], "type": "hero", "variant": "H3-Invitation-Cover", "enabled": True, "order": 1, "props": {"eyebrow": "Nos casamos", "title": "Mari & José", "subtitle": "Acompáñanos en este día especial"}, "settings": {"elementVisibility": {"eyebrow": True, "subtitle": True}}},
            {"id": ids[1], "type": "countdown", "variant": "C1-Classic", "enabled": True, "order": 2, "props": {"title": "Faltan", "date": ""}, "settings": {}},
            {"id": ids[2], "type": "details", "variant": "D1-Cards", "enabled": True, "order": 3, "props": {"title": "Detalles del evento", "place": "", "date": "", "time": ""}, "settings": {}},
            {"id": ids[3], "type": "rsvp", "variant": "R1-Form", "enabled": True, "order": 4, "props": {"title": "Confirma tu asistencia", "buttonLabel": "Confirmar"}, "settings": {}},
            {"id": ids[4], "type": "footer", "variant": "FO1-Minimal", "enabled": True, "order": 5, "props": {"title": "Gracias por acompañarnos"}, "settings": {}},
        ]
    ids = [new_id("blk") for _ in range(4)]
    return [
        {"id": ids[0], "type": "navigation", "variant": "N1-Overlay-Nav", "enabled": True, "order": 1, "props": {"title": "Nuvly Web", "buttonLabel": "Contactar"}, "settings": {"elementVisibility": {"buttonLabel": True}}},
        {"id": ids[1], "type": "hero", "variant": "H1-Centered", "enabled": True, "order": 2, "props": {"eyebrow": "Nueva página", "title": "Tu web lista para publicar", "subtitle": "Edita bloques, estilos y contenido desde Nuvly Studio."}, "settings": {"elementVisibility": {"eyebrow": True, "subtitle": True}}},
        {"id": ids[2], "type": "services", "variant": "SV1-Cards", "enabled": True, "order": 3, "props": {"title": "Servicios", "itemsText": "Diseño|Web moderna\nPublicación|URL lista"}, "settings": {}},
        {"id": ids[3], "type": "footer", "variant": "FO1-Minimal", "enabled": True, "order": 4, "props": {"title": "Nuvly"}, "settings": {}},
    ]
