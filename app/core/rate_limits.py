"""Shared atomic fixed-window budgets; identifiers are stored only as hashes."""

import time
from datetime import datetime, timezone
from hashlib import sha256

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse

from app.core.database import get_database
from app.core.errors import NuvlyError


def consume_rate_limit(scope, subject, limit, seconds, *, cost=1, now=None):
    current = time.time() if now is None else now
    bucket = int(current // seconds)
    key = sha256(f"{scope}:{str(subject).strip().lower()}:{bucket}".encode()).hexdigest()
    operation = {
        "$inc": {"count": cost},
        "$setOnInsert": {"expiresAt": datetime.fromtimestamp((bucket + 2) * seconds, timezone.utc)},
    }
    try:
        collection = get_database().rate_limits
        try:
            result = collection.find_one_and_update(
                {"_id": key}, operation, upsert=True, return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError:
            result = collection.find_one_and_update(
                {"_id": key}, {"$inc": {"count": cost}}, return_document=ReturnDocument.AFTER
            )
    except Exception as error:
        raise NuvlyError(
            "El servicio está temporalmente ocupado. Inténtalo nuevamente.", 503, "RATE_LIMIT_UNAVAILABLE"
        ) from error
    if result is None or result["count"] > limit:
        error = NuvlyError("Demasiadas solicitudes. Espera antes de reintentar.", 429, "RATE_LIMIT_EXCEEDED")
        error.retry_after = max(1, int((bucket + 1) * seconds - current))
        raise error


class AbuseLimitMiddleware:
    def __init__(self, app, *, api_prefix):
        self.app = app
        self.prefix = api_prefix.rstrip("/")

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        policies = {
            "/auth/login": (30, 60),
            "/admin/auth/login": (30, 60),
            "/auth/register": (10, 300),
            "/auth/google": (30, 60),
            "/auth/google/challenge": (30, 60),
            "/auth/forgot-password": (5, 900),
            "/auth/reset-password": (10, 900),
            "/media/upload": (30, 60),
            "/media/upload-batch": (30, 60),
            "/customer/invitations": (10, 60),
            "/customer/websites": (10, 60),
            "/support/contact": (5, 900),
            "/payments/preview": (60, 60),
            "/payments/create-checkout": (10, 60),
            "/payments/webhooks/mercadopago": (120, 60),
            "/analytics/experience": (120, 60),
        }
        policy = policies.get(path[len(self.prefix) :]) if path.startswith(self.prefix + "/") else None
        if path.startswith(self.prefix + "/payments/") and path.endswith("/receipt-email"):
            policy = (5, 900)
        if scope["type"] == "http" and scope.get("method") == "POST" and policy:
            try:
                await run_in_threadpool(
                    consume_rate_limit, "ip:" + path, (scope.get("client") or ("unknown",))[0], *policy
                )
            except NuvlyError as error:
                headers = {"Retry-After": str(error.retry_after)} if hasattr(error, "retry_after") else {}
                return await JSONResponse(
                    {"error": {"code": error.code, "message": error.message}},
                    status_code=error.status_code,
                    headers=headers,
                )(scope, receive, send)
        await self.app(scope, receive, send)
