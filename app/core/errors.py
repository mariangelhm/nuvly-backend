import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class NuvlyError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "NUVLY_ERROR"):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


def _request_context(request: Request) -> str:
    return f"{request.method} {request.url.path}"


def _validation_details(exc: RequestValidationError) -> list[dict[str, object]]:
    details: list[dict[str, object]] = []
    for error in exc.errors():
        raw_loc = error.get("loc", ())
        field_path = [str(part) for part in raw_loc if part != "body"]
        details.append(
            {
                "field": ".".join(field_path) if field_path else None,
                "message": error.get("msg", "Invalid value."),
                "type": error.get("type", "validation_error"),
            }
        )
    return details


def _validation_error_payload(request: Request, exc: RequestValidationError) -> dict[str, object]:
    details = _validation_details(exc)
    path = request.url.path.rstrip("/")
    if path.endswith("/auth/register"):
        return {
            "code": "AUTH_REGISTER_VALIDATION_ERROR",
            "message": "Datos inválidos para registro.",
            "details": details,
        }
    if path.endswith("/auth/login"):
        return {
            "code": "AUTH_LOGIN_VALIDATION_ERROR",
            "message": "Datos inválidos para inicio de sesión.",
            "details": details,
        }
    return {
        "code": "REQUEST_VALIDATION_ERROR",
        "message": "Request validation failed.",
        "details": details,
    }


async def handle_nuvly_error(request: Request, exc: NuvlyError):
    logger.warning(
        "Handled NuvlyError | request=%s | status=%s | code=%s | message=%s",
        _request_context(request),
        exc.status_code,
        exc.code,
        exc.message,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def handle_request_validation_error(request: Request, exc: RequestValidationError):
    logger.warning(
        "Request validation failed | request=%s | errors=%s",
        _request_context(request),
        exc.errors(),
    )
    payload = _validation_error_payload(request, exc)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": payload},
    )


async def handle_response_validation_error(request: Request, exc: ResponseValidationError):
    logger.exception(
        "Response validation failed | request=%s | errors=%s",
        _request_context(request),
        exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "RESPONSE_VALIDATION_ERROR", "message": "Response validation failed."}},
    )


async def handle_unexpected_error(request: Request, exc: Exception):
    logger.exception("Unhandled exception | request=%s", _request_context(request), exc_info=exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": {"code": "INTERNAL_SERVER_ERROR", "message": "Internal server error."}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(NuvlyError, handle_nuvly_error)
    app.add_exception_handler(RequestValidationError, handle_request_validation_error)
    app.add_exception_handler(ResponseValidationError, handle_response_validation_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
