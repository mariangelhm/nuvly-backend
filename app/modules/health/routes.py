from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from app.core.database import ping_database

router = APIRouter(prefix="/health", tags=["health"])

@router.get("")
def health_check(request: Request):
    startup_status = getattr(request.app.state, "startup_status", "unknown")
    startup_error = getattr(request.app.state, "startup_error", None)

    database_status = "ok"
    try:
        ping_database()
    except Exception as exc:
        database_status = "error"
        if startup_status == "ready":
            startup_status = "degraded"
        if not startup_error:
            startup_error = str(exc)

    response_status = status.HTTP_200_OK
    if startup_status == "starting" or database_status != "ok":
        response_status = status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
        "status": startup_status,
        "database": database_status,
        "service": "nuvly-backend",
    }
    if startup_error:
        payload["error"] = startup_error

    return JSONResponse(status_code=response_status, content=payload)
