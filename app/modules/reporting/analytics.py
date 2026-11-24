from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.config import get_settings
from app.modules.auth.dependencies import get_current_admin_user
from app.modules.domain.repository import DomainRepository

router = APIRouter(prefix="/analytics", tags=["analytics"])
repository = DomainRepository()


class ExperienceMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: Literal["route_load", "navigation_error", "render_error", "script_error", "promise_error"]
    page: Literal[
        "home", "catalog", "template", "login", "products", "editor", "checkout", "payment_return", "contact", "legal"
    ]
    productType: Literal["", "website", "invitation"] = ""
    durationMs: float | None = Field(default=None, ge=0, le=60000)
    consent: Literal[True]

    @model_validator(mode="after")
    def check_duration(self):
        if (self.kind == "route_load") != (self.durationMs is not None):
            raise ValueError("Duration is required only for route_load")
        return self


@router.post("/experience", status_code=202)
def record_experience_metric(payload: ExperienceMetric):
    now = datetime.now(timezone.utc)
    document = payload.model_dump(exclude_none=True, exclude={"consent"})
    document.update(
        receivedAt=now,
        expiresAt=now + timedelta(days=30),
        environment="production" if get_settings().app_env.lower() in ("production", "prod") else "test",
    )
    repository.collection("experience_metrics").insert_one(document)
    return {"accepted": True}


@router.get("/experience", dependencies=[Depends(get_current_admin_user)])
def experience_summary(days: int = Query(default=7, ge=1, le=30)):
    environment = "production" if get_settings().app_env.lower() in ("production", "prod") else "test"
    return {
        "days": days,
        "environment": environment,
        "items": list(
            repository.collection("experience_metrics").aggregate(
                [
                    {
                        "$match": {
                            "environment": environment,
                            "receivedAt": {"$gte": datetime.now(timezone.utc) - timedelta(days=days)},
                        }
                    },
                    {
                        "$group": {
                            "_id": {"page": "$page", "kind": "$kind", "productType": "$productType"},
                            "count": {"$sum": 1},
                            "averageMs": {"$avg": "$durationMs"},
                            "maxMs": {"$max": "$durationMs"},
                        }
                    },
                    {"$sort": {"count": -1}},
                    {"$limit": 100},
                ],
                maxTimeMS=5000,
            )
        ),
    }


class AnalyticsEvent(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    sessionId: str = Field(pattern=r"^[a-f0-9]{32}$")
    sequence: int = Field(ge=1, le=10000000)
    event: Literal[
        "page_view",
        "catalog_viewed",
        "template_viewed",
        "template_selected",
        "editor_opened",
        "checkout_viewed",
        "draft_saved",
        "contact_opened",
        "support_clicked",
    ]
    page: Literal[
        "home", "catalog", "template", "login", "products", "editor", "checkout", "payment_return", "contact", "legal"
    ]
    templateId: str | None = Field(default=None, pattern=r"^[a-zA-Z0-9_-]{1,120}$")
    productType: Literal["", "website", "invitation"] = ""
    consent: Literal[True]


@router.post("/events", status_code=202)
def record_event(payload: AnalyticsEvent):
    now = datetime.now(timezone.utc)
    collection = repository.collection("analytics_events")
    # Best-effort telemetry is deliberately independent from checkout operations.
    if (
        collection.count_documents(
            {"sessionId": payload.sessionId, "receivedAt": {"$gte": (now - timedelta(minutes=1)).isoformat()}},
            limit=120,
        )
        >= 120
    ):
        return {"accepted": False}
    document = payload.model_dump(exclude_none=True)
    document.update(
        receivedAt=now.isoformat(),
        expiresAt=now + timedelta(days=180),
        environment="production" if get_settings().app_env.lower() in ("production", "prod") else "test",
    )
    collection.update_one({"id": payload.id}, {"$setOnInsert": document}, upsert=True)
    return {"accepted": True}
