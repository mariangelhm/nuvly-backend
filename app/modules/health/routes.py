import logging

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.database import ping_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def health_check(request: Request):
    startup_status = getattr(request.app.state, "startup_status", "unknown")

    database_status = "ok"
    try:
        ping_database()
    except Exception:
        database_status = "error"
        if startup_status == "ready":
            startup_status = "degraded"
        logger.exception("Database health check failed")

    response_status = status.HTTP_200_OK
    if startup_status != "ready" or database_status != "ok":
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
        "status": startup_status,
        "database": database_status,
        "service": "nuvly-backend",
    }

    return JSONResponse(status_code=response_status, content=payload, headers={"Cache-Control": "no-store"})
