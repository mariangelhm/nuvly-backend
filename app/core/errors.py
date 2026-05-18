from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class NuvlyError(Exception):
    def __init__(self, message: str, status_code: int = 400, code: str = "NUVLY_ERROR"):
        self.message = message
        self.status_code = status_code
        self.code = code
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NuvlyError)
    async def handle_nuvly_error(_: Request, exc: NuvlyError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message}},
        )
