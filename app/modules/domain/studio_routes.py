from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Query, Request

from app.core.catalog import VariantLevel
from app.core.database import get_database
from app.modules.domain.schemas import (
    InvitationTemplateCreate,
    InvitationTemplateResponse,
    InvitationTemplateUpdate,
    PublishRequest,
    SnapshotResponse,
    StudioDashboardResponse,
    StudioQuickSummaryResponse,
    TemplateStatus,
    TemplateStatusUpdate,
    WebsiteTemplateCreate,
    WebsiteTemplateResponse,
    WebsiteTemplateUpdate,
)
from app.modules.domain.services import (
    INVITATION_TEMPLATE_CONFIG,
    WEBSITE_TEMPLATE_CONFIG,
    TemplateService,
)

router = APIRouter(prefix="/studio", tags=["studio"])
admin_router = APIRouter(prefix="/admin/studio", tags=["admin-studio"])
invitation_service = TemplateService(INVITATION_TEMPLATE_CONFIG)
website_service = TemplateService(WEBSITE_TEMPLATE_CONFIG)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _relative_time_label(value: str | None) -> str:
    parsed = _parse_iso_datetime(value)
    if not parsed:
        return "Hace un momento"
    delta = datetime.now(timezone.utc) - parsed
    total_seconds = max(int(delta.total_seconds()), 0)
    if total_seconds < 60:
        return "Hace un momento"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"Hace {minutes} minuto{'s' if minutes != 1 else ''}"
    hours = minutes // 60
    if hours < 24:
        return f"Hace {hours} hora{'s' if hours != 1 else ''}"
    days = hours // 24
    return f"Hace {days} día{'s' if days != 1 else ''}"


def _collection_exists(db: Any, collection_name: str) -> bool:
    try:
        return collection_name in db.list_collection_names()
    except Exception:
        return False


def _count_documents_if_collection_exists(db: Any, collection_name: str, filters: dict[str, Any]) -> int:
    if not _collection_exists(db, collection_name):
        return 0
    return db[collection_name].count_documents(filters)


def _build_recent_activity() -> list[dict[str, Any]]:
    db = get_database()
    events: list[dict[str, Any]] = []

    def add_event(event_id: str, title: str, event_type: str, created_at: str | None) -> None:
        if not created_at:
            return
        events.append(
            {
                "id": event_id,
                "title": title,
                "subtitle": f"Por Admin Studio · {_relative_time_label(created_at)}",
                "type": event_type,
                "createdAt": created_at,
            }
        )

    if _collection_exists(db, "website_templates"):
        for document in db["website_templates"].find({}, {"_id": 0, "id": 1, "title": 1, "createdAt": 1, "lastPublishedAt": 1}).limit(50):
            add_event(f"{document['id']}:created", f'Template "{document.get("title") or "Sin nombre"}" creado', "template", document.get("createdAt"))
            add_event(f"{document['id']}:published", f'Template "{document.get("title") or "Sin nombre"}" publicado', "template", document.get("lastPublishedAt"))

    if _collection_exists(db, "invitation_templates"):
        for document in db["invitation_templates"].find({}, {"_id": 0, "id": 1, "title": 1, "createdAt": 1, "lastPublishedAt": 1}).limit(50):
            add_event(f"{document['id']}:created", f'Template "{document.get("title") or "Sin nombre"}" creado', "template", document.get("createdAt"))
            add_event(f"{document['id']}:published", f'Template "{document.get("title") or "Sin nombre"}" publicado', "template", document.get("lastPublishedAt"))

    if _collection_exists(db, "customer_websites"):
        for document in db["customer_websites"].find({}, {"_id": 0, "id": 1, "title": 1, "createdAt": 1, "lastPublishedAt": 1, "payment": 1}).limit(50):
            title = document.get("title") or "Proyecto sin nombre"
            add_event(f"{document['id']}:created", f'Proyecto "{title}" creado', "project", document.get("createdAt"))
            add_event(f"{document['id']}:paid", f'Proyecto "{title}" pagado', "project", (document.get("payment") or {}).get("paidAt"))
            add_event(f"{document['id']}:published", f'Proyecto "{title}" publicado', "project", document.get("lastPublishedAt"))

    if _collection_exists(db, "customer_invitations"):
        for document in db["customer_invitations"].find({}, {"_id": 0, "id": 1, "title": 1, "createdAt": 1, "lastPublishedAt": 1, "payment": 1}).limit(50):
            title = document.get("title") or "Invitación sin nombre"
            add_event(f"{document['id']}:created", f'Invitación "{title}" creada', "invitation", document.get("createdAt"))
            add_event(f"{document['id']}:paid", f'Invitación "{title}" pagada', "invitation", (document.get("payment") or {}).get("paidAt"))
            add_event(f"{document['id']}:published", f'Invitación "{title}" publicada', "invitation", document.get("lastPublishedAt"))

    if _collection_exists(db, "pricing_plans"):
        for document in db["pricing_plans"].find({}, {"_id": 0, "id": 1, "name": 1, "updatedAt": 1}).limit(50):
            add_event(f"{document['id']}:updated", f'Plan "{document.get("name") or "Sin nombre"}" actualizado', "configuration", document.get("updatedAt"))

    if _collection_exists(db, "pricing_components"):
        for document in db["pricing_components"].find({}, {"_id": 0, "id": 1, "name": 1, "updatedAt": 1}).limit(50):
            add_event(f"{document['id']}:updated", f'Componente "{document.get("name") or "Sin nombre"}" actualizado', "component", document.get("updatedAt"))

    if _collection_exists(db, "users"):
        for document in db["users"].find({}, {"_id": 0, "id": 1, "name": 1, "email": 1, "createdAt": 1}).limit(50):
            title = document.get("name") or document.get("email") or "Usuario"
            add_event(f"{document['id']}:created", f'Cliente "{title}" registrado', "customer", document.get("createdAt"))

    events.sort(key=lambda item: _parse_iso_datetime(item["createdAt"]) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return events[:10]


def _build_quick_summary() -> StudioQuickSummaryResponse:
    db = get_database()
    return StudioQuickSummaryResponse(
        webTemplates=_count_documents_if_collection_exists(db, "website_templates", {}),
        invitationTemplates=_count_documents_if_collection_exists(db, "invitation_templates", {}),
        webComponents=_count_documents_if_collection_exists(db, "pricing_components", {"productType": "website"}),
        invitationComponents=_count_documents_if_collection_exists(db, "pricing_components", {"productType": "invitation"}),
        extras=_count_documents_if_collection_exists(db, "pricing_extras", {"active": True}),
        activeUsers=_count_documents_if_collection_exists(db, "users", {"active": True}),
    )


@router.post("/invitation-templates", response_model=InvitationTemplateResponse, status_code=201)
def create_invitation_template(payload: InvitationTemplateCreate, request: Request):
    return invitation_service.create(payload, base_url=str(request.base_url).rstrip("/"))


@router.get("/invitation-templates", response_model=list[InvitationTemplateResponse])
def list_invitation_templates(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    templateStatus: TemplateStatus | None = Query(default=None),
    category: str | None = Query(default=None),
    level: VariantLevel | None = Query(default=None),
    catalogVisible: bool | None = Query(default=None),
):
    return invitation_service.list(limit, skip, templateStatus, category, level, catalogVisible, base_url=str(request.base_url).rstrip("/"))


@router.get("/invitation-templates/{template_id}", response_model=InvitationTemplateResponse)
def get_invitation_template(template_id: str, request: Request):
    return invitation_service.get(template_id, base_url=str(request.base_url).rstrip("/"))


@router.put("/invitation-templates/{template_id}", response_model=InvitationTemplateResponse)
def update_invitation_template(template_id: str, payload: InvitationTemplateUpdate, request: Request):
    return invitation_service.update(template_id, payload, base_url=str(request.base_url).rstrip("/"))


@router.patch("/invitation-templates/{template_id}/status", response_model=InvitationTemplateResponse)
def update_invitation_template_status(template_id: str, payload: TemplateStatusUpdate, request: Request):
    return invitation_service.update_status(
        template_id,
        payload.templateStatus,
        payload.changedBy,
        payload.reason,
        base_url=str(request.base_url).rstrip("/"),
    )


@router.post("/invitation-templates/{template_id}/publish", response_model=SnapshotResponse)
def publish_invitation_template(template_id: str, request: Request, payload: PublishRequest | None = None):
    return invitation_service.publish(template_id, base_url=str(request.base_url).rstrip("/"), publish_request=payload)


@router.post("/invitation-templates/{template_id}/unpublish", response_model=InvitationTemplateResponse)
def unpublish_invitation_template(template_id: str, request: Request):
    return invitation_service.unpublish(template_id)


@router.post("/website-templates", response_model=WebsiteTemplateResponse, status_code=201)
def create_website_template(payload: WebsiteTemplateCreate, request: Request):
    return website_service.create(payload, base_url=str(request.base_url).rstrip("/"))


@router.get("/website-templates", response_model=list[WebsiteTemplateResponse])
def list_website_templates(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    skip: int = Query(default=0, ge=0),
    templateStatus: TemplateStatus | None = Query(default=None),
    category: str | None = Query(default=None),
    level: VariantLevel | None = Query(default=None),
    catalogVisible: bool | None = Query(default=None),
):
    return website_service.list(limit, skip, templateStatus, category, level, catalogVisible, base_url=str(request.base_url).rstrip("/"))


@router.get("/website-templates/{template_id}", response_model=WebsiteTemplateResponse)
def get_website_template(template_id: str, request: Request):
    return website_service.get(template_id, base_url=str(request.base_url).rstrip("/"))


@router.put("/website-templates/{template_id}", response_model=WebsiteTemplateResponse)
def update_website_template(template_id: str, payload: WebsiteTemplateUpdate, request: Request):
    return website_service.update(template_id, payload, base_url=str(request.base_url).rstrip("/"))


@router.patch("/website-templates/{template_id}/status", response_model=WebsiteTemplateResponse)
def update_website_template_status(template_id: str, payload: TemplateStatusUpdate, request: Request):
    return website_service.update_status(
        template_id,
        payload.templateStatus,
        payload.changedBy,
        payload.reason,
        base_url=str(request.base_url).rstrip("/"),
    )


@router.post("/website-templates/{template_id}/publish", response_model=SnapshotResponse)
def publish_website_template(template_id: str, payload: PublishRequest | None = None):
    return website_service.publish(template_id, publish_request=payload)


@router.post("/website-templates/{template_id}/unpublish", response_model=WebsiteTemplateResponse)
def unpublish_website_template(template_id: str):
    return website_service.unpublish(template_id)


@admin_router.get("/dashboard", response_model=StudioDashboardResponse)
def get_studio_dashboard():
    return {
        "recentActivity": _build_recent_activity(),
        "quickSummary": _build_quick_summary(),
    }
